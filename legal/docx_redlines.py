"""Original-package DOCX revisions, with an explicit appendix for unsupported edits."""
from __future__ import annotations

import io
import posixpath
import re
import zipfile
from copy import deepcopy
from datetime import datetime, timezone
from difflib import SequenceMatcher

from lxml import etree

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
NS = {'w': W}
REL = 'http://schemas.openxmlformats.org/package/2006/relationships'
SETTINGS_REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings'
CT = 'http://schemas.openxmlformats.org/package/2006/content-types'
XML_SPACE = '{http://www.w3.org/XML/1998/namespace}space'


def _xml(data: bytes):
    return etree.fromstring(data, etree.XMLParser(resolve_entities=False, no_network=True))


def open_package(data: bytes):
    archive = zipfile.ZipFile(io.BytesIO(data))
    try:
        infos = archive.infolist()
        if len(infos) > 2000 or sum(i.file_size for i in infos) > 40 * 1024 * 1024:
            raise ValueError('Word 解压后过大，请拆分文件。')
        names = [i.filename for i in infos]
        if len(names) != len(set(names)):
            raise ValueError('Word 包内存在重名文件，请另存为标准 DOCX。')
        if any(n.lower().endswith('vbaproject.bin') for n in names):
            raise ValueError('不接受包含宏的 Word 文件。')
        if any(n.startswith('_xmlsignatures/') for n in names):
            raise ValueError('Word 含数字签名；编辑会破坏签名，请提供未签署的审查副本。')
        root = _xml(archive.read('word/document.xml'))
        if root.tag != f'{{{W}}}document':
            raise ValueError('请另存为标准 DOCX 格式后上传。')
        # Refuse to silently accept or flatten earlier reviewers' changes.
        revisions = '//w:ins|//w:del|//w:moveFrom|//w:moveTo|//w:rPrChange|//w:pPrChange|//w:sectPrChange|//w:tblPrChange|//w:trPrChange|//w:tcPrChange|//w:tblGridChange|//w:cellIns|//w:cellDel|//w:numberingChange'
        for name in names:
            if name.startswith('word/') and name.endswith('.xml'):
                part = root if name == 'word/document.xml' else _xml(archive.read(name))
                if part.xpath(revisions, namespaces=NS):
                    raise ValueError('合同已有未处理的修订，请先在 Word 中确认修订后再上传；系统不会清除已有修订。')
        if root.xpath('//w:altChunk', namespaces=NS):
            raise ValueError('合同含尚未展开的嵌入正文，请另存为标准 DOCX 后重试。')
        return archive, root
    except Exception:
        archive.close()
        raise


def paragraph_text(p) -> str:
    """Use the same visible-text convention for intake and export anchors."""
    nodes = p.xpath('.//w:t[not(ancestor::w:txbxContent)]|.//w:tab[not(ancestor::w:txbxContent)]|.//w:br[not(ancestor::w:txbxContent)]|.//w:cr[not(ancestor::w:txbxContent)]', namespaces=NS)
    return ''.join((n.text or '') if n.tag == f'{{{W}}}t' else '\t' if n.tag == f'{{{W}}}tab' else '\n' for n in nodes)


def visible_paragraph_text(p) -> str:
    """A paragraph's own text, including inside a textbox but not nested boxes."""
    nodes = p.xpath('.//w:t|.//w:tab|.//w:br|.//w:cr', namespaces=NS)
    return ''.join((n.text or '') if n.tag == f'{{{W}}}t' else '\t' if n.tag == f'{{{W}}}tab' else '\n'
                   for n in nodes if next(n.iterancestors(f'{{{W}}}p'), None) is p)


class UnsupportedRevision(ValueError):
    """Valid source text that cannot be changed in place without structural loss."""


