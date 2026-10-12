"""Real geometry fixtures: columns, merged cells, mixed scans and source crops."""
import hashlib
import io

import pytest
from PIL import Image, ImageDraw
from pypdf import PdfReader, PdfWriter
from pypdf.generic import RectangleObject
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from legal import document_ocr as ocr
from legal import pdf_structure as pdfs


@pytest.fixture(autouse=True)
def no_private_worker(monkeypatch):
    monkeypatch.delenv('LEGAL_DOCUMENT_PARSER_URL', raising=False)
    monkeypatch.delenv('LEGAL_DOCUMENT_PARSER_TOKEN', raising=False)


def make_pdf(draw):
    stream = io.BytesIO()
    paper = canvas.Canvas(stream, pagesize=(600, 800))
    draw(paper)
    paper.save()
    return stream.getvalue()


def scan_image():
    image = Image.new('RGB', (600, 800), 'white')
    draw = ImageDraw.Draw(image)
    draw.text((40, 80), 'IMAGE ONLY CONTRACT. Amount: 1000', fill='black')
    return image


def test_columns_read_top_to_bottom_before_next_column():
    def draw(c):
        c.setFont('Helvetica', 12)
        c.drawString(50, 750, 'Contract terms and obligations for both signing parties')
        for i in range(3):
            # Intentionally paint interleaved rows, as common PDF writers do.
            c.drawString(50, 710 - i * 20, f'Left clause {i + 1}.')
            c.drawString(330, 710 - i * 20, f'Right clause {i + 1}.')
    result = pdfs.parse_pdf(make_pdf(draw))
    text = '\n'.join(b['text'] for b in result['blocks'])
    assert text.index('Left clause 3') < text.index('Right clause 1')
    assert all(b['native_editable'] is False and b['anchor'] is None for b in result['blocks'])
    assert not result['document']['issues']


def test_merged_cells_retain_grid_and_text_once():
    def draw(c):
        c.rect(50, 450, 500, 200)
        for y in (500, 600):
            c.line(50, y, 550, y)
        c.line(200, 550, 550, 550)
        for x in (200, 350):
            c.line(x, 450, x, 600)
        for x, y, text in [(60, 625, 'Merged heading'), (60, 575, 'Party'),
                           (210, 575, 'Acme'), (360, 575, 'ID'),
                           (210, 525, 'Signer'), (360, 525, 'Alice'),
                           (60, 475, 'Amount'), (210, 475, 'USD'), (360, 475, '1000')]:
            c.drawString(x, y, text)
    result = pdfs.parse_pdf(make_pdf(draw))
    tables = [n for n in result['document']['body'] if n['type'] == 'table']
    assert len(tables) == 1
    cells = [c for r in tables[0]['rows'] for c in r['cells']]
    assert any(c['row'] == 0 and c['col_span'] == 3 for c in cells)
    assert any(c['row'] == 1 and c['col'] == 0 and c['row_span'] == 2 for c in cells)
    assert len(result['blocks']) == 9
    assert sum(b['text'] == 'Acme' for b in result['blocks']) == 1
    assert all(b['table']['id'] == tables[0]['id'] for b in result['blocks'])
    assert len({b['table']['cell_id'] for b in result['blocks']}) == 9


