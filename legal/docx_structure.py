"""Native Word structure with immutable paragraph anchors and local image references.

Text lives only in blocks. Nodes and assets never copy alt text, style names or
other unredacted prose into metadata that could bypass the redaction pass.
"""
from __future__ import annotations

from collections import defaultdict
import io
import posixpath
import re

from PIL import Image, UnidentifiedImageError

from legal.docx_redlines import NS, W, open_package, paragraph_editable, paragraph_text, visible_paragraph_text, _xml

R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
WP = 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'
V = 'urn:schemas-microsoft-com:vml'
MC = 'http://schemas.openxmlformats.org/markup-compatibility/2006'
REL = 'http://schemas.openxmlformats.org/package/2006/relationships'
PREFIXES = {**NS, 'r': R, 'a': A, 'wp': WP, 'v': V}
MAX_NODES = 10000
MAX_IMAGE_PIXELS = 40_000_000
MAX_LABEL = 500


def _int(value, default=0, minimum=0, maximum=1000000):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if minimum <= number <= maximum else default


def _value(node, name, default=None):
    child = node.find(f'{{{W}}}{name}') if node is not None else None
    return child.get(f'{{{W}}}val', default) if child is not None else default


def _children(node):
    """Unwrap content controls while choosing one AlternateContent representation."""
    for child in node:
        if child.tag == f'{{{MC}}}AlternateContent':
            choice = child.find(f'{{{MC}}}Choice')
            if choice is None:
                choice = child.find(f'{{{MC}}}Fallback')
            if choice is not None:
                yield from _children(choice)
        elif child.tag in {f'{{{W}}}{name}' for name in ('sdt', 'sdtContent', 'customXml')}:
            yield from _children(child)
        else:
            yield child


def _roman(number):
    if not 0 < number < 4000:
        return str(number)
    result = ''
    for value, text in ((1000, 'M'), (900, 'CM'), (500, 'D'), (400, 'CD'), (100, 'C'), (90, 'XC'),
                        (50, 'L'), (40, 'XL'), (10, 'X'), (9, 'IX'), (5, 'V'), (4, 'IV'), (1, 'I')):
        count, number = divmod(number, value)
        result += text * count
    return result


def _letters(number):
    if number <= 0:
        return str(number)
    result = ''
    while number:
        number, digit = divmod(number - 1, 26)
        result = chr(65 + digit) + result
    return result


def _chinese(number):
    if not 0 <= number < 10000:
        return str(number)
    if number == 0:
        return '零'
    result, zero = '', False
    for place, unit in ((1000, '千'), (100, '百'), (10, '十'), (1, '')):
        digit, number = divmod(number, place)
        if digit:
            if zero:
                result += '零'
            result += ('' if digit == 1 and place == 10 and not result else '零一二三四五六七八九'[digit]) + unit
            zero = False
        elif result and number:
            zero = True
    return result


def _number(number, fmt):
    if fmt in ('decimal', 'decimalZero'):
        return str(number).zfill(2) if fmt == 'decimalZero' else str(number)
    if fmt in ('upperRoman', 'lowerRoman'):
        value = _roman(number)
        return value.lower() if fmt == 'lowerRoman' else value
    if fmt in ('upperLetter', 'lowerLetter'):
        value = _letters(number)
        return value.lower() if fmt == 'lowerLetter' else value
    if fmt in ('chineseCounting', 'chineseCountingThousand', 'ideographTraditional'):
        return _chinese(number)
    if fmt == 'decimalEnclosedCircle' and 1 <= number <= 20:
        return chr(0x2460 + number - 1)
    if fmt == 'none':
        return ''
    return None


