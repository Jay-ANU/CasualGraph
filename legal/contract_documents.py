"""Local-only contract parsing, deterministic redaction and anchored Word revisions."""
from __future__ import annotations

import hashlib
import io
import re
from pathlib import Path
from typing import Any

from legal.docx_redlines import open_package as _docx_parts, paragraph_text, redline_docx

MAX_UPLOAD = 10 * 1024 * 1024
MAX_TEXT = 60000
MAX_BLOCKS = 500
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
NS = {'w': W}




def parse_contract(data: bytes, filename: str) -> dict[str, Any]:
    if not data or len(data) > MAX_UPLOAD:
        raise ValueError('请上传不超过 10 MB 的非空文件。')
    ext = Path(filename).suffix.lower()
    blocks: list[dict[str, Any]] = []
    warnings: list[str] = []
    if ext == '.docx':
        archive, root = _docx_parts(data)
        try:
            for index, p in enumerate(root.xpath('//w:body//w:p[not(ancestor::w:txbxContent)]', namespaces=NS)):
                text = paragraph_text(p).strip()
                if text:
                    blocks.append({'id': f'p{index + 1}', 'text': text, 'anchor': index, 'page': None})
            if root.xpath('//w:drawing|//w:pict|//w:object', namespaces=NS):
                warnings.append('图片、文本框和嵌入对象未纳入文字审查；需要人工检查。')
            if any(re.match(r'word/(header|footer|footnotes|endnotes|comments)', n) for n in archive.namelist()):
                warnings.append('页眉页脚、脚注、尾注和既有批注未纳入本轮审查。')
        finally:
            archive.close()
    elif ext == '.pdf':
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise ValueError('请先移除 PDF 密码保护。')
        if len(reader.pages) > 100:
            raise ValueError('首版最多接收 100 页 PDF，请按合同拆分。')
        for page_no, page in enumerate(reader.pages, 1):
            text = (page.extract_text() or '').strip()
            if not text:
                raise ValueError(f'第 {page_no} 页未提取到文字，可能为扫描页；请提供可复制文字的 PDF 或 DOCX。')
            for value in re.split(r'\n\s*\n|(?=第[一二三四五六七八九十百零\d]+条)', text):
                if value.strip():
                    blocks.append({'id': f'p{len(blocks) + 1}', 'text': value.strip(), 'anchor': None, 'page': page_no})
        warnings.append('PDF 表格阅读顺序和图片内容需人工复核；仅支持审查报告及文字修改稿，不回写 PDF。')
    elif ext == '.txt':
        try:
            text = data.decode('utf-8-sig')
        except UnicodeDecodeError as exc:
            raise ValueError('TXT 需要 UTF-8 编码。') from exc
        for line in text.splitlines():
            if line.strip():
                blocks.append({'id': f'p{len(blocks) + 1}', 'text': line.strip(), 'anchor': None, 'page': None})
    else:
        raise ValueError('仅支持 DOCX、可复制文字的 PDF 和 UTF-8 TXT。')
    if any(re.search(r'【(?:补充)?脱敏\d+】', b['text']) for b in blocks):
        raise ValueError('原件包含系统保留的脱敏代称，请使用原始审查副本。')
    if not blocks:
        raise ValueError('没有提取到可审查正文。')
    if len(blocks) > MAX_BLOCKS or sum(len(b['text']) for b in blocks) > MAX_TEXT:
        raise ValueError('首版每份合同最多 6 万字、500 个正文段落；请拆分后审查，系统不会静默截断。')
    return {'blocks': blocks, 'format': ext[1:], 'warnings': warnings,
            'content_hash': hashlib.sha256(data).hexdigest()}


def redact_blocks(blocks: list[dict], additional_terms: list[str] | None = None,
                  excluded_terms: list[str] | None = None) -> tuple[list[dict], dict[str, str]]:
    from legal.redaction_detection import redact
    return redact(blocks, additional_terms, excluded_terms)


def restore(text: str, mapping: dict[str, str]) -> str:
    return re.sub(r'【脱敏\d+】', lambda m: mapping.get(m.group(), m.group()), text)


