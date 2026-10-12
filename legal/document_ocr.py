"""Bounded client for the operator's private, prewarmed document parser.

No model SDK runs in the API process. No user-supplied URL, public parser,
redirect, proxy, source filename, or document content is logged or forwarded
to a model provider. Protocol v1 uses top-left PDF points / image pixels.
"""
from __future__ import annotations

import asyncio
import io
import ipaddress
import json
import math
import os
import ssl
import time
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.parse import urlsplit

MAX_INPUT_BYTES = 10 * 1024 * 1024
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_IMAGE_PIXELS = 12_000_000
MAX_OCR_PAGES = 4
MAX_ITEMS = 1500
MAX_TEXT = 120_000
ISSUE_MESSAGES = {
    'ocr_not_configured': '尚未配置私有 OCR 服务；原图已保留，图片文字等待识别。',
    'ocr_configuration_invalid': '私有 OCR 服务配置不完整或地址不符合要求；原图已保留。',
    'ocr_unavailable': '私有 OCR 服务暂时不可用；原图已保留，图片文字等待识别。',
    'ocr_timeout': '本次图片识别时间已用完；剩余原图已保留，等待后续识别。',
    'ocr_budget_exceeded': '本次图片识别数量已达上限；剩余原图已保留，等待后续识别。',
    'ocr_invalid_response': '图片识别结果不完整或格式不符；请对照保留的原图检查。',
    'ocr_input_limit': '图片或页面超出本次 OCR 的资源上限；原件已保留。',
    'ocr_no_text': '图片识别未返回可审查文字；请对照保留的原图检查。',
    'ocr_partial': '图片仅完成部分识别；未识别内容仍需对照原图检查。',
    'ocr_review_required': '图片文字由 OCR 识别，请对照原图核对文字、数字及表格关系。',
}


def _issue(code: str, **where: Any) -> dict[str, Any]:
    return {'code': code, 'message': ISSUE_MESSAGES[code], **where}


def _timeout_seconds() -> float:
    try:
        value = float(os.getenv('LEGAL_DOCUMENT_PARSER_TIMEOUT_SECONDS', '20'))
        return max(1.0, min(value, 60.0)) if math.isfinite(value) else 20.0
    except ValueError:
        return 20.0


@dataclass
class OCRBudget:
    """Create once per upload and share across every image/page request."""

    seconds: float = field(default_factory=_timeout_seconds)
    max_requests: int = MAX_OCR_PAGES
    started: float = field(default_factory=time.monotonic)
    requests: int = 0

    def remaining(self) -> float:
        return max(0.0, min(self.seconds, 60.0) - (time.monotonic() - self.started))

    def reserve(self) -> str | None:
        if self.remaining() <= 0:
            return 'ocr_timeout'
        if self.requests >= min(self.max_requests, MAX_OCR_PAGES):
            return 'ocr_budget_exceeded'
        self.requests += 1
        return None


def _configuration() -> tuple[str, str, str | None]:
    url = os.getenv('LEGAL_DOCUMENT_PARSER_URL', '').strip().rstrip('/')
    token = os.getenv('LEGAL_DOCUMENT_PARSER_TOKEN', '').strip()
    if not url and not token:
        return '', '', 'ocr_not_configured'
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or '').lower().rstrip('.')
        if (not token or len(token) < 32 or any(ord(c) < 33 or ord(c) > 126 for c in token)
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.path not in ('', '/') or not host
                or parsed.scheme not in ('https', 'http')):
            raise ValueError
        _ = parsed.port
        loopback = host == 'localhost'
        private = host.endswith('.internal')
        try:
            ip = ipaddress.ip_address(host)
            loopback = ip.is_loopback
            networks = ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', 'fc00::/7')
            private = any(ip in ipaddress.ip_network(net) for net in networks)
        except ValueError:
            pass
        if not (loopback or private) or (not loopback and parsed.scheme != 'https'):
            raise ValueError
    except (ValueError, TypeError):
        return '', '', 'ocr_configuration_invalid'
    return url, token, None


def ocr_status() -> dict[str, Any]:
    """Configuration status only; does not claim remote readiness or expose secrets."""
    _, _, code = _configuration()
    return {
        'configured': code is None,
        'state': 'configured' if code is None else code,
        'message': '已配置私有 OCR 服务；按需识别并保留原图。' if code is None else ISSUE_MESSAGES[code],
    }


def _pending(code: str) -> dict[str, Any]:
    return {'status': 'pending', 'pages': [], 'blocks': [], 'issues': [_issue(code)]}


def _box(value: Any, width: float, height: float) -> list[float] | None:
    if value is None:
        return None
    if (not isinstance(value, list) or len(value) != 4
            or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in value)):
        raise ValueError
    x0, y0, x1, y1 = map(float, value)
    if x0 < -1 or y0 < -1 or x1 > width + 1 or y1 > height + 1 or x1 <= x0 or y1 <= y0:
        raise ValueError
    return [max(0.0, x0), max(0.0, y0), min(width, x1), min(height, y1)]


