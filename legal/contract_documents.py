"""Source-preserving contract parsing, local redaction and anchored revisions."""
from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path
from typing import Any

from legal.docx_redlines import redline_docx

MAX_UPLOAD = 10 * 1024 * 1024
MAX_TEXT = 60000
MAX_BLOCKS = 500

def parse_contract(data: bytes, filename: str) -> dict[str, Any]:
    if not data or len(data) > MAX_UPLOAD:
        raise ValueError('请上传不超过 10 MB 的非空文件。')
    started = time.monotonic()
    ext = Path(filename).suffix.lower()
    if ext == '.docx':
        from legal.docx_structure import parse_docx
        from legal.document_enrichment import enrich_docx_images
        result = parse_docx(data)
        enrich_docx_images(result, data)
    elif ext == '.pdf':
        from legal.pdf_structure import parse_pdf
        result = parse_pdf(data)
    elif ext == '.txt':
        try:
            text = data.decode('utf-8-sig')
        except UnicodeDecodeError as exc:
            raise ValueError('TXT 需要 UTF-8 编码。') from exc
        blocks = [{'id': f'p{i + 1}', 'text': line.strip(), 'anchor': None, 'page': None, 'kind': 'paragraph'}
                  for i, line in enumerate(line for line in text.splitlines() if line.strip())]
        result = {'blocks': blocks, 'warnings': [], 'assets': [],
                  'document': {'version': 1, 'source': 'txt', 'body': [
                      {'type': 'paragraph', 'id': 'node-' + b['id'], 'block_id': b['id']} for b in blocks],
                      'pages': [], 'issues': []}}
    else:
        raise ValueError('仅支持 DOCX、PDF 和 UTF-8 TXT。')
    blocks = result['blocks']
    if any(re.search(r'【(?:补充)?脱敏\d+】', b['text'] + b.get('label', '')) for b in blocks):
        raise ValueError('原件包含系统保留的脱敏代称，请使用原始审查副本。')
    if len({block['id'] for block in blocks}) != len(blocks):
        raise ValueError('文件包含重复文字定位，请重新导出原件后上传。')
    # Keep scans viewable when OCR is unavailable. Creating a review requires
    # actual text, so a failed recognizer cannot invent successful coverage.
    if not blocks and not result.get('assets') and not result.get('document', {}).get('pages'):
        raise ValueError('没有提取到可审查正文或可查看的图片。')
    if len(blocks) > MAX_BLOCKS or sum(len(b['text']) + len(b.get('label', '')) for b in blocks) > MAX_TEXT:
        raise ValueError('每份合同最多 6 万字、500 个文字块（包括单元格和识别文字）；请拆分后审查，系统不会静默截断。')
    issues = result.get('document', {}).get('issues', [])
    result.update(format=ext[1:], content_hash=hashlib.sha256(data).hexdigest(),
                  parsing_status='needs_ocr' if not blocks else 'partial' if issues else 'ready',
                  parsing_metrics={'elapsed_ms': round((time.monotonic() - started) * 1000),
                                   'block_count': len(blocks), 'asset_count': len(result.get('assets', []))})
    return result


def redact_blocks(blocks: list[dict], additional_terms: list[str] | None = None,
                  excluded_terms: list[str] | None = None) -> tuple[list[dict], dict[str, str]]:
    from legal.redaction_detection import redact
    return redact(blocks, additional_terms, excluded_terms)


def restore(text: str, mapping: dict[str, str]) -> str:
    return re.sub(r'【脱敏\d+】', lambda m: mapping.get(m.group(), m.group()), text)


