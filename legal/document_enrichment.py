"""Optional Word image OCR through the same private parser worker as PDF scans.

Ordinary Word text/tables never need OCR. Only OCR text enters the normal,
user-confirmed text redaction flow; image pixels stay in the source package.
"""
from __future__ import annotations

import io


def enrich_docx_images(parsed: dict, data: bytes) -> None:
    assets = parsed.get('assets', [])
    if not assets:
        return
    from legal import document_ocr
    if not document_ocr.ocr_status().get('configured'):
        return
    from PIL import Image, UnidentifiedImageError
    from legal.document_assets import docx_asset_bytes, MAX_IMAGE_PIXELS

    budget = document_ocr.OCRBudget()
    document = parsed['document']
    issues = document.setdefault('issues', [])

    def image_nodes(nodes, ancestor_tables=()):
        for node in nodes:
            if node.get('type') == 'image':
                yield node, tuple(node.get('ancestor_tables') or ancestor_tables)
            for row in node.get('rows', []):
                for cell in row.get('cells', []):
                    table = {'id': node['id'], 'cell_id': cell['id'],
                             **{key: cell[key] for key in ('row', 'col', 'row_span', 'col_span', 'header') if key in cell}}
                    yield from image_nodes(cell.get('children', []), (*ancestor_tables, table))

    nodes = list(image_nodes(document.get('body', [])))
    for section in document.get('sections', []):
        nodes.extend(image_nodes(section.get('body', [])))
    for asset in assets:
        placements = [(node, table) for node, table in nodes if node.get('asset_id') == asset['id']]
        if not placements:
            continue
        try:
            raw = docx_asset_bytes(data, asset)
            with Image.open(io.BytesIO(raw)) as image:
                # Small decorations retain a coverage notice without spending OCR
                # latency. Bounds are checked before decoding any large raster.
                if image.width < 160 or image.height < 60 or not 60_000 <= image.width * image.height <= MAX_IMAGE_PIXELS:
                    continue
        except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError):
            continue
        result = document_ocr.recognize_image(raw, asset.get('media_type', 'image/png'), budget=budget)
        # A repeated image is recognized once but keeps separate source anchors
        # at each placement; accepting a change must not edit another copy.
        for node, ancestor_tables in placements:
            block_ids = []
            for index, item in enumerate(result.get('blocks', [])):
                if not isinstance(item.get('text'), str) or not item['text'].strip():
                    continue
                bid = f'ocr-{node["id"]}-{index + 1}'
                block = {'id': bid, 'text': item['text'].strip(), 'page': None, 'anchor': None,
                         'kind': 'ocr', 'asset_id': asset['id'], 'native_editable': False}
                if item.get('bbox'):
                    block['image_bbox'] = item['bbox']
                if ancestor_tables:
                    block['table'] = dict(ancestor_tables[-1])
                    if len(ancestor_tables) > 1:
                        block['ancestor_tables'] = [dict(table) for table in ancestor_tables[:-1]]
                if isinstance(item.get('table'), dict):
                    table = {key: item['table'][key] for key in ('id', 'cell_id', 'row', 'col', 'row_span', 'col_span', 'header') if key in item['table']}
                    for key in ('id', 'cell_id'):
                        if key in table:
                            table[key] = node['id'] + '-' + str(table[key])
                    block['table'] = table
                    if ancestor_tables:
                        # OCR cells retain every enclosing Word cell for field
                        # redaction (e.g. "Contact" beside an image of a name).
                        block['ancestor_tables'] = [dict(parent) for parent in ancestor_tables]
                parsed['blocks'].append(block)
                block_ids.append(bid)
            node['block_ids'] = block_ids
            # OCR does not establish that seals, handwriting or graphical
            # relationships were fully read. Keep a localized, honest notice.
            message = ('这张图片已提取部分文字；请对照原图核对表格、签章和遗漏内容。' if block_ids
                       else '这张图片尚未识别出可审查文字；可在原件视图查看。')
            issue = {'id': f'ocr-{node["id"]}', 'code': 'image_ocr_review' if block_ids else 'image_ocr_pending',
                     'message': message, 'asset_id': asset['id'], 'node_id': node['id']}
            if block_ids:
                issue['block_id'] = block_ids[0]
            issues.append(issue)
    if any(b.get('kind') == 'ocr' for b in parsed['blocks']):
        parsed.setdefault('warnings', []).append('图片识别文字已纳入脱敏和审查；图片、签章及识别遗漏仍需对照原件。')