def _run_text(run) -> str:
    return ''.join((n.text or '') if n.tag == f'{{{W}}}t' else '\t' if n.tag == f'{{{W}}}tab' else '\n' if n.tag in (f'{{{W}}}br', f'{{{W}}}cr') else '' for n in run)


def _run(template, text: str, deleted: bool = False):
    run = etree.Element(f'{{{W}}}r', attrib=dict(template.attrib))
    props = template.find(f'{{{W}}}rPr')
    if props is not None:
        run.append(deepcopy(props))
    for value in re.split(r'(\t|\n)', text):
        if not value:
            continue
        if value in ('\t', '\n'):
            etree.SubElement(run, f'{{{W}}}{"tab" if value == chr(9) else "br"}')
        else:
            t = etree.SubElement(run, f'{{{W}}}{"delText" if deleted else "t"}')
            t.set(XML_SPACE, 'preserve')
            t.text = value
    return run


def _segments(p, block_id):
    if any(True for _ in p.iterancestors(f'{{{W}}}sdt')):
        raise UnsupportedRevision(f'{block_id} 位于内容控件中，原控件与原位置保留；请参照修改建议处理。')
    runs, objects, offset = [], {}, 0
    for child in p:
        if child.tag == f'{{{W}}}pPr':
            continue
        # Fields, linked text and range markers need a richer editor. Images can
        # remain as opaque original nodes when an edit does not cross their anchor.
        if child.tag != f'{{{W}}}r' or any(n.tag not in {f'{{{W}}}{x}' for x in ('rPr', 't', 'tab', 'br', 'cr', 'drawing', 'pict')} for n in child):
            raise UnsupportedRevision(f'{block_id} 含书签、域、批注或复杂对象，原位置保留；请参照修改建议处理。')
        if any(n.tag == f'{{{W}}}br' and n.get(f'{{{W}}}type', 'textWrapping') != 'textWrapping' for n in child):
            raise UnsupportedRevision(f'{block_id} 含分页或分栏符，原位置保留；请参照修改建议处理。')
        text = ''
        for element in child:
            if element.tag in (f'{{{W}}}drawing', f'{{{W}}}pict'):
                if text:
                    runs.append((offset, offset + len(text), child, text))
                    offset += len(text)
                    text = ''
                object_run = etree.Element(f'{{{W}}}r', attrib=dict(child.attrib))
                props = child.find(f'{{{W}}}rPr')
                if props is not None:
                    object_run.append(deepcopy(props))
                object_run.append(deepcopy(element))
                objects.setdefault(offset, []).append(object_run)
            elif element.tag == f'{{{W}}}t':
                text += element.text or ''
            elif element.tag == f'{{{W}}}tab':
                text += '\t'
            elif element.tag in (f'{{{W}}}br', f'{{{W}}}cr'):
                text += '\n'
        if text:
            runs.append((offset, offset + len(text), child, text))
            offset += len(text)
    return runs, objects


def paragraph_editable(p) -> bool:
    """Local capability hint; crossing an inline object's anchor may still need an appendix."""
    try:
        runs, _ = _segments(p, '')
    except UnsupportedRevision:
        return False
    return bool(runs) and ''.join(run[3] for run in runs) == paragraph_text(p)


def _runs(p, block_id):
    return _segments(p, block_id)[0]


def _slice(runs, start, end, deleted=False):
    for a, b, template, text in runs:
        lo, hi = max(a, start), min(b, end)
        if lo < hi:
            yield _run(template, text[lo - a:hi - a], deleted)


