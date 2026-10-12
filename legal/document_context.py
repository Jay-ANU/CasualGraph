"""The same source structure for review, redacted previews and local exports.

Text lives in blocks only. The structure contains references and geometry, never
another copy of a cell value, image alt text, a source path or an image payload.
"""
from __future__ import annotations

from html import escape
import math

VERSION = 1
KINDS = {'paragraph', 'heading', 'table_cell', 'ocr', 'textbox', 'header', 'footer', 'footnote', 'endnote'}
SECTION_TITLES = {'header': '页眉', 'footer': '页脚', 'textbox': '文本框', 'footnote': '脚注', 'endnote': '尾注', 'comment': '既有批注'}


def _geometry(value):
    if (isinstance(value, (list, tuple)) and len(value) == 4
            and all(isinstance(x, (float, int)) and math.isfinite(x) for x in value)):
        return list(value)
    return None


def model_blocks(blocks: list[dict]) -> list[dict]:
    """Allowlisted metadata; no source XML anchors, raw image bytes or spans."""
    output = []
    for block in blocks:
        item = {'id': block['id'], 'text': block['text']}
        if block.get('page'):
            item['page'] = block['page']
        if block.get('kind') in KINDS:
            item['kind'] = block['kind']
        for key in ('label', 'asset_id', 'section_id'):
            if isinstance(block.get(key), str) and block[key]:
                item[key] = block[key]
        if isinstance(block.get('heading_level'), int):
            item['heading_level'] = block['heading_level']
        if isinstance(block.get('native_editable'), bool):
            item['native_editable'] = block['native_editable']
        table = block.get('table')
        if isinstance(table, dict):
            item['table'] = {key: table[key] for key in ('id', 'cell_id', 'row', 'col', 'row_span', 'col_span', 'header') if key in table}
        output.append(item)
    return output


def public_structure(document: dict | None) -> dict | None:
    """Keep old flat contracts readable and never expose parser-private fields."""
    if not isinstance(document, dict) or document.get('version') != VERSION:
        return None

    def nodes(values, depth=0):
        if depth > 24:
            return []
        result = []
        for source in values or []:
            if not isinstance(source, dict) or source.get('type') not in ('paragraph', 'table', 'image'):
                continue
            kind = source['type']
            item = {'id': source['id'], 'type': kind}
            if source.get('page'):
                item['page'] = source['page']
            if (bbox := _geometry(source.get('bbox'))) is not None:
                item['bbox'] = bbox
            if kind == 'paragraph':
                item['block_id'] = source.get('block_id')
            elif kind == 'image':
                item.update(asset_id=source.get('asset_id'), block_ids=list(source.get('block_ids') or []))
                for key in ('width', 'height', 'host_block_id'):
                    if key in source:
                        item[key] = source[key]
            else:
                item['rows'] = []
                if isinstance(source.get('column_widths'), list):
                    item['column_widths'] = source['column_widths']
                for row in source.get('rows', []):
                    cells = []
                    for cell in row.get('cells', []):
                        safe = {key: cell[key] for key in ('id', 'row', 'col', 'row_span', 'col_span', 'header') if key in cell}
                        safe['children'] = nodes(cell.get('children'), depth + 1)
                        if (bbox := _geometry(cell.get('bbox'))) is not None:
                            safe['bbox'] = bbox
                        cells.append(safe)
                    item['rows'].append({'id': row['id'], 'cells': cells})
            result.append(item)
        return result

    pages = []
    for page in document.get('pages', []):
        pages.append({key: page[key] for key in ('number', 'width', 'height', 'rotation', 'crop_bbox', 'coverage', 'method') if key in page})
    issues = []
    for issue in document.get('issues', []):
        issues.append({key: issue[key] for key in ('id', 'code', 'message', 'severity', 'page', 'block_id', 'node_id', 'asset_id', 'bbox') if key in issue})
    sections = []
    for section in document.get('sections', []):
        kind = section.get('kind', '')
        sections.append({'id': section['id'], 'kind': kind,
                         'title': SECTION_TITLES.get(kind, '附属内容'), 'read_only': True,
                         'body': nodes(section.get('body'))})
    return {'version': VERSION, 'source': document.get('source'), 'body': nodes(document.get('body')),
            'pages': pages, 'issues': issues, **({'sections': sections} if sections else {})}


def public_assets(assets: list[dict]) -> list[dict]:
    return [{key: asset[key] for key in ('id', 'media_type', 'width', 'height', 'page', 'bbox') if key in asset}
            for asset in assets]


def public_blocks(blocks: list[dict]) -> list[dict]:
    output = model_blocks(blocks)
    for item, block in zip(output, blocks):
        item['page'] = block.get('page')
        if (bbox := _geometry(block.get('bbox'))) is not None:
            item['bbox'] = bbox
        if 'redaction_spans' in block:
            item['redaction_spans'] = block['redaction_spans']
    return output


