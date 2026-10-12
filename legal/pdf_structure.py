"""Local PDF layout, ruled tables, source geometry and targeted private OCR.

The source bytes are immutable. All boxes use points from the top-left of the
rotated MediaBox, normalized to (0, 0). Rendering and annotated export must
apply pypdf's transfer_rotation_to_content() even when the original rotation
is zero (it also normalizes a nonzero MediaBox origin).
"""
from __future__ import annotations

import io
import math
import re
import statistics
import threading
from typing import Any

from legal import document_ocr

MAX_BYTES = 10 * 1024 * 1024
MAX_PAGES = 100
MAX_PAGE_CHARS = 60_000
MAX_PAGE_EDGES = 1000
MAX_TABLE_INTERSECTIONS = 20_000
MAX_ASSETS = 200
MAX_RENDER_PIXELS = 4_000_000
MAX_RENDER_SIDE = 3000
MAX_EMBEDDED_IMAGE_PIXELS = 12_000_000
_PDFIUM_RENDER_LOCK = threading.Lock()


def _reader(data: bytes):
    from pypdf import PdfReader
    if not data or len(data) > MAX_BYTES:
        raise ValueError('请上传不超过 10 MB 的非空 PDF。')
    if not data.startswith(b'%PDF-'):
        raise ValueError('PDF 文件头无效，请检查文件是否完整。')
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise ValueError('请先移除 PDF 密码保护。')
        if len(reader.pages) > MAX_PAGES:
            raise ValueError('最多接收 100 页 PDF，请按合同拆分。')
        if not reader.pages:
            raise ValueError('PDF 中没有可显示页面。')
        return reader
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError('PDF 文件无法读取，请检查文件是否完整。') from exc


def _normalize_page(page: Any, number: int) -> dict[str, Any]:
    page.transfer_rotation_to_content()
    width, height = float(page.mediabox.width), float(page.mediabox.height)
    if not all(math.isfinite(v) and 0 < v <= 30000 for v in (width, height)):
        raise ValueError('PDF 页面尺寸超出支持范围。')
    crop = page.cropbox
    bbox = [max(0.0, float(crop.left)), max(0.0, height - float(crop.top)),
            min(width, float(crop.right)), min(height, height - float(crop.bottom))]
    if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
        raise ValueError('PDF 页面裁切范围无效。')
    return {'number': number, 'width': width, 'height': height,
            'crop_bbox': [round(v, 4) for v in bbox]}


def prepare_pdf_for_ocr(data: bytes, pages: list[int]) -> tuple[bytes, list[dict[str, Any]]]:
    """Copy selected visible pages, without unrelated pages or document metadata."""
    from pypdf import PdfWriter
    from pypdf.generic import RectangleObject
    reader, writer = _reader(data), PdfWriter()
    geometry = []
    for number in pages:
        if number < 1 or number > len(reader.pages):
            raise ValueError('PDF 页码无效。')
        page = writer.add_page(reader.pages[number - 1])
        info = _normalize_page(page, number)
        geometry.append(info)
        x0, y0, x1, y1 = info['crop_bbox']
        page.mediabox = RectangleObject([x0, info['height'] - y1, x1, info['height'] - y0])
        page.cropbox = RectangleObject(page.mediabox)
        page.transfer_rotation_to_content()
        # Annotations/attachments are not needed for OCR and must not be copied.
        if '/Annots' in page:
            del page['/Annots']
    stream = io.BytesIO()
    writer.write(stream)
    return stream.getvalue(), geometry


def render_pdf_asset(data: bytes, asset: dict[str, Any], *, max_pixels: int = MAX_RENDER_PIXELS) -> tuple[bytes, str]:
    """Lazily rasterize only the selected source region, with a hard pixel bound."""
    # PDFium is not thread-safe, including use of independent PDF documents.
    with _PDFIUM_RENDER_LOCK:
        return _render_pdf_asset(data, asset, max_pixels=max_pixels)