def _settings(archive) -> dict[str, bytes]:
    relpath = 'word/_rels/document.xml.rels'
    rels = _xml(archive.read(relpath)) if relpath in archive.namelist() else etree.Element(f'{{{REL}}}Relationships', nsmap={None: REL})
    related = [r for r in rels if r.get('Type') == SETTINGS_REL]
    if len(related) > 1 or (related and related[0].get('TargetMode') == 'External'):
        raise ValueError('Word 设置关系异常，无法安全生成修订稿。')
    target = related[0].get('Target', 'settings.xml') if related else 'settings.xml'
    path = posixpath.normpath(posixpath.join('word', target)).lstrip('/')
    if not path.startswith('word/') or not path.endswith('.xml'):
        raise ValueError('Word 设置文件路径异常。')
    settings = _xml(archive.read(path)) if path in archive.namelist() else etree.Element(f'{{{W}}}settings', nsmap={'w': W})
    if settings.tag != f'{{{W}}}settings':
        raise ValueError('Word 设置文件无效。')
    # CT_Settings schema order; retain all unrelated settings.
    for node in list(settings):
        if node.tag in {f'{{{W}}}trackRevisions', f'{{{W}}}revisionView'}:
            settings.remove(node)
    preceding = set('writeProtection view zoom removePersonalInformation removeDateAndTime doNotDisplayPageBoundaries displayBackgroundShape printPostScriptOverText printFractionalCharacterWidth printFormsData embedTrueTypeFonts embedSystemFonts saveSubsetFonts saveFormsData mirrorMargins alignBordersAndEdges bordersDoNotSurroundHeader bordersDoNotSurroundFooter gutterAtTop hideSpellingErrors hideGrammaticalErrors activeWritingStyle proofState formsDesign attachedTemplate linkStyles stylePaneFormatFilter stylePaneSortMethod documentType mailMerge'.split())
    idx = 0
    for i, child in enumerate(settings):
        if etree.QName(child).localname in preceding:
            idx = i + 1
    view = etree.Element(f'{{{W}}}revisionView')
    view.set(f'{{{W}}}markup', 'true')
    view.set(f'{{{W}}}insDel', 'true')
    tracking = etree.Element(f'{{{W}}}trackRevisions')
    tracking.set(f'{{{W}}}val', 'true')
    settings.insert(idx, view)
    settings.insert(idx + 1, tracking)
    if not related:
        ids = {r.get('Id') for r in rels}
        n = 1
        while f'rIdLegalSettings{n}' in ids:
            n += 1
        etree.SubElement(rels, f'{{{REL}}}Relationship', Id=f'rIdLegalSettings{n}', Type=SETTINGS_REL, Target=target)
    types = _xml(archive.read('[Content_Types].xml'))
    if not any(r.get('PartName') == '/' + path for r in types):
        etree.SubElement(types, f'{{{CT}}}Override', PartName='/' + path, ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml')
    return {path: _serialize(settings), relpath: _serialize(rels), '[Content_Types].xml': _serialize(types)}


def _serialize(node):
    return etree.tostring(node, xml_declaration=True, encoding='UTF-8', standalone=True)


def _revision_children(p, before, after, bid, rid, stamp):
    runs, objects = _segments(p, bid)
    if not runs:
        raise UnsupportedRevision('找不到可直接修改的文字，原位置保留；请参照修改建议处理。')
    if ''.join(run[3] for run in runs) != before:
        raise UnsupportedRevision('段落包含暂不直接改写的文字结构，原位置保留；请参照修改建议处理。')
    matcher = SequenceMatcher(None, before, after, autojunk=len(before) + len(after) > 12000)
    operations = matcher.get_opcodes()
    if any(a < pos < b for op, a, b, _, _ in operations if op != 'equal' for pos in objects):
        raise UnsupportedRevision('修改跨越图片或文本框的位置，原位置与对象保留；请参照修改建议处理。')
    children, emitted = [], set()

    def emit_objects(at):
        if at in objects and at not in emitted:
            children.extend(objects[at])
            emitted.add(at)

    for op, a, b, x, y in operations:
        emit_objects(a)
        if op == 'equal':
            cursor = a
            for at in sorted(pos for pos in objects if a <= pos <= b):
                children.extend(_slice(runs, cursor, at))
                emit_objects(at)
                cursor = at
            children.extend(_slice(runs, cursor, b))
            continue
        for tag in ('del', 'ins'):
            if (tag == 'del' and a == b) or (tag == 'ins' and x == y):
                continue
            node = etree.Element(f'{{{W}}}{tag}')
            for key, val in {'id': str(rid), 'author': 'CausalGraph Legal', 'date': stamp}.items():
                node.set(f'{{{W}}}{key}', val)
            rid += 1
            if tag == 'del':
                node.extend(_slice(runs, a, b, True))
            else:
                template = next((run[2] for run in runs if run[0] <= a < run[1]), runs[-1][2])
                node.append(_run(template, after[x:y]))
            children.append(node)
    emit_objects(len(before))
    return children, rid


def _readonly_source(archive, root, block):
    """Validate a real ancillary paragraph before allowing an appendix-only edit."""
    if block.get('kind') in ('ocr', 'image_text') and block.get('native_editable') is False:
        # OCR blocks are bound by the parsed contract snapshot rather than a Word
        # text node. They are never presented as an in-place native edit.
        return None
    ref = block.get('source_ref')
    if not isinstance(ref, dict):
        raise ValueError('原文定位无效，未导出任何修改。')
    part, at = ref.get('part'), ref.get('paragraph')
    if (not isinstance(part, str) or not part.startswith('word/') or part not in archive.namelist()
            or type(at) is not int or at < 0):
        raise ValueError('原文定位无效，未导出任何修改。')
    source = root if part == 'word/document.xml' else _xml(archive.read(part))
    paragraphs = source.xpath('//w:p', namespaces=NS)
    if at >= len(paragraphs) or visible_paragraph_text(paragraphs[at]).strip() != block['text']:
        raise ValueError('原文定位已变化，停止导出以避免误改。')
    return part, at


def _appendix(root, changes):
    body = root.find(f'{{{W}}}body')
    if body is None:
        raise ValueError('Word 缺少正文，无法生成修改建议附录。')
    section = body.find(f'{{{W}}}sectPr')
    at = body.index(section) if section is not None else len(body)

    def paragraph(value, *, heading=False, page_break=False):
        nonlocal at
        p = etree.Element(f'{{{W}}}p')
        if page_break:
            props = etree.SubElement(p, f'{{{W}}}pPr')
            etree.SubElement(props, f'{{{W}}}pageBreakBefore')
        template = etree.Element(f'{{{W}}}r')
        if heading:
            props = etree.SubElement(template, f'{{{W}}}rPr')
            etree.SubElement(props, f'{{{W}}}b')
        p.append(_run(template, value))
        body.insert(at, p)
        at += 1

    paragraph('未写入原位置的修改建议', heading=True, page_break=True)
    paragraph('以下修改没有替换原位置。原段落、图片和复杂对象均保留；请按下列完整建议在原位置处理。正文中其他已经生成的 Word 修订可正常接受或拒绝。')
    for index, change in enumerate(changes, 1):
        paragraph(f"{index}. 原文位置：{change['block_id']}", heading=True)
        paragraph('保留原因：' + change['reason'])
        paragraph('原文：' + change['original'])
        paragraph('建议替换为：')
        paragraph(change['text'])


def _redline_result(data: bytes, originals: list[dict], replacements: dict[str, str], *, appendix: bool) -> dict:
    archive, root = open_package(data)
    try:
        paragraphs = root.xpath('//w:body//w:p[not(ancestor::w:txbxContent)]', namespaces=NS)
        source_indices = {p: i for i, p in enumerate(root.xpath('//w:p', namespaces=NS))}
        index = {b['id']: b for b in originals}
        if len(index) != len(originals):
            raise ValueError('原文定位重复，未导出任何修改。')
        rid = max([0] + [int(x) for x in root.xpath('//@w:id', namespaces=NS) if re.fullmatch(r'\d+', x)]) + 1
        stamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        applied, unapplied, occupied, occupied_sources = [], [], set(), set()
        for bid, replacement in replacements.items():
            if not isinstance(bid, str) or not bid or len(bid) > 100:
                raise ValueError('原文定位无效，未导出任何修改。')
            block = index.get(bid)
            anchor = block.get('anchor') if block else None
            if (not isinstance(replacement, str) or len(replacement) > 60000
                    or re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', replacement)):
                raise ValueError('替换文本无效或过长。')
            if not block:
                raise ValueError('原文定位无效，未导出任何修改。')
            if anchor is None and block.get('native_editable') is False:
                source = _readonly_source(archive, root, block)
                if source in occupied_sources:
                    raise ValueError('原文定位重复，未导出任何修改。')
                if source is not None:
                    occupied_sources.add(source)
                if block['text'] == replacement:
                    continue
                reason = '该内容位于只读附属区域或来自图片识别，原位置保留。'
                if not appendix:
                    raise UnsupportedRevision(reason)
                unapplied.append({'block_id': bid, 'reason': reason, 'text': replacement, 'original': block['text']})
                continue
            if type(anchor) is not int or not 0 <= anchor < len(paragraphs) or anchor in occupied:
                raise ValueError('原文定位无效或重复，未导出任何修改。')
            occupied.add(anchor)
            p = paragraphs[anchor]
            source = ('word/document.xml', source_indices[p])
            ref = block.get('source_ref')
            if (source in occupied_sources
                    or (ref is not None and ref != {'part': source[0], 'paragraph': source[1]})
                    or (re.fullmatch(r'p\d+', bid) and int(bid[1:]) != anchor + 1)):
                raise ValueError('原文定位无效或重复，未导出任何修改。')
            occupied_sources.add(source)
            before = paragraph_text(p)
            if before.strip() != block['text']:
                raise ValueError('原文定位已变化，停止导出以避免误改。')
            leading = before[:len(before) - len(before.lstrip())]
            trailing = before[len(before.rstrip()):]
            after = leading + replacement + trailing
            if before == after:
                continue
            try:
                new_children, rid = _revision_children(p, before, after, bid, rid, stamp)
            except UnsupportedRevision as exc:
                if not appendix:
                    raise
                unapplied.append({'block_id': bid, 'reason': str(exc), 'text': replacement, 'original': block['text']})
                continue
            props = p.find(f'{{{W}}}pPr')
            for child in list(p):
                if child is not props:
                    p.remove(child)
            p.extend(new_children)
            applied.append(bid)
        details = {'unapplied': [{k: item[k] for k in ('block_id', 'reason')} for item in unapplied], 'applied_block_ids': applied}
        if not applied and not unapplied:
            return {'content': data, **details}
        if unapplied:
            _appendix(root, unapplied)
        updates = _settings(archive)
        updates['word/document.xml'] = _serialize(root)
        out = io.BytesIO()
        with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as dest:
            dest.comment = archive.comment
            for info in archive.infolist():
                dest.writestr(info, updates.pop(info.filename, archive.read(info.filename)))
            for name, content in updates.items():
                dest.writestr(name, content)
        return {'content': out.getvalue(), **details}
    finally:
        archive.close()


def redline_docx(data: bytes, originals: list[dict], replacements: dict[str, str]) -> bytes:
    """Strict native revisions; unsupported edits raise instead of silently omitting work."""
    return _redline_result(data, originals, replacements, appendix=False)['content']


def redline_docx_result(data: bytes, originals: list[dict], replacements: dict[str, str]) -> dict:
    """Native revisions plus a clearly labelled appendix for unapplied user choices.

    The result is {content: bytes, applied_block_ids: list[str], unapplied:
    [{block_id, reason}]}. Integrity errors still fail the complete export. An
    unsupported edit keeps the original location intact and includes its exact
    replacement in the appendix; it is never reported as applied.
    """
    return _redline_result(data, originals, replacements, appendix=True)
