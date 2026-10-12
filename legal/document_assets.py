"""Private source bytes and safe raster previews, used only after matter access checks."""
from __future__ import annotations

import base64
import hashlib
import io
import posixpath

MAX_IMAGE_PIXELS = 16_000_000
MAX_PREVIEW_PIXELS = 4_000_000
MAX_ASSET_BYTES = 12 * 1024 * 1024
SOURCE_MIMES = {'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                'pdf': 'application/pdf', 'txt': 'text/plain; charset=utf-8'}


def original_bytes(payload: dict) -> bytes:
    try:
        data = base64.b64decode(payload['original_b64'], validate=True)
    except (KeyError, ValueError, TypeError) as exc:
        raise ValueError('原件无法读取，请重新上传。') from exc
    if not data or (payload.get('content_hash') and hashlib.sha256(data).hexdigest() != payload['content_hash']):
        raise ValueError('原件内容校验不一致，请重新上传后审查。')
    return data


def docx_asset_bytes(data: bytes, asset: dict) -> bytes:
    from legal.docx_redlines import open_package
    part = asset.get('source_part')
    if (not isinstance(part, str) or not part.startswith('word/') or '\\' in part
            or posixpath.normpath(part) != part):
        raise ValueError('图片的原件位置无效。')
    archive, _ = open_package(data)
    try:
        info = archive.getinfo(part)
        if info.file_size > MAX_ASSET_BYTES:
            raise ValueError('图片过大，请在原 Word 中查看。')
        return archive.read(part)
    except KeyError as exc:
        raise ValueError('原件中未找到这张图片。') from exc
    finally:
        archive.close()


def raster_preview(data: bytes) -> tuple[bytes, str]:
    """Only return decoded raster pixels; SVG/HTML/EXIF/external links cannot reach the UI."""
    from PIL import Image, UnidentifiedImageError
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.width < 1 or image.height < 1 or image.width * image.height > MAX_IMAGE_PIXELS:
                raise ValueError('图片分辨率过大，请在原件中查看。')
            image.seek(0)
            image.load()
            safe = image.convert('RGB')
            safe.thumbnail((2000, 2000))
            safe.info.clear()
            output = io.BytesIO()
            safe.save(output, format='PNG')
            if output.tell() > MAX_ASSET_BYTES:
                raise ValueError('图片预览过大，请在原件中查看。')
            return output.getvalue(), 'image/png'
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError) as exc:
        raise ValueError('此图片格式无法安全预览，原件中的图片保持不变。') from exc


def asset_preview(payload: dict, asset_id: str) -> tuple[bytes, str]:
    asset = next((asset for asset in payload.get('assets', []) if asset.get('id') == asset_id), None)
    if not asset:
        raise KeyError(asset_id)
    data = original_bytes(payload)
    if payload['format'] == 'docx':
        return raster_preview(docx_asset_bytes(data, asset))
    if payload['format'] == 'pdf':
        from legal.pdf_structure import render_pdf_asset
        return render_pdf_asset(data, asset, max_pixels=MAX_PREVIEW_PIXELS)
    raise ValueError('此文件没有图片预览。')