def _validate_result(raw: Any, expected_pages: int) -> dict[str, Any]:
    """Allowlist the worker contract, including text size, geometry and cell spans."""
    if (not isinstance(raw, dict) or raw.get('version') != 1
            or raw.get('status') not in ('complete', 'partial') or not isinstance(raw.get('pages'), list)
            or len(raw['pages']) > expected_pages):
        raise ValueError
    pages = []
    seen = set()
    total_text = total_items = 0
    for page in raw['pages']:
        if not isinstance(page, dict):
            raise ValueError
        number = page.get('number')
        width, height = page.get('width'), page.get('height')
        if (type(number) is not int or number < 1 or number > expected_pages or number in seen
                or any(isinstance(v, bool) or not isinstance(v, (int, float))
                       or not math.isfinite(v) or v <= 0 or v > 30000 for v in (width, height))
                or not isinstance(page.get('items'), list)):
            raise ValueError
        seen.add(number)
        items = []
        for item in page['items']:
            total_items += 1
            if not isinstance(item, dict) or total_items > MAX_ITEMS:
                raise ValueError
            kind = item.get('type')
            bbox = _box(item.get('bbox'), width, height)
            if kind == 'paragraph':
                value = item.get('text')
                if not isinstance(value, str):
                    raise ValueError
                total_text += len(value)
                if value.strip():
                    items.append({'type': kind, 'text': value.strip(), 'bbox': bbox})
            elif kind == 'table':
                if not isinstance(item.get('cells'), list) or len(item['cells']) > MAX_ITEMS:
                    raise ValueError
                cells, occupied = [], set()
                for cell in item['cells']:
                    total_items += 1
                    if not isinstance(cell, dict) or total_items > MAX_ITEMS:
                        raise ValueError
                    coords = [cell.get(k) for k in ('row', 'col', 'row_span', 'col_span')]
                    if (any(type(v) is not int for v in coords)
                            or min(coords[:2]) < 0 or max(coords[:2]) > 500
                            or min(coords[2:]) < 1 or max(coords[2:]) > 100
                            or coords[2] * coords[3] > MAX_ITEMS or not isinstance(cell.get('text'), str)):
                        raise ValueError
                    row, col, row_span, col_span = coords
                    positions = {(r, c) for r in range(row, row + row_span) for c in range(col, col + col_span)}
                    if occupied.intersection(positions) or len(occupied) + len(positions) > MAX_ITEMS:
                        raise ValueError
                    occupied.update(positions)
                    total_text += len(cell['text'])
                    cells.append({'row': row, 'col': col, 'row_span': row_span, 'col_span': col_span,
                                  'text': cell['text'].strip(), 'bbox': _box(cell.get('bbox'), width, height),
                                  'header': bool(cell.get('header', False))})
                if cells:
                    items.append({'type': kind, 'bbox': bbox, 'cells': cells})
            elif kind == 'image':
                items.append({'type': kind, 'bbox': bbox})
            else:
                raise ValueError
            if total_text > MAX_TEXT:
                raise ValueError
        pages.append({'number': number, 'width': float(width), 'height': float(height), 'items': items})
    partial = raw['status'] == 'partial' or len(pages) != expected_pages
    return {'status': 'partial' if partial else 'complete', 'pages': pages,
            'issues': [_issue('ocr_partial')] if partial else []}


def _request(data: bytes, media_type: str, expected_pages: int, budget: OCRBudget) -> dict[str, Any]:
    url, token, code = _configuration()
    if code:
        return _pending(code)
    if not data or len(data) > MAX_INPUT_BYTES:
        return _pending('ocr_input_limit')
    if code := budget.reserve():
        return _pending(code)
    import httpx
    try:
        ca_file = os.getenv('LEGAL_DOCUMENT_PARSER_CA_FILE', '').strip()
        verify = ssl.create_default_context(cafile=ca_file) if ca_file else True
        async def fetch():
            # HTTPX phase timeouts alone are not a total deadline: a slow
            # response can keep each read alive. Cancel the whole operation.
            async with asyncio.timeout(budget.remaining()):
                remaining = budget.remaining()
                timeout = httpx.Timeout(remaining, connect=min(remaining, 3.0))
                async with httpx.AsyncClient(timeout=timeout, follow_redirects=False,
                                            trust_env=False, verify=verify) as client:
                    async with client.stream('POST', url + '/v1/parse', content=data,
                                             headers={'Authorization': 'Bearer ' + token, 'Content-Type': media_type,
                                                      'X-Parser-Protocol': '1'}) as response:
                        if response.status_code != 200:
                            code = {413: 'ocr_input_limit', 504: 'ocr_timeout'}.get(response.status_code, 'ocr_unavailable')
                            return _pending(code)
                        content = bytearray()
                        async for chunk in response.aiter_bytes():
                            content.extend(chunk)
                            if len(content) > MAX_RESPONSE_BYTES:
                                return _pending('ocr_invalid_response')
                return _validate_result(json.loads(content), expected_pages)
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            result = asyncio.run(fetch())
        else:
            # Public helpers are synchronous. FastAPI runs the upload handler
            # in a thread; this branch also permits explicit async callers.
            with ThreadPoolExecutor(max_workers=1, thread_name_prefix='private-parser') as pool:
                result = pool.submit(lambda: asyncio.run(fetch())).result()
        has_text = any(item.get('text') or any(cell.get('text') for cell in item.get('cells', []))
                       for page in result['pages'] for item in page['items'])
        if has_text:
            result['issues'].append(_issue('ocr_review_required'))
        elif result['status'] != 'pending':
            result['status'] = 'partial'
            result['issues'].append(_issue('ocr_no_text'))
        return result
    except (TimeoutError, httpx.TimeoutException):
        return _pending('ocr_timeout')
    except (httpx.HTTPError, OSError):
        return _pending('ocr_unavailable')
    except (ValueError, TypeError, KeyError, OverflowError):
        return _pending('ocr_invalid_response')


