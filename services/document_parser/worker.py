"""Docling adapter and killable, prewarmed process for the private parser."""
from __future__ import annotations

import io
import logging
import math
import multiprocessing
import os
import signal
import threading
from pathlib import Path
from typing import Any

MAX_BYTES = 10 * 1024 * 1024
MAX_PAGES = 4
MAX_IMAGE_PIXELS = 12_000_000
MAX_TOTAL_RASTER_PIXELS = 24_000_000
MAX_ITEMS = 1500
MAX_TEXT = 120_000


class ParserFailure(Exception):
    """Only its generic code, never a backend exception, crosses HTTP."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _bounded_env(name: str, default: float, maximum: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
        return max(1.0, min(value, maximum)) if math.isfinite(value) else default
    except ValueError:
        return default


def preflight(data: bytes, media_type: str) -> tuple[bytes, str, tuple[int, int] | None]:
    """Bound decoded dimensions before Docling can rasterize any source page."""
    if not data or len(data) > MAX_BYTES:
        raise ParserFailure('input_limit')
    try:
        if media_type == 'application/pdf':
            from pypdf import PdfReader
            pdf = PdfReader(io.BytesIO(data))
            if pdf.is_encrypted or not 0 < len(pdf.pages) <= MAX_PAGES:
                raise ParserFailure('input_limit')
            raster = 0.0
            for page in pdf.pages:
                w, h = float(page.mediabox.width), float(page.mediabox.height)
                unit = float(page.get('/UserUnit', 1))
                if not all(math.isfinite(v) and v > 0 for v in (w, h, unit)):
                    raise ParserFailure('input_limit')
                # The selected OCR engine rasterizes at 3 pixels / PDF point.
                pixels = w * h * unit * unit * 9
                if pixels > MAX_IMAGE_PIXELS:
                    raise ParserFailure('input_limit')
                raster += pixels
            if raster > MAX_TOTAL_RASTER_PIXELS:
                raise ParserFailure('input_limit')
            return data, 'source.pdf', None
        if media_type not in ('image/png', 'image/jpeg', 'image/tiff', 'image/webp'):
            raise ParserFailure('unsupported_type')
        from PIL import Image
        with Image.open(io.BytesIO(data)) as image:
            original_size = image.size
            if image.width * image.height > MAX_IMAGE_PIXELS or getattr(image, 'n_frames', 1) != 1:
                raise ParserFailure('input_limit')
            # Bound decoded image size and assign explicit physical dimensions:
            # 144 DPI prevents an unspecified-DPI camera image becoming a huge
            # PDF page that the OCR stage would upscale threefold again.
            image.thumbnail((1800, 1800))
            image = image.convert('RGB')
            try:
                stream = io.BytesIO()
                image.save(stream, format='PNG', dpi=(144, 144))
                return stream.getvalue(), 'source.png', original_size
            finally:
                image.close()
    except ParserFailure:
        raise
    except Exception as exc:
        raise ParserFailure('invalid_input') from exc


def normalize_docling_document(document: dict[str, Any], *, image_size: tuple[int, int] | None = None,
                               partial: bool = False) -> dict[str, Any]:
    """Convert the pinned Docling JSON graph to our deliberately small v1 schema.

    Traverse references, not the flat texts collection: tables own their cell
    text and may also reference text nodes. Emitting both duplicates clauses.
    Furniture is retained because contract footnotes/headers can be material.
    """
    source_pages = document.get('pages', {})
    if not isinstance(source_pages, dict) or not 0 < len(source_pages) <= MAX_PAGES:
        raise ParserFailure('invalid_result')
    pages = {}
    source_sizes = {}
    for key, page in source_pages.items():
        number = int(page.get('page_no', key))
        size = page['size']
        width, height = float(size['width']), float(size['height'])
        if not all(math.isfinite(v) and 0 < v <= 30000 for v in (width, height)):
            raise ParserFailure('invalid_result')
        source_sizes[number] = (width, height)
        target = image_size if image_size and len(source_pages) == 1 else (width, height)
        pages[number] = {'number': number, 'width': target[0], 'height': target[1], 'items': []}
    references = {}
    for kind in ('texts', 'tables', 'pictures', 'groups'):
        for index, item in enumerate(document.get(kind, [])):
            references[item.get('self_ref', f'#/{kind}/{index}')] = item
    visited = set()
    item_count = text_count = 0

    def coordinates(raw: dict[str, Any] | None, number: int) -> list[float] | None:
        if not raw:
            return None
        width, height = source_sizes[number]
        x0, y0, x1, y1 = (float(raw[k]) for k in ('l', 't', 'r', 'b'))
        if str(raw.get('coord_origin', 'TOPLEFT')).upper() == 'BOTTOMLEFT':
            y0, y1 = height - y0, height - y1
        x0, x1 = sorted((x0, x1))
        y0, y1 = sorted((y0, y1))
        if not all(math.isfinite(v) for v in (x0, y0, x1, y1)):
            raise ParserFailure('invalid_result')
        sx, sy = pages[number]['width'] / width, pages[number]['height'] / height
        result = [max(0.0, x0) * sx, max(0.0, y0) * sy, min(width, x1) * sx, min(height, y1) * sy]
        return result if result[2] > result[0] and result[3] > result[1] else None

    def visit(ref: Any):
        nonlocal item_count, text_count, partial
        ref = ref.get('$ref') if isinstance(ref, dict) else ref
        if not isinstance(ref, str) or ref in visited:
            return
        visited.add(ref)
        item = references.get(ref)
        if not item:
            partial = True
            return
        prov = item.get('prov', [])
        locations = [p for p in prov if p.get('page_no') in pages]
        number = locations[0]['page_no'] if locations else None
        bbox = coordinates(locations[0].get('bbox'), number) if locations else None
        if ref.startswith('#/tables/'):
            # Multiple page fragments cannot be silently assigned one bbox.
            if len({p['page_no'] for p in locations}) > 1:
                partial = True
            cells = []
            for cell in item.get('data', {}).get('table_cells', []):
                text = cell.get('text', '')
                row, col = int(cell['start_row_offset_idx']), int(cell['start_col_offset_idx'])
                row_span = int(cell.get('row_span', cell['end_row_offset_idx'] - row))
                col_span = int(cell.get('col_span', cell['end_col_offset_idx'] - col))
                cells.append({'row': row, 'col': col, 'row_span': row_span, 'col_span': col_span,
                              'text': text, 'bbox': coordinates(cell.get('bbox'), number) if number else None,
                              'header': bool(cell.get('column_header') or cell.get('row_header'))})
                text_count += len(text)
            if number is not None and cells:
                pages[number]['items'].append({'type': 'table', 'bbox': bbox, 'cells': cells})
                item_count += 1 + len(cells)
            else:
                partial = True
            return
        if item.get('text'):
            if number is None:
                partial = True
            else:
                text = item['text']
                text_count += len(text)
                pages[number]['items'].append({'type': 'paragraph', 'text': text, 'bbox': bbox})
                item_count += 1
        elif ref.startswith('#/pictures/') and number is not None:
            pages[number]['items'].append({'type': 'image', 'bbox': bbox})
            item_count += 1
        for child in item.get('children', []):
            visit(child)
        if item_count > MAX_ITEMS or text_count > MAX_TEXT:
            raise ParserFailure('result_limit')

    for root in ('body', 'furniture'):
        for child in document.get(root, {}).get('children', []):
            visit(child)
    if item_count > MAX_ITEMS or text_count > MAX_TEXT:
        raise ParserFailure('result_limit')
    return {'version': 1, 'status': 'partial' if partial else 'complete',
            'pages': [pages[number] for number in sorted(pages)], 'issues': []}


class DoclingEngine:
    def __init__(self):
        artifacts = os.getenv('DOCLING_ARTIFACTS_PATH', '').strip()
        if not artifacts or not Path(artifacts).is_dir():
            raise ParserFailure('models_unavailable')
        # These settings are in addition to network egress denial in deployment.
        os.environ['HF_HUB_OFFLINE'] = '1'
        os.environ['TRANSFORMERS_OFFLINE'] = '1'
        os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import (
            PdfPipelineOptions, TesseractCliOcrOptions, OcrMode,
            TableStructureOptions, TableFormerMode,
        )
        from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption, ImageFormatOption
        options = PdfPipelineOptions(
            artifacts_path=Path(artifacts), enable_remote_services=False, allow_external_plugins=False,
            document_timeout=_bounded_env('PARSER_DOCUMENT_TIMEOUT_SECONDS', 18, 55),
            do_ocr=True, do_table_structure=True,
            do_picture_classification=False, do_picture_description=False,
            do_code_enrichment=False, do_formula_enrichment=False,
            generate_page_images=False, generate_picture_images=False,
            accelerator_options=AcceleratorOptions(device=AcceleratorDevice.CPU, num_threads=2),
            ocr_options=TesseractCliOcrOptions(lang=['chi_sim', 'chi_tra', 'eng'], mode=OcrMode.FULL_PAGE),
            table_structure_options=TableStructureOptions(mode=TableFormerMode.FAST),
        )
        self.converter = DocumentConverter(allowed_formats=[InputFormat.PDF, InputFormat.IMAGE], format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=options),
            InputFormat.IMAGE: ImageFormatOption(pipeline_options=options),
        })
        self.converter.initialize_pipeline(InputFormat.PDF)
        self.converter.initialize_pipeline(InputFormat.IMAGE)

    def convert(self, data: bytes, media_type: str) -> dict[str, Any]:
        from docling.datamodel.base_models import DocumentStream
        normalized, name, image_size = preflight(data, media_type)
        result = self.converter.convert(DocumentStream(name=name, stream=io.BytesIO(normalized)),
                                        max_num_pages=MAX_PAGES, max_file_size=MAX_BYTES,
                                        raises_on_error=False)
        status = str(getattr(result.status, 'value', result.status))
        if status not in ('success', 'partial_success'):
            raise ParserFailure('conversion_failed')
        return normalize_docling_document(result.document.export_to_dict(), image_size=image_size,
                                          partial=status != 'success')


def _child(connection):
    # Third-party parsers sometimes include extracted snippets in warnings.
    # Keep those diagnostics out of application stdout/stderr, including native
    # subprocess output. The parent exposes only the generic failure code.
    if os.name == 'posix':
        os.setsid()  # Tesseract descendants share this killable process group.
    logging.disable(logging.CRITICAL)
    with open(os.devnull, 'w') as sink:
        os.dup2(sink.fileno(), 1)
        os.dup2(sink.fileno(), 2)
    try:
        engine = DoclingEngine()
        connection.send({'ready': True})
    except Exception:
        connection.send({'ready': False})
        connection.close()
        return
    while True:
        try:
            data, media_type = connection.recv()
        except (EOFError, OSError):
            break
        try:
            connection.send({'result': engine.convert(data, media_type)})
        except ParserFailure as exc:
            connection.send({'error': exc.code})
        except Exception:
            connection.send({'error': 'conversion_failed'})
    connection.close()


class ParserProcess:
    """One model process; timeouts kill it so subsequent jobs cannot pile up."""

    def __init__(self):
        self._process = None
        self._connection = None
        self._ready = False
        self._lock = threading.Lock()

    def start(self):
        self.close()
        context = multiprocessing.get_context('spawn')
        parent, child = context.Pipe()
        self._connection = parent
        self._process = context.Process(target=_child, args=(child,), daemon=True)
        self._process.start()
        child.close()

    def ready(self, timeout: float = 0) -> bool:
        if not self._process or not self._process.is_alive():
            return False
        if not self._ready and self._connection.poll(timeout):
            try:
                self._ready = self._connection.recv().get('ready', False)
            except (EOFError, OSError):
                return False
        return self._ready

    def convert(self, data: bytes, media_type: str) -> dict[str, Any]:
        if not self._lock.acquire(blocking=False):
            raise ParserFailure('busy')
        try:
            if not self.ready():
                raise ParserFailure('unavailable')
            self._connection.send((data, media_type))
            timeout = _bounded_env('PARSER_HARD_TIMEOUT_SECONDS', 20, 60)
            if not self._connection.poll(timeout):
                self.start()  # Replacement prewarms independently; no queued raw documents.
                raise ParserFailure('timeout')
            response = self._connection.recv()
            if 'result' not in response:
                code = response.get('error')
                raise ParserFailure(code if code in ('input_limit', 'invalid_input', 'result_limit', 'unsupported_type')
                                    else 'conversion_failed')
            return response['result']
        except (EOFError, OSError):
            self.start()
            raise ParserFailure('unavailable') from None
        finally:
            self._lock.release()

    def close(self):
        if self._process:
            pid = self._process.pid
            if os.name == 'posix' and pid:
                try:
                    os.killpg(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            if self._process.is_alive():
                self._process.terminate()
                self._process.join(timeout=1)
                if self._process.is_alive():
                    self._process.kill()
                    self._process.join(timeout=1)
            # A killed Python process could otherwise orphan a running OCR
            # subprocess. Reap the entire group, even if Python already exited.
            if os.name == 'posix' and pid:
                try:
                    os.killpg(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            self._process.close()
            self._process = None
        if self._connection:
            self._connection.close()
            self._connection = None
        self._ready = False