def _render_pdf_asset(data: bytes, asset: dict[str, Any], *, max_pixels: int) -> tuple[bytes, str]:
    import pypdfium2
    from pypdf import PdfWriter
    from pypdf.generic import RectangleObject
    reader = _reader(data)
    number = asset.get('page')
    if type(number) is not int or not 1 <= number <= len(reader.pages):
        raise ValueError('图片页码无效。')
    writer = PdfWriter()
    page = writer.add_page(reader.pages[number - 1])
    _check_embedded_images(page)
    info = _normalize_page(page, number)
    width, height = info['width'], info['height']
    bbox = document_ocr._box(asset.get('bbox') or info['crop_bbox'], width, height)
    if bbox is None:
        raise ValueError('图片范围无效。')
    x0, y0, x1, y1 = bbox
    limit = max(1, min(int(max_pixels), MAX_RENDER_PIXELS))
    scale = min(2.0, math.sqrt(limit / ((x1 - x0) * (y1 - y0))),
                MAX_RENDER_SIDE / max(x1 - x0, y1 - y0)) * .999
    # PDFium normally honors CropBox. Render against MediaBox, then crop in
    # device space before allocating the bitmap, using the exact same origin.
    page.cropbox = RectangleObject(page.mediabox)
    stream = io.BytesIO()
    writer.write(stream)
    with pypdfium2.PdfDocument(stream.getvalue()) as pdf:
        render_page = pdf[0]
        try:
            def allocate(w, h, **kwargs):
                # Check the exact rounded dimensions before PDFium allocates,
                # not just after generating an oversized bitmap.
                if w * h > limit or max(w, h) > MAX_RENDER_SIDE:
                    raise ValueError('图片范围超出渲染资源上限。')
                return pypdfium2.PdfBitmap.new_native(w, h, **kwargs)
            bitmap = render_page.render(scale=scale, crop=(x0, height - y1, width - x1, y0),
                                        bitmap_maker=allocate, limit_image_cache=True)
            try:
                picture = bitmap.to_pil()
                try:
                    if picture.width * picture.height > limit:
                        factor = math.sqrt(limit / (picture.width * picture.height))
                        resized = picture.resize((max(1, int(picture.width * factor)),
                                                  max(1, int(picture.height * factor))))
                        picture.close()
                        picture = resized
                    out = io.BytesIO()
                    picture.save(out, format='PNG')
                    return out.getvalue(), 'image/png'
                finally:
                    picture.close()
            finally:
                bitmap.close()
        finally:
            render_page.close()


def _check_embedded_images(page: Any) -> None:
    """Do not decode a huge compressed XObject merely to make a small preview."""
    seen, total = set(), 0
    def inspect(resources, depth=0):
        nonlocal total
        if depth > 10:
            raise ValueError('PDF 图片嵌套超出预览资源上限。')
        resources = resources.get_object() if hasattr(resources, 'get_object') else resources
        objects = resources.get('/XObject', {}) if resources else {}
        objects = objects.get_object() if hasattr(objects, 'get_object') else objects
        for reference in objects.values():
            identity = (getattr(reference, 'idnum', None), getattr(reference, 'generation', None))
            if identity != (None, None) and identity in seen:
                continue
            seen.add(identity)
            if len(seen) > 2000:
                raise ValueError('PDF 图片对象超出预览资源上限。')
            obj = reference.get_object()
            if obj.get('/Subtype') == '/Image':
                pixels = int(obj.get('/Width', 0)) * int(obj.get('/Height', 0))
                total += max(0, pixels)
                if pixels > MAX_EMBEDDED_IMAGE_PIXELS or total > MAX_EMBEDDED_IMAGE_PIXELS * 2:
                    raise ValueError('PDF 内嵌图片超出预览资源上限，请查看原始 PDF。')
            elif obj.get('/Subtype') == '/Form':
                inspect(obj.get('/Resources'), depth + 1)
    inspect(page.get('/Resources'))


def _bbox(values: list[dict[str, Any]]) -> list[float]:
    return [min(v['bbox'][0] for v in values), min(v['bbox'][1] for v in values),
            max(v['bbox'][2] for v in values), max(v['bbox'][3] for v in values)]


def _inside(word: dict[str, Any], box: list[float] | tuple) -> bool:
    x, y = (word['x0'] + word['x1']) / 2, (word['top'] + word['bottom']) / 2
    return box[0] <= x < box[2] and box[1] <= y < box[3]