def recognize_image(data: bytes, media_type: str, *, budget: OCRBudget | None = None) -> dict[str, Any]:
    """OCR one selected image; returned boxes use original image pixels, top-left.

    The caller owns the image node and asset. Attach these blocks to that node,
    never both to it and the document body. Decorative-image selection is the
    caller's responsibility; skipped images still need a coverage issue.
    """
    if media_type not in ('image/png', 'image/jpeg', 'image/tiff', 'image/webp'):
        return _pending('ocr_input_limit')
    try:
        from PIL import Image
        with Image.open(io.BytesIO(data)) as picture:
            width, height = picture.size
            if width * height > MAX_IMAGE_PIXELS or getattr(picture, 'n_frames', 1) != 1:
                return _pending('ocr_input_limit')
    except (OSError, ValueError, Image.DecompressionBombError):
        return _pending('ocr_input_limit')
    result = _request(data, media_type, 1, budget or OCRBudget())
    blocks = []
    for page in result.get('pages', []):
        sx, sy = width / page['width'], height / page['height']
        table_number = 0
        for item in page['items']:
            if item['type'] == 'table':
                table_number += 1
            values = item['cells'] if item['type'] == 'table' else [item]
            for cell in values:
                if not cell.get('text'):
                    continue
                bbox = cell.get('bbox') or item.get('bbox')
                bbox = [bbox[0] * sx, bbox[1] * sy, bbox[2] * sx, bbox[3] * sy] if bbox else None
                block = {'text': cell['text'], 'bbox': bbox, 'kind': 'ocr'}
                if item['type'] == 'table':
                    table_id = f'table-{table_number}'
                    block['table'] = {'id': table_id, 'cell_id': f'{table_id}-r{cell["row"]}-c{cell["col"]}',
                                      'header': bool(cell.get('header', False)),
                                      **{k: cell[k] for k in ('row', 'col', 'row_span', 'col_span')}}
                blocks.append(block)
    if not blocks and result['status'] != 'pending' and not any(i['code'] == 'ocr_no_text' for i in result['issues']):
        result['status'] = 'partial'
        result['issues'].append(_issue('ocr_no_text'))
    return {**result, 'blocks': blocks, 'width': width, 'height': height}


def recognize_pdf_pages(data: bytes, pages: list[int], *, budget: OCRBudget | None = None) -> dict[str, Any]:
    """Send only selected visible pages to the private worker, in one bounded call.

    Returned geometry is in the rotated, zero-origin MediaBox coordinate
    system used by pdf_structure, even for original CropBoxes / rotated pages.
    """
    _, _, code = _configuration()
    if code:
        return _pending(code)
    if (not pages or len(pages) > MAX_OCR_PAGES or len(set(pages)) != len(pages)
            or any(type(page) is not int or page < 1 for page in pages)):
        return _pending('ocr_input_limit')
    try:
        from legal.pdf_structure import prepare_pdf_for_ocr
        selected, geometry = prepare_pdf_for_ocr(data, pages)
    except (ValueError, OSError):
        return _pending('ocr_input_limit')
    result = _request(selected, 'application/pdf', len(pages), budget or OCRBudget())
    for page in result.get('pages', []):
        original = geometry[page['number'] - 1]
        x0, y0, x1, y1 = original['crop_bbox']
        sx, sy = (x1 - x0) / page['width'], (y1 - y0) / page['height']
        for item in page['items']:
            for obj in [item, *item.get('cells', [])]:
                if bbox := obj.get('bbox'):
                    obj['bbox'] = [x0 + bbox[0] * sx, y0 + bbox[1] * sy,
                                   x0 + bbox[2] * sx, y0 + bbox[3] * sy]
        page.update(number=original['number'], width=original['width'], height=original['height'])
    return result