class _Numbering:
    def __init__(self, archive):
        self.styles, self.nums, self.abstract = {}, {}, {}
        self.counts = defaultdict(dict)
        self.default_style = None
        if 'word/styles.xml' in archive.namelist():
            root = _xml(archive.read('word/styles.xml'))
            for style in root.findall(f'{{{W}}}style'):
                key = style.get(f'{{{W}}}styleId')
                if key:
                    self.styles[key] = style
                if style.get(f'{{{W}}}type') == 'paragraph' and style.get(f'{{{W}}}default') in ('1', 'true'):
                    self.default_style = key
        if 'word/numbering.xml' in archive.namelist():
            root = _xml(archive.read('word/numbering.xml'))
            self.nums = {n.get(f'{{{W}}}numId'): n for n in root.findall(f'{{{W}}}num')}
            self.abstract = {n.get(f'{{{W}}}abstractNumId'): n for n in root.findall(f'{{{W}}}abstractNum')}

    def properties(self, paragraph):
        direct = paragraph.find(f'{{{W}}}pPr')
        key, chain, seen = _value(direct, 'pStyle', self.default_style), [], set()
        while key in self.styles and key not in seen and len(chain) < 32:
            seen.add(key)
            style = self.styles[key]
            props = style.find(f'{{{W}}}pPr')
            if props is not None:
                chain.append(props)
            key = _value(style, 'basedOn')
        return list(reversed(chain)) + ([direct] if direct is not None else [])

    def describe(self, paragraph, part):
        number_id, level, heading = None, 0, None
        for props in self.properties(paragraph):
            outline = _value(props, 'outlineLvl')
            if outline is not None:
                heading = _int(outline, 9, maximum=9) + 1
                heading = heading if heading <= 9 else None
            num = props.find(f'{{{W}}}numPr')
            if num is not None:
                number_id = _value(num, 'numId', number_id)
                level = _int(_value(num, 'ilvl', level), maximum=8)
        if number_id in (None, '0'):
            return None, heading, False
        num = self.nums.get(number_id)
        if num is None:
            return None, heading, True
        abstract = self.abstract.get(_value(num, 'abstractNumId'))
        if abstract is None:
            return None, heading, True
        levels = {_int(n.get(f'{{{W}}}ilvl'), maximum=8): n for n in abstract.findall(f'{{{W}}}lvl')}
        starts = {}
        for override in num.findall(f'{{{W}}}lvlOverride'):
            at = _int(override.get(f'{{{W}}}ilvl'), maximum=8)
            changed = override.find(f'{{{W}}}lvl')
            if changed is not None:
                levels[at] = changed
            start = _value(override, 'startOverride')
            if start is not None:
                starts[at] = _int(start, 1)
        definition = levels.get(level)
        if definition is None:
            return None, heading, True
        counts = self.counts[(part, number_id)]
        start = lambda at: starts.get(at, _int(_value(levels.get(at), 'start', '1'), 1))
        counts[level] = counts[level] + 1 if level in counts else start(level)
        for at in list(counts):
            restart = _value(levels.get(at), 'lvlRestart')
            trigger = at - 1 if restart is None else _int(restart, 0, maximum=9) - 1
            if at > level and trigger >= level:
                counts.pop(at, None)
        fmt = _value(definition, 'numFmt', 'decimal')
        pattern = _value(definition, 'lvlText', '%' + str(level + 1) + '.')
        if not isinstance(pattern, str) or len(pattern) > MAX_LABEL:
            return None, heading, True
        if fmt == 'bullet':
            return ''.join('•' if 0xE000 <= ord(ch) <= 0xF8FF else ch for ch in pattern), heading, False
        valid = True
        legal_node = definition.find(f'{{{W}}}isLgl')
        legal_numbering = legal_node is not None and legal_node.get(f'{{{W}}}val', '1') not in ('0', 'false', 'off')

        def replace(match):
            nonlocal valid
            at = int(match.group(1)) - 1
            value = _number(counts.get(at, start(at)), 'decimal' if legal_numbering else _value(levels.get(at), 'numFmt', 'decimal'))
            if value is None:
                valid = False
            return value or ''

        label = re.sub(r'%([1-9])', replace, pattern)
        return (label if valid else None), heading, not valid