def _join_text(words: list[dict[str, Any]]) -> str:
    text = ''
    for word in sorted(words, key=lambda w: w['x0']):
        value = word['text']
        # PDF extractors often split every CJK glyph into a separate word.
        if text and not (re.search(r'[\u3400-\u9fff]$', text) and re.match(r'[\u3400-\u9fff，。；：、）]', value)):
            text += ' '
        text += value
    return text.strip()


def _lines(words: list[dict[str, Any]], *, split_columns: bool = True) -> list[dict[str, Any]]:
    bands: list[list[dict[str, Any]]] = []
    for word in sorted(words, key=lambda w: (w['top'], w['x0'])):
        if bands and abs(word['top'] - statistics.median(w['top'] for w in bands[-1])) <= 3:
            bands[-1].append(word)
        else:
            bands.append([word])
    lines = []
    for band in bands:
        groups: list[list[dict[str, Any]]] = [[]]
        for word in sorted(band, key=lambda w: w['x0']):
            threshold = max(22, (word['bottom'] - word['top']) * 2)
            if split_columns and groups[-1] and word['x0'] - groups[-1][-1]['x1'] > threshold:
                groups.append([])
            groups[-1].append(word)
        for group in groups:
            lines.append({'type': 'paragraph', 'text': _join_text(group),
                          'bbox': [min(w['x0'] for w in group), min(w['top'] for w in group),
                                   max(w['x1'] for w in group), max(w['bottom'] for w in group)]})
    return lines


def _reading_order(items: list[dict[str, Any]], depth: int = 0) -> list[dict[str, Any]]:
    """Column order with spanning headings/tables separating vertical bands.

    This geometric fast path does not claim semantic reading-order certainty.
    Unlike sorting (top, left), it completes the left column before the right.
    """
    if len(items) < 4 or depth > 8:
        return sorted(items, key=lambda item: (item['bbox'][1], item['bbox'][0]))
    left, _, right, _ = _bbox(items)
    width = right - left
    points = sorted({v for item in items for v in (item['bbox'][0], item['bbox'][2])})
    candidates = [(a + b) / 2 for a, b in zip(points, points[1:])
                  if b - a >= 12 and left + width * .2 < (a + b) / 2 < right - width * .2]
    best = None
    for cut in candidates:
        before = [i for i in items if i['bbox'][2] <= cut]
        after = [i for i in items if i['bbox'][0] >= cut]
        spanning = [i for i in items if i not in before and i not in after]
        if len(before) < 2 or len(after) < 2 or len(spanning) > max(2, len(items) * .2):
            continue
        a, b = _bbox(before), _bbox(after)
        if min(a[3], b[3]) - max(a[1], b[1]) < 12:
            continue
        score = (min(len(before), len(after)), -len(spanning), b[0] - a[2])
        if best is None or score > best[0]:
            best = (score, cut, spanning)
    if best:
        _, cut, spanning = best
        # Full-width elements remain between the column bands they separate.
        remaining = [i for i in items if i not in spanning]
        ordered = []
        for boundary in sorted(spanning, key=lambda i: i['bbox'][1]):
            band = [i for i in remaining if i['bbox'][1] < boundary['bbox'][1]]
            remaining = [i for i in remaining if i not in band]
            ordered += _reading_order([i for i in band if i['bbox'][2] <= cut], depth + 1)
            ordered += _reading_order([i for i in band if i['bbox'][0] >= cut], depth + 1)
            ordered.append(boundary)
        ordered += _reading_order([i for i in remaining if i['bbox'][2] <= cut], depth + 1)
        ordered += _reading_order([i for i in remaining if i['bbox'][0] >= cut], depth + 1)
        return ordered
    return sorted(items, key=lambda item: (item['bbox'][1], item['bbox'][0]))