@pytest.mark.parametrize('paint_order', ['row', 'column'])
def test_borderless_table_cells_follow_geometry_not_paint_order(paint_order):
    rows = [('Party', 'Name', 'Amount'), ('Buyer', 'Acme', '1000'), ('Seller', 'Delta', '2000')]
    def draw(c):
        coords = [(r, col) for r in range(3) for col in range(3)]
        if paint_order == 'column':
            coords.sort(key=lambda rc: (rc[1], rc[0]))
        for row, col in coords:
            c.drawString(50 + col * 180, 720 - row * 25, rows[row][col])
    result = pdfs.parse_pdf(make_pdf(draw))
    assert [b['text'] for b in result['blocks']] == [text for row in rows for text in row]
    assert all(b['table']['row'] == index // 3 for index, b in enumerate(result['blocks']))
    assert all(b['table']['header'] for b in result['blocks'][:3])
    assert all(not b['table']['header'] for b in result['blocks'][3:])


def test_ambiguous_short_columns_keep_text_and_disclose_uncertain_table():
    def draw(c):
        for row in range(3):
            c.drawString(50, 720 - row * 25, f'Alpha {row}')
            c.drawString(350, 720 - row * 25, f'Beta {row}')
    result = pdfs.parse_pdf(make_pdf(draw))
    assert len(result['blocks']) >= 2
    assert not any(n['type'] == 'table' for n in result['document']['body'])
    assert any(i['code'] == 'pdf_table_uncertain' for i in result['document']['issues'])


def test_mixed_pdf_retains_scanned_page_without_rejecting_native_text():
    def draw(c):
        c.drawString(50, 750, 'Native payment clause: 1000.')
        c.showPage()
        c.drawImage(ImageReader(scan_image()), 0, 0, width=600, height=800)
    raw = make_pdf(draw)
    fingerprint = hashlib.sha256(raw).hexdigest()
    result = pdfs.parse_pdf(raw)
    assert 'Native payment' in result['blocks'][0]['text']
    assert len(result['document']['pages']) == 2
    assert any(i['code'] == 'pdf_ocr_pending' and i['page'] == 2 for i in result['document']['issues'])
    assert any(a['page'] == 2 for a in result['assets'])
    assert hashlib.sha256(raw).hexdigest() == fingerprint
    assert all('data_b64' not in a and 'text' not in a for a in result['assets'])


def test_wholly_scanned_pdf_has_zero_reviewable_blocks_and_source_preview():
    raw = make_pdf(lambda c: c.drawImage(ImageReader(scan_image()), 0, 0, width=600, height=800))
    result = pdfs.parse_pdf(raw)
    assert result['blocks'] == []
    assert result['document']['body'][0]['type'] == 'image'
    assert any(i['code'] == 'pdf_ocr_pending' for i in result['document']['issues'])
    content, media = pdfs.render_pdf_asset(raw, result['assets'][0], max_pixels=120000)
    with Image.open(io.BytesIO(content)) as image:
        assert image.width * image.height <= 120000
        assert image.getextrema()[0][0] < 250
    assert media == 'image/png'


def test_ocr_tables_replace_missing_scan_text_without_duplicate_native(monkeypatch):
    raw = make_pdf(lambda c: c.drawImage(ImageReader(scan_image()), 0, 0, width=600, height=800))
    def recognize(data, pages, **kwargs):
        assert data == raw and pages == [1]
        return {'status': 'complete', 'pages': [{'number': 1, 'width': 600, 'height': 800,
                 'items': [{'type': 'paragraph', 'text': 'Payment clause', 'bbox': [40, 50, 300, 70]},
                           {'type': 'table', 'bbox': [40, 90, 400, 130], 'cells': [
                               {'row': 0, 'col': 0, 'row_span': 1, 'col_span': 1, 'text': 'Amount', 'bbox': [40, 90, 200, 130]},
                               {'row': 0, 'col': 1, 'row_span': 1, 'col_span': 1, 'text': '1000', 'bbox': [200, 90, 400, 130]}]}]}],
                'issues': [ocr._issue('ocr_review_required')]}
    monkeypatch.setattr(ocr, 'recognize_pdf_pages', recognize)
    result = pdfs.parse_pdf(raw)
    assert [b['text'] for b in result['blocks']] == ['Payment clause', 'Amount', '1000']
    assert sum(n['type'] == 'table' for n in result['document']['body']) == 1
    assert not any(i['code'] == 'pdf_ocr_pending' for i in result['document']['issues'])


def test_ocr_result_with_empty_table_is_not_a_reviewed_scan(monkeypatch):
    raw = make_pdf(lambda c: c.drawImage(ImageReader(scan_image()), 0, 0, width=600, height=800))
    monkeypatch.setattr(ocr, 'recognize_pdf_pages', lambda *a, **kw: {'status': 'complete', 'pages': [
        {'number': 1, 'items': [{'type': 'table', 'bbox': [0, 0, 100, 100], 'cells': [
            {'row': 0, 'col': 0, 'row_span': 1, 'col_span': 1, 'text': ''}]}]}], 'issues': []})
    result = pdfs.parse_pdf(raw)
    assert not result['blocks']
    assert any(i['code'] == 'pdf_ocr_pending' for i in result['document']['issues'])


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
def test_rotated_nonzero_media_and_crop_use_same_render_coordinates(rotation):
    raw = make_pdf(lambda c: c.drawString(100, 500, 'LOCATION TARGET'))
    reader, writer = PdfReader(io.BytesIO(raw)), PdfWriter()
    page = reader.pages[0]
    page.mediabox = RectangleObject([20, 30, 620, 830])
    page.cropbox = RectangleObject([50, 100, 550, 750])
    page.rotate(rotation)
    writer.add_page(page)
    stream = io.BytesIO(); writer.write(stream)
    raw = stream.getvalue()
    result = pdfs.parse_pdf(raw)
    info = result['document']['pages'][0]
    assert (info['width'], info['height']) == pytest.approx((600, 800) if rotation % 180 == 0 else (800, 600))
    assert result['blocks']
    block = result['blocks'][0]
    x0, y0, x1, y1 = block['bbox']
    assert 0 <= x0 < x1 <= info['width'] and 0 <= y0 < y1 <= info['height']
    # The box should actually contain ink in a renderer, not just look plausible.
    image, _ = pdfs.render_pdf_asset(raw, {'page': 1, 'bbox': block['bbox']})
    with Image.open(io.BytesIO(image)) as picture:
        assert picture.convert('L').getextrema()[0] < 100
    selected, geometry = pdfs.prepare_pdf_for_ocr(raw, [1])
    selected_page = PdfReader(io.BytesIO(selected)).pages[0]
    assert float(selected_page.mediabox.left) == pytest.approx(0)
    assert float(selected_page.mediabox.bottom) == pytest.approx(0)
    assert float(selected_page.mediabox.width) == pytest.approx(geometry[0]['crop_bbox'][2] - geometry[0]['crop_bbox'][0])


def test_small_picture_not_ocrd_but_coverage_is_explicit(monkeypatch):
    def draw(c):
        c.drawString(50, 750, 'Ordinary native clause.')
        c.drawImage(ImageReader(scan_image()), 50, 600, width=25, height=25)
    monkeypatch.setattr(ocr, 'recognize_image', lambda *a, **k: pytest.fail('decorative image invoked OCR'))
    result = pdfs.parse_pdf(make_pdf(draw))
    assert len(result['assets']) == 1
    assert any(i['code'] == 'pdf_image_not_reviewed' for i in result['document']['issues'])


def test_mixed_image_ocr_is_linked_only_to_image_and_keeps_cell_relationships(monkeypatch):
    def draw(c):
        c.drawString(50, 750, 'Native clause remains exactly once.')
        c.drawImage(ImageReader(scan_image()), 50, 200, width=300, height=400)
    monkeypatch.setattr(ocr, 'ocr_status', lambda: {'configured': True})
    monkeypatch.setattr(ocr, 'recognize_image', lambda *a, **k: {
        'status': 'complete', 'width': 600, 'height': 800,
        'blocks': [{'text': 'Account', 'bbox': [20, 20, 100, 40], 'kind': 'ocr',
                    'table': {'id': 'table-1', 'cell_id': 'cell-1', 'row': 0, 'col': 0, 'row_span': 1, 'col_span': 1}}],
        'issues': [ocr._issue('ocr_review_required')]})
    result = pdfs.parse_pdf(make_pdf(draw))
    block = next(b for b in result['blocks'] if b['text'] == 'Account')
    assert block['table']['id'].startswith('pdf-image-')
    image = next(n for n in result['document']['body'] if n['type'] == 'image')
    assert image['block_ids'] == [block['id']]
    assert all(n.get('block_id') != block['id'] for n in result['document']['body'])


def test_invalid_pdf_and_oversized_page_count_remain_bounded():
    with pytest.raises(ValueError):
        pdfs.parse_pdf(b'not PDF')
    writer = PdfWriter()
    for _ in range(101):
        writer.add_blank_page(width=100, height=100)
    stream = io.BytesIO(); writer.write(stream)
    with pytest.raises(ValueError, match='100'):
        pdfs.parse_pdf(stream.getvalue())


def test_table_detector_failure_keeps_usable_native_paragraph(monkeypatch):
    import pdfplumber
    def fail(*args, **kwargs):
        raise ValueError('malformed table geometry')
    monkeypatch.setattr(pdfplumber.page.Page, 'find_tables', fail)
    result = pdfs.parse_pdf(make_pdf(lambda c: c.drawString(50, 750, 'Usable native clause.')))
    assert result['blocks'][0]['text'] == 'Usable native clause.'
    assert any(i['code'] == 'pdf_table_unavailable' for i in result['document']['issues'])


def test_oversized_embedded_bitmap_is_rejected_before_renderer_decodes_it(monkeypatch):
    import pypdfium2
    from pypdf.generic import NumberObject, NameObject
    raw = make_pdf(lambda c: c.drawImage(ImageReader(scan_image()), 0, 0, width=600, height=800))
    reader, writer = PdfReader(io.BytesIO(raw)), PdfWriter()
    page = writer.add_page(reader.pages[0])
    image = next(iter(page['/Resources']['/XObject'].values())).get_object()
    image[NameObject('/Width')] = NumberObject(100000)
    image[NameObject('/Height')] = NumberObject(100000)
    stream = io.BytesIO(); writer.write(stream)
    monkeypatch.setattr(pypdfium2, 'PdfDocument', lambda *a, **k: pytest.fail('huge source image reached decoder'))
    with pytest.raises(ValueError, match='资源上限'):
        pdfs.render_pdf_asset(stream.getvalue(), {'page': 1, 'bbox': [0, 0, 600, 800]})


def test_dense_crossing_geometry_does_not_allocate_quadratic_intersections(monkeypatch):
    import pdfplumber
    edges = [{'orientation': 'h'}] * 150 + [{'orientation': 'v'}] * 150
    monkeypatch.setattr(pdfplumber.page.Page, 'edges', property(lambda _: edges))
    monkeypatch.setattr(pdfplumber.page.Page, 'find_tables', lambda *a, **k: pytest.fail('dense geometry entered table finder'))
    result = pdfs.parse_pdf(make_pdf(lambda c: c.drawString(50, 750, 'Native clause stays available.')))
    assert result['blocks'][0]['text'] == 'Native clause stays available.'
    assert any(i['code'] == 'pdf_table_geometry_limit' for i in result['document']['issues'])
