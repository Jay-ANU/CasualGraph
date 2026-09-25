"""Real, run-preserving DOCX revisions. Never exports a reconstructed plain document."""
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


def _runs(p, block_id):
    runs, offset = [], 0
    for child in p:
        if child.tag == f'{{{W}}}pPr':
            continue
        # Leave unchanged paragraphs untouched. Reject structural objects in
        # edited paragraphs instead of losing bookmarks, fields or comments.
        if child.tag != f'{{{W}}}r' or any(n.tag not in {f'{{{W}}}{x}' for x in ('rPr', 't', 'tab', 'br', 'cr')} for n in child):
            raise ValueError(f'{block_id} 含书签、域、批注或复杂对象，未生成部分修改稿；请在原 Word 中人工修改该段。')
        if any(n.tag == f'{{{W}}}br' and n.get(f'{{{W}}}type', 'textWrapping') != 'textWrapping' for n in child):
            raise ValueError(f'{block_id} 含分页或分栏符，请在原 Word 中修改该段。')
        value = _run_text(child)
        if value:
            runs.append((offset, offset + len(value), child, value))
            offset += len(value)
        elif len(child) > 1 or (len(child) == 1 and child[0].tag != f'{{{W}}}rPr'):
            raise ValueError(f'{block_id} 含非文字对象，请在原 Word 中修改该段。')
    return runs


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


def redline_docx(data: bytes, originals: list[dict], replacements: dict[str, str]) -> bytes:
    """Include chosen proposals as pending Word revisions, not accepted clean text.

    Plain body and table paragraphs are supported. Unchanged package parts remain
    byte-for-byte identical. Any unsupported changed paragraph aborts the export.
    """
    archive, root = open_package(data)
    try:
        paragraphs = root.xpath('//w:body//w:p[not(ancestor::w:txbxContent)]', namespaces=NS)
        index = {b['id']: b for b in originals}
        rid = max([0] + [int(x) for x in root.xpath('//@w:id', namespaces=NS) if re.fullmatch(r'\d+', x)]) + 1
        stamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        changed = False
        for bid, replacement in replacements.items():
            block = index.get(bid)
            anchor = block.get('anchor') if block else None
            if not block or type(anchor) is not int or not 0 <= anchor < len(paragraphs):
                raise ValueError('原文定位无效，未导出任何修改。')
            if not isinstance(replacement, str) or len(replacement) > 60000:
                raise ValueError('替换文本无效或过长。')
            p = paragraphs[anchor]
            before = paragraph_text(p)
            if before.strip() != block['text']:
                raise ValueError('原文定位已变化，停止导出以避免误改。')
            leading = before[:len(before) - len(before.lstrip())]
            trailing = before[len(before.rstrip()):]
            after = leading + replacement + trailing
            if before == after:
                continue
            runs = _runs(p, bid)
            if not runs:
                raise ValueError('找不到可修改文字。')
            new_children = []
            matcher = SequenceMatcher(None, before, after, autojunk=len(before) + len(after) > 12000)
            for op, a, b, x, y in matcher.get_opcodes():
                if op == 'equal':
                    new_children.extend(_slice(runs, a, b))
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
                        template = next((r[2] for r in runs if r[0] <= a < r[1]), runs[-1][2])
                        node.append(_run(template, after[x:y]))
                    new_children.append(node)
            props = p.find(f'{{{W}}}pPr')
            for child in list(p):
                if child is not props:
                    p.remove(child)
            p.extend(new_children)
            changed = True
        if not changed:
            return data
        updates = _settings(archive)
        updates['word/document.xml'] = _serialize(root)
        out = io.BytesIO()
        with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as dest:
            dest.comment = archive.comment
            for info in archive.infolist():
                dest.writestr(info, updates.pop(info.filename, archive.read(info.filename)))
            for name, content in updates.items():
                dest.writestr(name, content)
        return out.getvalue()
    finally:
        archive.close()
