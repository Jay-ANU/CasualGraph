"""Annotated source PDF plus a readable change appendix; never PDF text replacement."""
from __future__ import annotations

from functools import lru_cache
from html import escape
import io
import math
import os
from pathlib import Path
import threading

_FONT_LOCK = threading.Lock()


@lru_cache(maxsize=4)
def _font(configured: str) -> str:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfbase.ttfonts import TTFont
    # The production image installs this small CJK TrueType collection so the
    # appendix embeds its own Chinese glyphs. A dev machine may override it.
    candidates = [configured, '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
                  '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc']
    with _FONT_LOCK:
        for candidate in candidates:
            if candidate and Path(candidate).is_file():
                name = 'LegalAppendixCJK'
                pdfmetrics.registerFont(TTFont(name, candidate, subfontIndex=0))
                return name
        pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
    return 'STSong-Light'


def _location(block: dict) -> str:
    parts = [f'第 {block["page"]} 页' if block.get('page') else '原位置待核对', f'文字块 {block["id"]}']
    table = block.get('table')
    if table:
        parts.append(f'表格 {table.get("id", "")}，第 {table.get("row", 0) + 1} 行、第 {table.get("col", 0) + 1} 列')
    return ' · '.join(parts)


def _appendix(selected: list[tuple[dict, str]], original_pages: int) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, KeepTogether

    font = _font(os.getenv('LEGAL_PDF_FONT_PATH', '').strip())
    normal = ParagraphStyle('LegalBody', fontName=font, fontSize=10.5, leading=16,
                            textColor=colors.HexColor('#202936'), wordWrap='CJK', splitLongWords=True,
                            spaceAfter=9)
    heading = ParagraphStyle('LegalTitle', parent=normal, fontSize=18, leading=26, spaceAfter=14)
    item_heading = ParagraphStyle('LegalItem', parent=normal, fontSize=12, leading=18, spaceBefore=12, spaceAfter=8)
    small = ParagraphStyle('LegalSmall', parent=normal, fontSize=9, leading=14, textColor=colors.HexColor('#526174'))

    def para(text, style=normal):
        value = escape(str(text)).replace('\r\n', '\n').replace('\r', '\n').replace('\t', '    ')
        return Paragraph(value.replace('\n', '<br/>'), style)

    story = [para('合同修订建议附录', heading),
             para(f'前 {original_pages} 页保留原 PDF 的文字、表格和图片。以下 {len(selected)} 项为当前选择的修改，已尽可能标在原页对应位置；原 PDF 正文没有被覆盖。', normal),
             para('批注和本附录构成审阅副本。需要正式修改正文时，请使用可编辑原件逐项落实；原件仍可单独下载。', small), Spacer(1, 5)]
    for index, (block, replacement) in enumerate(selected, 1):
        story.append(KeepTogether([para(f'{index}  {_location(block)}', item_heading), para('原文', small)]))
        story.append(para(block['text']))
        story.append(para('修改后建议', small))
        story.append(para(replacement))
    output = io.BytesIO()

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(font, 8)
        canvas.setFillColor(colors.HexColor('#526174'))
        canvas.drawRightString(A4[0] - 48, 27, f'修订建议附录  {doc.page}')
        canvas.restoreState()

    SimpleDocTemplate(output, pagesize=A4, leftMargin=48, rightMargin=48, topMargin=42, bottomMargin=46,
                      title='合同修订建议附录', author='CasualGraph').build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()


def _rect(block: dict, width: float, height: float):
    bbox = block.get('bbox')
    if (not isinstance(bbox, (tuple, list)) or len(bbox) != 4
            or not all(isinstance(x, (int, float)) and math.isfinite(x) for x in bbox)):
        return None
    x0, top, x1, bottom = bbox
    if not 0 <= x0 < x1 <= width + .1 or not 0 <= top < bottom <= height + .1:
        return None
    # Parser coordinates refer to the normalized rotated MediaBox, top-left.
    return (x0, max(0, height - bottom), min(width, x1), height - top)


def annotated_pdf(data: bytes, originals: list[dict], replacements: dict[str, str]) -> bytes:
    from pypdf import PdfReader, PdfWriter
    from pypdf.annotations import Text, Highlight
    from pypdf.generic import ArrayObject, FloatObject, NameObject, TextStringObject

    by_id = {block['id']: block for block in originals}
    if len(by_id) != len(originals) or any(bid not in by_id for bid in replacements):
        raise ValueError('PDF 修改定位无效，请重新选择修改。')
    selected = [(block, replacements[block['id']]) for block in originals
                if block['id'] in replacements and replacements[block['id']] != block['text']]
    if not selected:
        return data
    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        raise ValueError('请先移除 PDF 密码保护。')
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    normalized = set()
    for index, (block, replacement) in enumerate(selected, 1):
        page_no = block.get('page')
        if not isinstance(page_no, int) or not 1 <= page_no <= len(reader.pages):
            continue  # Still included, explicitly unlocated, in the complete appendix.
        page = writer.pages[page_no - 1]
        if page_no not in normalized:
            # Also normalizes nonzero MediaBox origins when /Rotate is zero.
            page.transfer_rotation_to_content()
            normalized.add(page_no)
        width, height = float(page.mediabox.width), float(page.mediabox.height)
        rect = _rect(block, width, height)
        contents = f'修订建议 {index}\n{_location(block)}\n原文：\n{block["text"]}\n修改后建议：\n{replacement}'
        if rect:
            x0, y0, x1, y1 = rect
            highlight = Highlight(rect=rect, quad_points=ArrayObject([FloatObject(x) for x in
                                  (x0, y1, x1, y1, x0, y0, x1, y0)]), highlight_color='f4cc5a')
            highlight[NameObject('/CA')] = FloatObject(.2)
            # The highlighted source itself opens the complete comment. A sticky
            # note icon on top of the same words would obscure short cell values.
            highlight[NameObject('/Contents')] = TextStringObject(contents)
            highlight[NameObject('/T')] = TextStringObject('CasualGraph 修订建议')
            writer.add_annotation(page_no - 1, highlight)
        else:
            note_rect = (float(page.cropbox.left) + 12, float(page.cropbox.top) - 34,
                         float(page.cropbox.left) + 30, float(page.cropbox.top) - 16)
            note = Text(rect=note_rect, text=contents, open=False)
            note[NameObject('/T')] = TextStringObject('CasualGraph 修订建议')
            writer.add_annotation(page_no - 1, note)
    appendix = PdfReader(io.BytesIO(_appendix(selected, len(reader.pages))))
    for page in appendix.pages:
        writer.add_page(page)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()