def _paragraphs(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for item in _reading_order(items):
        if result and item['type'] == result[-1]['type'] == 'paragraph':
            prev = result[-1]
            a, b = prev['bbox'], item['bbox']
            height = b[3] - b[1]
            starts_clause = bool(re.match(r'^(?:第[\u4e00-\u9fff\d]+[条章节]|\d+[.、）)]|[（(]\d+[)）])', item['text']))
            if (not starts_clause and -1 <= b[1] - a[3] <= max(5, height * .65)
                    and abs(b[0] - a[0]) <= max(15, height * 1.5)
                    and not re.search(r'[。；;：:]$', prev['text'])):
                prev['text'] += '\n' + item['text']
                prev['bbox'] = _bbox([prev, item])
                continue
        result.append(dict(item))
    return result


_FIELD_LABEL = re.compile(
    r'^(?:序号|编号|项目|名称|品名|金额|日期|数量|单价|总价|甲方|乙方|丙方|供应商|地址|账户|账号|'
    r'开户行|银行|收款方|付款方|币种|税率|姓名|公司|签署方|备注|规格|单位|'
    r'身份证号码|证件号码|身份证号|手机号|联系电话|电话号码|电话|邮箱|电子邮箱|法定代表人|'
    r'联系人|收款账户|收款账号|联系地址|通讯地址|账户名称|户名|统一社会信用代码|'
    r'no\.?|id|item|description|amount|date|quantity|qty|price|total|party|name|account|address|unit|currency)$', re.I)


def _borderless_tables(words: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    """Infer only repeated short, aligned rows with field/header evidence.

    Two prose columns are not a table merely because their left edges align.
    Ambiguous short-column layouts get a coverage notice instead of invented
    cell relationships. The original text remains available in either case.
    """
    lines = _lines(words)
    bands: list[list[dict[str, Any]]] = []
    for line in sorted(lines, key=lambda v: (v['bbox'][1], v['bbox'][0])):
        if bands and abs(line['bbox'][1] - bands[-1][0]['bbox'][1]) <= 3:
            bands[-1].append(line)
        else:
            bands.append([line])
    runs: list[list[list[dict[str, Any]]]] = []
    for band in bands:
        band.sort(key=lambda v: v['bbox'][0])
        eligible = (2 <= len(band) <= 6 and all(len(v['text']) <= 70 for v in band)
                    and not any(re.search(r'[。！？.!?]$', v['text']) for v in band))
        if not eligible:
            runs.append([])
            continue
        if (runs and runs[-1] and len(runs[-1][-1]) == len(band)
                and band[0]['bbox'][1] - runs[-1][-1][0]['bbox'][3] <= 35
                and all(abs(a['bbox'][0] - b['bbox'][0]) <= 5 for a, b in zip(runs[-1][0], band))):
            runs[-1].append(band)
        else:
            runs.append([band])
    result, uncertain = [], False
    for run in runs:
        if len(run) < 3:
            continue
        labels = lambda row: sum(bool(_FIELD_LABEL.fullmatch(v['text'].strip(' ：:'))) for v in row)
        header = labels(run[0]) >= 2
        field_column = sum(bool(_FIELD_LABEL.fullmatch(row[0]['text'].strip(' ：:'))) for row in run) >= 2
        if not header and not field_column:
            uncertain = True
            continue
        cols = len(run[0])
        xs = [max(0, min(row[0]['bbox'][0] for row in run) - 1)]
        for col in range(1, cols):
            xs.append((max(row[col - 1]['bbox'][2] for row in run) + min(row[col]['bbox'][0] for row in run)) / 2)
        xs.append(max(row[-1]['bbox'][2] for row in run) + 1)
        ys = [max(0, run[0][0]['bbox'][1] - 1)]
        for prev, row in zip(run, run[1:]):
            ys.append((max(v['bbox'][3] for v in prev) + min(v['bbox'][1] for v in row)) / 2)
        ys.append(max(v['bbox'][3] for v in run[-1]) + 1)
        cells = [{'row': r, 'col': c, 'row_span': 1, 'col_span': 1, 'header': header and r == 0,
                  'text': line['text'], 'bbox': [xs[c], ys[r], xs[c + 1], ys[r + 1]]}
                 for r, row in enumerate(run) for c, line in enumerate(row)]
        result.append({'type': 'table', 'bbox': [xs[0], ys[0], xs[-1], ys[-1]], 'cells': cells})
    return result, uncertain


def _native_page(page: Any, info: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    issues: list[str] = []
    if len(page.chars) > MAX_PAGE_CHARS:
        return [], [], ['pdf_page_text_limit']
    page = page.dedupe_chars(tolerance=1)
    words = [w for w in page.extract_words(x_tolerance=2, y_tolerance=3, use_text_flow=False)
             if w.get('text', '').strip() and _inside(w, info['crop_bbox'])]
    bad = [w for w in words if '(cid:' in w['text'] or w['text'].count('\ufffd') > len(w['text']) * .2]
    if bad:
        words = [w for w in words if w not in bad]
        issues.append('pdf_text_unreliable')
    tables = []
    try:
        edges = page.edges
        horizontal = sum(edge.get('orientation') == 'h' for edge in edges)
        vertical = sum(edge.get('orientation') == 'v' for edge in edges)
        eligible = len(edges) <= MAX_PAGE_EDGES and horizontal * vertical <= MAX_TABLE_INTERSECTIONS
        candidates = page.find_tables(table_settings={'vertical_strategy': 'lines', 'horizontal_strategy': 'lines'}) if eligible else []
        if not eligible:
            issues.append('pdf_table_geometry_limit')
    except Exception:
        candidates = []
        issues.append('pdf_table_unavailable')
    if candidates:
        for table in candidates:
            raw_cells = [c for c in dict.fromkeys(table.cells) if c[2] - c[0] >= 1 and c[3] - c[1] >= 1]
            if len(raw_cells) < 2 or len(raw_cells) > 1000:
                continue
            xs = sorted({round(v, 2) for cell in raw_cells for v in (cell[0], cell[2])})
            ys = sorted({round(v, 2) for cell in raw_cells for v in (cell[1], cell[3])})
            cells = []
            for cell in sorted(raw_cells, key=lambda c: (c[1], c[0])):
                row, col = ys.index(round(cell[1], 2)), xs.index(round(cell[0], 2))
                content = _lines([w for w in words if _inside(w, cell)], split_columns=False)
                cells.append({'row': row, 'col': col,
                              'row_span': ys.index(round(cell[3], 2)) - row,
                              'col_span': xs.index(round(cell[2], 2)) - col,
                              'text': '\n'.join(line['text'] for line in content), 'bbox': list(cell)})
            if any(cell['text'] for cell in cells):
                header = sum(bool(_FIELD_LABEL.fullmatch(c['text'].strip(' ：:'))) for c in cells if c['row'] == 0) >= 2
                for cell in cells:
                    cell['header'] = header and cell['row'] == 0
                tables.append({'type': 'table', 'bbox': list(table.bbox), 'cells': cells})
    covered = [cell['bbox'] for table in tables for cell in table['cells']]
    remaining = [w for w in words if not any(_inside(w, box) for box in covered)]
    inferred, uncertain = _borderless_tables(remaining)
    tables.extend(inferred)
    if uncertain:
        issues.append('pdf_table_uncertain')
    remaining = [w for w in remaining if not any(_inside(w, table['bbox']) for table in inferred)]
    items = _paragraphs([*_lines(remaining), *tables])
    images = []
    crop = info['crop_bbox']
    for raw in page.images:
        bbox = [max(crop[0], float(raw['x0'])), max(crop[1], float(raw['top'])),
                min(crop[2], float(raw['x1'])), min(crop[3], float(raw['bottom']))]
        if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
            continue
        if any(all(abs(a - b) < 1 for a, b in zip(bbox, image['bbox'])) for image in images):
            continue
        inside = [w for w in words if _inside(w, bbox)]
        native_coverage = (sum(len(w['text']) for w in inside) >= 120
                           and max((w['bottom'] for w in inside), default=0)
                           - min((w['top'] for w in inside), default=0) >= (bbox[3] - bbox[1]) * .4)
        sizeable = bbox[2] - bbox[0] >= 80 and bbox[3] - bbox[1] >= 30
        images.append({'type': 'image', 'bbox': bbox, 'ocr_candidate': sizeable and not native_coverage})
    return items, images, issues


def parse_pdf(data: bytes) -> dict[str, Any]:
    import pdfplumber
    from pypdf import PdfWriter
    budget = document_ocr.OCRBudget()
    reader, writer = _reader(data), PdfWriter()
    pages = []
    for number, page in enumerate(reader.pages, 1):
        pages.append(_normalize_page(writer.add_page(page), number))
    stream = io.BytesIO()
    writer.write(stream)
    document: dict[str, Any] = {'version': 1, 'source': 'pdf', 'body': [], 'pages': pages, 'issues': []}
    assets: list[dict[str, Any]] = []
    blocks: list[dict[str, Any]] = []
    page_items: dict[int, list[dict[str, Any]]] = {}
    scan_pages = []
    image_candidates = []

    def issue(code: str, message: str, **where: Any):
        document['issues'].append({'id': f'issue{len(document["issues"]) + 1}',
                                   'code': code, 'message': message, **where})

    def add_asset(number: int, bbox: list[float], **extra: Any) -> dict[str, Any] | None:
        if len(assets) >= MAX_ASSETS:
            return None
        asset = {'id': f'pdf-image-{len(assets) + 1}', 'media_type': 'image/png', 'page': number,
                 'bbox': [round(v, 4) for v in bbox], **extra}
        assets.append(asset)
        return asset

    with pdfplumber.open(io.BytesIO(stream.getvalue())) as pdf:
        for info, page in zip(pages, pdf.pages):
            number = info['number']
            try:
                native, images, codes = _native_page(page, info)
                for code in codes:
                    messages = {
                        'pdf_table_uncertain': f'第 {number} 页存在可能的无边框表格；文字已保留，行列对应关系需要对照原页检查。',
                        'pdf_table_unavailable': f'第 {number} 页表格结构未完整解析；可读取文字已保留，请对照原页核对行列。',
                        'pdf_text_unreliable': f'第 {number} 页部分文字编码无法可靠读取；原页已保留，遗漏文字需要 OCR 或人工核对。',
                    }
                    message = messages.get(code, f'第 {number} 页部分内容超出本地解析资源上限；已保留原页供检查。')
                    issue(code, message, page=number)
            except Exception:
                native, images = [], []
                issue('pdf_layout_unavailable', f'第 {number} 页本地结构解析未完成；已保留原页。', page=number)
            finally:
                page.close()
            page_items[number] = native
            # Empty and image-only pages are never represented as reviewed text.
            if not any(item.get('text') or any(c.get('text') for c in item.get('cells', [])) for item in native):
                asset = add_asset(number, info['crop_bbox'])
                if asset:
                    native.append({'type': 'image', 'bbox': asset['bbox'], 'asset_id': asset['id']})
                scan_pages.append(number)
                continue
            for image in images:
                asset = add_asset(number, image['bbox'])
                if asset is None:
                    issue('pdf_image_limit', f'第 {number} 页图片较多，部分图片请在原件中检查。', page=number)
                    break
                node = {'type': 'image', 'bbox': image['bbox'], 'asset_id': asset['id']}
                native.append(node)
                if image['ocr_candidate']:
                    image_candidates.append((node, asset))
                else:
                    issue('pdf_image_not_reviewed', '此图片未单独进行 OCR；图片及签章等视觉内容需要对照原件检查。',
                          page=number, asset_id=asset['id'], bbox=asset['bbox'])

    selected = scan_pages[:document_ocr.MAX_OCR_PAGES]
    if selected:
        result = document_ocr.recognize_pdf_pages(data, selected, budget=budget)
        recognized = set()
        for page in result.get('pages', []):
            content = [item for item in page['items'] if item.get('text') or any(c.get('text') for c in item.get('cells', []))]
            if content:
                recognized.add(page['number'])
                for item in content:
                    item['ocr'] = True
                    item['bbox'] = item.get('bbox') or pages[page['number'] - 1]['crop_bbox']
                # Source page preview stays available; text/table content occurs once.
                page_items[page['number']] = [*page_items[page['number']], *content]
        for number in scan_pages:
            if number not in recognized:
                code = (result.get('issues') or [{}])[0].get('code', 'ocr_no_text') if number in selected else 'ocr_budget_exceeded'
                issue('pdf_ocr_pending', f'第 {number} 页尚无可审查文字，已保留原页，等待 OCR 或人工核对。', page=number)
                issue(code, document_ocr.ISSUE_MESSAGES.get(code, document_ocr.ISSUE_MESSAGES['ocr_no_text']), page=number)
            else:
                for finding in result['issues']:
                    issue(finding['code'], finding['message'], page=number)

    # Mixed pages: OCR only the selected image region, never the whole native
    # text layer again. Missing/failed regions remain explicit in coverage.
    for node, asset in image_candidates:
        state = document_ocr.ocr_status()
        if not state['configured']:
            result = {'status': 'pending', 'blocks': [], 'issues': [document_ocr._issue(state['state'])]}
        elif budget.remaining() <= 0 or budget.requests >= budget.max_requests:
            result = document_ocr._pending('ocr_budget_exceeded' if budget.requests >= budget.max_requests else 'ocr_timeout')
        else:
            try:
                raw, media = render_pdf_asset(data, asset)
                result = document_ocr.recognize_image(raw, media, budget=budget)
            except (ValueError, OSError):
                result = document_ocr._pending('ocr_input_limit')
        x0, y0, x1, y1 = asset['bbox']
        sx, sy = (x1 - x0) / result.get('width', 1), (y1 - y0) / result.get('height', 1)
        node['ocr_blocks'] = []
        native_text = '\n'.join(item.get('text', '') for item in page_items[asset['page']] if item['type'] == 'paragraph')
        for block in result.get('blocks', []):
            # An existing hidden OCR text layer must not duplicate visible text.
            if re.sub(r'\s+', '', block['text']) in re.sub(r'\s+', '', native_text):
                continue
            bbox = block.get('bbox')
            if bbox:
                bbox = [x0 + bbox[0] * sx, y0 + bbox[1] * sy, x0 + bbox[2] * sx, y0 + bbox[3] * sy]
            parsed = {'text': block['text'], 'bbox': bbox or asset['bbox'], 'ocr': True}
            if table := block.get('table'):
                parsed['table'] = {**table, 'id': f'{asset["id"]}-{table["id"]}',
                                   'cell_id': f'{asset["id"]}-{table["cell_id"]}'}
            node['ocr_blocks'].append(parsed)
        for finding in result['issues']:
            issue(finding['code'], finding['message'], page=asset['page'], asset_id=asset['id'], bbox=asset['bbox'])

    def paragraph(item: dict[str, Any], number: int, table: dict[str, Any] | None = None) -> dict[str, Any] | None:
        text = item.get('text', '').strip()
        if not text:
            return None
        block_id = f'p{len(blocks) + 1}'
        block = {'id': block_id, 'text': text, 'anchor': None, 'page': number, 'bbox': item.get('bbox'),
                 'kind': 'ocr' if item.get('ocr') else ('table_cell' if table else 'paragraph'), 'native_editable': False}
        if table:
            block['table'] = table
        blocks.append(block)
        return {'type': 'paragraph', 'id': f'node-{block_id}', 'block_id': block_id,
                'page': number, 'bbox': item.get('bbox')}

    table_count = image_count = 0
    for info in pages:
        number = info['number']
        for item in _reading_order(page_items[number]):
            if item['type'] == 'paragraph':
                if node := paragraph(item, number):
                    document['body'].append(node)
            elif item['type'] == 'table':
                table_count += 1
                table_id = f'pdf-table-{table_count}'
                rows: dict[int, dict[str, Any]] = {}
                for cell in sorted(item['cells'], key=lambda c: (c['row'], c['col'])):
                    cell_id = f'{table_id}-r{cell["row"]}-c{cell["col"]}'
                    meta = {'id': table_id, 'cell_id': cell_id,
                            'header': bool(cell.get('header', False)),
                            **{key: cell[key] for key in ('row', 'col', 'row_span', 'col_span')}}
                    child = paragraph({**cell, 'ocr': item.get('ocr', False)}, number, meta)
                    rows.setdefault(cell['row'], {'id': f'{table_id}-r{cell["row"]}', 'cells': []})['cells'].append({
                        'id': cell_id, **{key: cell[key] for key in ('row', 'col', 'row_span', 'col_span')},
                        'header': bool(cell.get('header', False)), 'bbox': cell.get('bbox'),
                        'children': [child] if child else []})
                document['body'].append({'type': 'table', 'id': table_id, 'rows': list(rows.values()),
                                         'page': number, 'bbox': item.get('bbox')})
            elif item['type'] == 'image' and item.get('asset_id'):
                image_count += 1
                ids = []
                for block in item.get('ocr_blocks', []):
                    if child := paragraph(block, number, block.get('table')):
                        ids.append(child['block_id'])
                document['body'].append({'type': 'image', 'id': f'pdf-picture-{image_count}',
                                         'asset_id': item['asset_id'], 'block_ids': ids,
                                         'page': number, 'bbox': item['bbox']})
    warnings = list(dict.fromkeys(finding['message'] for finding in document['issues']))
    return {'blocks': blocks, 'document': document, 'assets': assets, 'warnings': warnings}