def model_structure(document: dict | None) -> dict | None:
    source = public_structure(document)
    if source is None:
        return None

    def compact(nodes):
        result = []
        for node in nodes:
            if node['type'] == 'paragraph':
                if node.get('block_id'):
                    result.append(node['block_id'])
            elif node['type'] == 'image':
                result.append({'image_id': node['id'], 'block_ids': node.get('block_ids', [])})
            else:
                rows = []
                for row in node['rows']:
                    cells = []
                    for cell in row['cells']:
                        item = {'cell_id': cell['id'], 'at': [cell.get('row', 0), cell.get('col', 0)],
                                'blocks': compact(cell['children'])}
                        if cell.get('row_span', 1) != 1 or cell.get('col_span', 1) != 1:
                            item['span'] = [cell.get('row_span', 1), cell.get('col_span', 1)]
                        if cell.get('header'):
                            item['header'] = True
                        cells.append(item)
                    rows.append(cells)
                result.append({'table_id': node['id'], 'rows': rows})
        return result

    # Geometry and asset bytes serve original previews. Compact references keep
    # full/empty cells and order without paying for a second copy of every node.
    return {'version': VERSION, 'body': compact(source['body']),
            'sections': [{'kind': section['kind'], 'body': compact(section['body'])} for section in source.get('sections', [])],
            'unread_regions': [{key: issue[key] for key in ('code', 'page', 'block_id', 'node_id', 'asset_id') if key in issue}
                               for issue in source['issues']]}


def model_request_blocks(blocks: list[dict], structure: dict | None) -> list[dict]:
    if structure is None:
        return model_blocks(blocks)
    represented_tables = set()

    def visit(nodes):
        for node in nodes:
            if isinstance(node, dict) and node.get('table_id'):
                represented_tables.add(node['table_id'])
                for row in node['rows']:
                    for cell in row:
                        visit(cell['blocks'])

    visit(structure['body'])
    for section in structure.get('sections', []):
        visit(section['body'])
    output = model_blocks(blocks)
    for item in output:
        if item.get('table', {}).get('id') in represented_tables:
            item.pop('table', None)
        if item.get('kind') in ('paragraph', 'table_cell'):
            item.pop('kind', None)
        if item.get('native_editable') is True:
            item.pop('native_editable', None)
    return output


def render_contract(blocks: list[dict], document: dict | None = None) -> str:
    """A full-document reading order with intact table geometry and minimal edit IDs."""
    by_id = {b['id']: b for b in blocks}
    used = set()

    def paragraph(bid, *, html=False):
        block = by_id.get(bid)
        if block is None or bid in used:
            return ''
        used.add(bid)
        location = f'（第{block["page"]}页）' if block.get('page') else ''
        label = f'（显示编号：{block["label"]}）' if block.get('label') else ''
        ocr = '（图片识别文字，需对照原图）' if block.get('kind') == 'ocr' else ''
        table = block.get('table')
        cell = (f'（表 {table["id"]}，第 {table.get("row", 0) + 1} 行、第 {table.get("col", 0) + 1} 列）'
                if table and (not html or block.get('kind') == 'ocr') else '')
        text = f'[{bid}]{location}{label}{ocr}{cell} {block["text"]}'
        return escape(text, quote=False) if html else text

    def render(nodes, in_table=False):
        output = []
        for node in nodes:
            if node['type'] == 'paragraph':
                text = paragraph(node.get('block_id'), html=in_table)
                if text:
                    output.append(text)
            elif node['type'] == 'image':
                output.append(f'【图片 {node["id"]}：图像保留在原件；下列内容仅为已提取文字，未向模型发送图像】')
                output.extend(filter(None, (paragraph(bid, html=in_table) for bid in node.get('block_ids', []))))
            elif node['type'] == 'table':
                output.append(f'<table id="{escape(node["id"], quote=True)}">')
                for row in node['rows']:
                    output.append('<tr>')
                    for cell in row['cells']:
                        tag = 'th' if cell.get('header') else 'td'
                        attrs = ' '.join(f'{key}="{escape(str(value), quote=True)}"' for key, value in (
                            ('id', cell['id']), ('row', cell.get('row', 0) + 1), ('column', cell.get('col', 0) + 1),
                            ('rowspan', cell.get('row_span', 1)), ('colspan', cell.get('col_span', 1))))
                        output.append(f'<{tag} {attrs}>\n' + '\n'.join(render(cell['children'], True)) + f'\n</{tag}>')
                    output.append('</tr>')
                output.append('</table>')
        return output

    structure = public_structure(document)
    if not structure:
        return '\n'.join(paragraph(b['id']) for b in blocks)
    output = render(structure['body'])
    for section in structure.get('sections', []):
        output += ['', f'【{section["title"]}：修改列入附录，原位置保留】', *render(section['body'])]
    # Compatibility with parsed structures from earlier versions: never lose text.
    remaining = [b['id'] for b in blocks if b['id'] not in used]
    if remaining:
        output += ['', '【其他已提取文字】', *(paragraph(bid) for bid in remaining)]
    return '\n'.join(output)


STRUCTURE_GUIDANCE = '''表格须按行列、表头和合并单元格整体理解；相同金额或期限不代表同一位置。
document_structure 中 at 为从0开始的行列，span 为跨行/跨列（缺省均为1），blocks 为文字块编号或嵌套结构；空数组是保留的空单元格。
每个 block_id 只对应一个可修改文字块，修改只返回该块的完整文字，不能把整张表写进一个单元格。
label 是自动编号的显示结果，不属于块内原文，revised_text 不要重复添加 label；HTML 实体按可见文字理解。
图片原始像素没有发给模型，OCR 文字不代表图片、印章、签名或版面已完整核实；未识别区域必须明确保留为资料缺口。
native_editable=false 表示源位置不能原位改写；仍可提出修改，导出时列为批注或附录。'''