class _Parser:
    def __init__(self, archive, root):
        self.archive, self.root = archive, root
        self.blocks, self.assets, self.issues, self.sections = [], [], [], []
        self.counts, self.asset_parts, self.rels = defaultdict(int), {}, {}
        self.parts = {'word/document.xml': root}
        self.paragraph_indices, self.seen_textboxes = {}, set()
        self.anchors = {p: i for i, p in enumerate(root.xpath('//w:body//w:p[not(ancestor::w:txbxContent)]', namespaces=NS))}
        self.numbering = _Numbering(archive)

    def ident(self, kind):
        self.counts[kind] += 1
        if sum(self.counts.values()) > MAX_NODES:
            raise ValueError('Word 结构过于复杂，请拆分后审查。')
        return f'{kind}{self.counts[kind]}'

    def issue(self, code, message, **location):
        self.issues.append({'id': self.ident('issue'), 'code': code, 'message': message, **location})

    def relations(self, part):
        if part not in self.rels:
            path = posixpath.join(posixpath.dirname(part), '_rels', posixpath.basename(part) + '.rels')
            root = _xml(self.archive.read(path)) if path in self.archive.namelist() else None
            self.rels[part] = {r.get('Id'): r for r in root} if root is not None else {}
        return self.rels[part]

    def related_part(self, part, rid, relation_type):
        relation = self.relations(part).get(rid)
        if relation is None or not relation.get('Type', '').endswith('/' + relation_type):
            return None
        target = relation.get('Target', '')
        if relation.get('TargetMode') == 'External' or not target or '\\' in target or ':' in target:
            return None
        resolved = posixpath.normpath(target.lstrip('/') if target.startswith('/') else posixpath.join(posixpath.dirname(part), target))
        return resolved if resolved.startswith('word/') and resolved in self.archive.namelist() else None

    def part_root(self, part):
        if part not in self.parts:
            self.parts[part] = _xml(self.archive.read(part))
        return self.parts[part]

    def source_ref(self, paragraph, part):
        if part not in self.paragraph_indices:
            self.paragraph_indices[part] = {p: i for i, p in enumerate(self.part_root(part).xpath('//w:p', namespaces=NS))}
        return {'part': part, 'paragraph': self.paragraph_indices[part][paragraph]}

    def image(self, ref, part, host, ancestor_tables=()):
        rid = ref.get(f'{{{R}}}embed') or ref.get(f'{{{R}}}id') or ref.get(f'{{{R}}}link')
        source = self.related_part(part, rid, 'image')
        if source is None:
            self.issue('image_unavailable', '一处图片未嵌入或无法读取，原件中的对应内容仍需查看。', **({'block_id': host} if host else {}))
            return None
        if source not in self.asset_parts:
            asset = {'id': self.ident('asset'), 'media_type': 'application/octet-stream', 'source_part': source}
            try:
                with Image.open(io.BytesIO(self.archive.read(source))) as image:
                    if image.width * image.height > MAX_IMAGE_PIXELS:
                        raise ValueError('image_size')
                    asset.update(width=image.width, height=image.height, media_type=Image.MIME.get(image.format, 'application/octet-stream'))
            except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
                self.issue('image_preview_unavailable', '一处图片格式或大小无法直接预览，可在原 Word 中查看。', asset_id=asset['id'])
            self.asset_parts[source] = asset
            self.assets.append(asset)
        asset = self.asset_parts[source]
        node = {'type': 'image', 'id': self.ident('image'), 'asset_id': asset['id']}
        if host:
            node['host_block_id'] = host
        if ancestor_tables:
            # Textboxes are presented in separate read-only sections. Keep the
            # original enclosing cells privately, so OCR does not lose a field
            # label merely because the preview moved the textbox out of its row.
            node['ancestor_tables'] = list(ancestor_tables)
        for key in ('width', 'height'):
            if key in asset:
                node[key] = asset[key]
        for parent in ref.iterancestors():
            if parent.tag in (f'{{{WP}}}inline', f'{{{WP}}}anchor'):
                extent = parent.find(f'{{{WP}}}extent')
                if extent is not None:
                    for key, attr in (('width', 'cx'), ('height', 'cy')):
                        emu = _int(extent.get(attr), 0, minimum=1, maximum=190_500_000)
                        if emu:
                            node[key] = max(1, round(emu / 9525))
                break
        self.issue('image_text_unread', '图片已保留；其中的文字和图示需结合图片识别结果或原件核对。', node_id=node['id'], asset_id=asset['id'])
        return node

    def paragraph(self, paragraph, part, kind, table=None, ancestor_tables=()):
        self.ident('paragraph')
        primary = kind == 'body' and paragraph in self.anchors
        bid = f'p{self.anchors[paragraph] + 1}' if primary else self.ident('auxp')
        text = (paragraph_text(paragraph) if primary else visible_paragraph_text(paragraph)).strip()
        label, heading, unresolved = self.numbering.describe(paragraph, part)
        nodes = []
        if text:
            block = {'id': bid, 'text': text, 'anchor': self.anchors[paragraph] if primary else None, 'page': None,
                     'kind': ('table_cell' if table else 'paragraph') if primary else kind,
                     'native_editable': bool(primary and paragraph_editable(paragraph)), 'source_ref': self.source_ref(paragraph, part)}
            if label:
                block['label'] = label
            if heading:
                block['heading_level'] = heading
            if table:
                block['table'] = table
            if ancestor_tables:
                block['ancestor_tables'] = list(ancestor_tables)
            self.blocks.append(block)
            nodes.append({'type': 'paragraph', 'id': 'node-' + bid, 'block_id': bid})
            if primary and not block['native_editable']:
                self.issue('native_edit_unavailable', '这一段含暂不直接改写的复杂结构；选择的修改可在导出附录中完整列出。', block_id=bid)
        if unresolved:
            self.issue('numbering_unresolved', '一处自动编号格式暂无法展开，请结合原件核对条款编号。', **({'block_id': bid} if text else {}))
        # Only the representation selected by AlternateContent is inspected. A
        # textbox has its own paragraph blocks and is never copied into its host.
        def objects(node):
            for child in _children(node):
                if child.tag == f'{{{W}}}txbxContent':
                    if child not in self.seen_textboxes:
                        self.seen_textboxes.add(child)
                        sid = self.ident('textbox')
                        body = self.container(child, part, 'textbox', table, ancestor_tables)
                        self.sections.append({'id': sid, 'kind': 'textbox', 'title': '文本框', 'body': body, 'read_only': True})
                        self.issue('textbox_read_only', '文本框文字已纳入审查；原位置保留，修改建议通过附录导出。', node_id=sid)
                    continue
                if child.tag in (f'{{{W}}}drawing', f'{{{W}}}pict'):
                    found, sections, issues = len(nodes), len(self.sections), len(self.issues)
                    objects(child)
                    if len(nodes) == found and len(self.sections) == sections and len(self.issues) == issues:
                        self.issue('drawing_unread', '一处图表或绘图对象尚未展开，请结合原件核对。', **({'block_id': bid} if text else {}))
                    continue
                if child.tag in (f'{{{A}}}blip', f'{{{V}}}imagedata'):
                    parents = (*ancestor_tables, table) if table else ancestor_tables
                    image = self.image(child, part, bid if text else None, parents)
                    if image:
                        nodes.append(image)
                    continue
                if child.tag == f'{{{W}}}object':
                    self.issue('embedded_object_unread', '嵌入对象未展开；请在原件中查看其内容。', **({'block_id': bid} if text else {}))
                if len(child):
                    objects(child)
        objects(paragraph)
        return nodes

    def logical_cells(self, row, tid):
        """Canonicalise legacy hMerge to the same grid as modern gridSpan cells."""
        groups, horizontal = [], None
        for cell in (c for c in _children(row) if c.tag == f'{{{W}}}tc'):
            self.ident('cell')
            props = cell.find(f'{{{W}}}tcPr')
            raw_span = _value(props, 'gridSpan', '1')
            span = _int(raw_span, 0, minimum=1, maximum=1000)
            if not span:
                span = 1
                self.issue('table_grid_unresolved', '一处表格列宽关系无效，文字已保留，请结合原件核对。', node_id=tid)
            vm = props.find(f'{{{W}}}vMerge') if props is not None else None
            vertical = vm.get(f'{{{W}}}val', 'continue') if vm is not None else None
            if vertical not in (None, 'restart', 'continue'):
                vertical = None
                self.issue('table_merge_unresolved', '一处合并单元格关系无效，文字已保留，请结合原件核对。', node_id=tid)
            hm = props.find(f'{{{W}}}hMerge') if props is not None else None
            state = hm.get(f'{{{W}}}val', 'continue') if hm is not None else None
            if state == 'continue' and horizontal is not None:
                horizontal['members'].append(cell)
                horizontal['span'] += span
                if horizontal['span'] > 1000:
                    raise ValueError('Word 表格列数过多，请拆分后审查。')
                if horizontal['vertical'] != vertical:
                    horizontal['vertical'] = None
                    self.issue('table_merge_unresolved', '一处横纵合并关系不一致，横向内容已保留，请结合原件核对。', node_id=tid)
                continue
            group = {'members': [cell], 'span': span, 'vertical': vertical}
            groups.append(group)
            horizontal = group if state == 'restart' else None
            if state not in (None, 'restart'):
                self.issue('table_merge_unresolved', '一处旧式横向合并缺少有效起点，文字已保留，请结合原件核对。', node_id=tid)
        return groups

    def table(self, table, part, kind, ancestor_tables=()):
        tid = self.ident('table')
        node = {'type': 'table', 'id': tid, 'rows': []}
        widths = [_int(col.get(f'{{{W}}}w')) for col in table.findall(f'{{{W}}}tblGrid/{{{W}}}gridCol')]
        if widths:
            node['column_widths'] = widths
        active = {}
        for row_index, row in enumerate(c for c in _children(table) if c.tag == f'{{{W}}}tr'):
            row_node = {'id': f'{tid}-row{row_index}', 'cells': []}
            node['rows'].append(row_node)
            props = row.find(f'{{{W}}}trPr')
            col = _int(_value(props, 'gridBefore'))
            header_node = props.find(f'{{{W}}}tblHeader') if props is not None else None
            header = header_node is not None and header_node.get(f'{{{W}}}val', '1') not in ('0', 'false', 'off')
            next_active = {}
            for group in self.logical_cells(row, tid):
                span, merge = group['span'], group['vertical']
                continued = merge == 'continue'
                prior = active.get((col, span)) if continued else None
                if prior:
                    cell_node, context = prior
                    cell_node['row_span'] += 1
                    context['row_span'] = cell_node['row_span']
                else:
                    cid = f'{tid}-r{row_index}-c{col}'
                    cell_node = {'id': cid, 'row': row_index, 'col': col, 'row_span': 1, 'col_span': span, 'children': []}
                    if header:
                        cell_node['header'] = True
                    context = {'id': tid, 'cell_id': cid, 'row': row_index, 'col': col, 'row_span': 1, 'col_span': span, 'header': header}
                    row_node['cells'].append(cell_node)
                    if continued:
                        self.issue('table_merge_unresolved', '一处合并单元格关系不完整，已保留文字，请结合原件核对。', node_id=tid)
                for cell in group['members']:
                    cell_node['children'].extend(self.container(cell, part, kind, context, ancestor_tables))
                if merge is not None:
                    next_active[(col, span)] = (cell_node, context)
                col += span
            active = next_active
        return node

    def container(self, container, part, kind, table=None, ancestor_tables=()):
        nodes = []
        for child in _children(container):
            if child.tag == f'{{{W}}}p':
                nodes.extend(self.paragraph(child, part, kind, table, ancestor_tables))
            elif child.tag == f'{{{W}}}tbl':
                parents = (*ancestor_tables, table) if table else ancestor_tables
                nodes.append(self.table(child, part, kind, parents))
        return nodes

    def ancillary(self):
        seen = set()
        for kind, title in (('header', '页眉'), ('footer', '页脚')):
            for ref in self.root.xpath(f'//w:sectPr/w:{kind}Reference', namespaces=NS):
                part = self.related_part('word/document.xml', ref.get(f'{{{R}}}id'), kind)
                if not part:
                    self.issue('ancillary_unavailable', '一处页眉页脚引用无法读取，请结合原件核对。')
                    continue
                if part in seen:
                    continue
                seen.add(part)
                sid = self.ident(kind)
                body = self.container(self.part_root(part), part, kind)
                if not body:
                    continue
                self.sections.append({'id': sid, 'kind': kind, 'title': title, 'body': body, 'read_only': True})
                self.issue('ancillary_read_only', '页眉页脚文字已纳入审查；原位置保留，修改建议通过附录导出。', node_id=sid)
        for stem, message in (('footnotes', '脚注'), ('endnotes', '尾注'), ('comments', '既有批注')):
            if any(re.fullmatch(r'word/' + stem + r'[^/]*\.xml', name) for name in self.archive.namelist()):
                self.issue('ancillary_unread', message + '尚未纳入正文审查，请结合原件核对。')


def parse_docx(data: bytes) -> dict:
    """Parse locally; original body paragraph IDs remain compatible with redlines."""
    archive, root = open_package(data)
    try:
        parser = _Parser(archive, root)
        body = root.find(f'{{{W}}}body')
        if body is None:
            raise ValueError('Word 缺少正文。')
        nodes = parser.container(body, 'word/document.xml', 'body')
        parser.ancillary()
        document = {'version': 1, 'source': 'docx', 'body': nodes, 'pages': [], 'issues': parser.issues}
        if parser.sections:
            document['sections'] = parser.sections
        warnings = list(dict.fromkeys(issue['message'] for issue in parser.issues))
        return {'blocks': parser.blocks, 'document': document, 'assets': parser.assets, 'warnings': warnings}
    finally:
        archive.close()
