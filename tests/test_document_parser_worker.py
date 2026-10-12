"""Worker adapter/auth contracts; no public service, model download or raw log."""
import asyncio
import io
import multiprocessing
import os
import threading
import time
from types import SimpleNamespace

import pytest
import httpx
from fastapi.testclient import TestClient
from PIL import Image
from pypdf import PdfWriter

from services.document_parser.app import create_app
from services.document_parser import worker


TOKEN = 'worker-test-token-at-least-thirty-two-characters'


def document_fixture():
    # Mirrors DoclingDocument.export_to_dict(): page maps, JSON references,
    # bottom-origin provenance, furniture, and explicit merged table cells.
    bbox = lambda l, t, r, b: {'l': l, 't': t, 'r': r, 'b': b, 'coord_origin': 'BOTTOMLEFT'}
    prov = lambda box: [{'page_no': 1, 'bbox': box, 'charspan': [0, 20]}]
    return {
        'pages': {'1': {'page_no': 1, 'size': {'width': 200, 'height': 100}}},
        'body': {'children': [{'$ref': '#/texts/0'}, {'$ref': '#/tables/0'}, {'$ref': '#/pictures/0'}]},
        'furniture': {'children': [{'$ref': '#/texts/2'}]},
        'texts': [
            {'self_ref': '#/texts/0', 'text': 'Payment clause', 'prov': prov(bbox(10, 90, 150, 80)), 'children': []},
            {'self_ref': '#/texts/1', 'text': 'DO NOT DUPLICATE CELL', 'prov': prov(bbox(10, 70, 190, 50)), 'children': []},
            {'self_ref': '#/texts/2', 'text': 'Contract footnote', 'prov': prov(bbox(10, 10, 150, 2)), 'children': []},
        ],
        'tables': [{'self_ref': '#/tables/0', 'prov': prov(bbox(10, 70, 190, 50)),
                    'children': [{'$ref': '#/texts/1'}], 'data': {'table_cells': [
                        {'start_row_offset_idx': 0, 'end_row_offset_idx': 1, 'start_col_offset_idx': 0,
                         'end_col_offset_idx': 2, 'row_span': 1, 'col_span': 2, 'text': 'Merged cell',
                         'column_header': True, 'bbox': bbox(10, 70, 190, 50)}]}}],
        'pictures': [{'self_ref': '#/pictures/0', 'prov': prov(bbox(10, 40, 80, 20)), 'children': []}],
        'groups': [],
    }


def test_docling_reference_graph_keeps_furniture_spans_and_coordinate_origin():
    result = worker.normalize_docling_document(document_fixture(), image_size=(400, 200))
    page = result['pages'][0]
    assert (page['width'], page['height']) == (400, 200)
    assert page['items'][0]['bbox'] == [20, 20, 300, 40]
    table = next(i for i in page['items'] if i['type'] == 'table')
    assert table['cells'][0]['col_span'] == 2 and table['cells'][0]['header']
    texts = [i.get('text') for i in page['items']]
    assert 'Contract footnote' in texts and 'DO NOT DUPLICATE CELL' not in texts


def test_missing_source_reference_marks_partial_without_inventing_text():
    fixture = document_fixture()
    fixture['body']['children'].append({'$ref': '#/texts/missing'})
    assert worker.normalize_docling_document(fixture)['status'] == 'partial'


def test_preflight_rejects_huge_pdf_before_rasterization():
    writer, stream = PdfWriter(), io.BytesIO()
    writer.add_blank_page(width=10000, height=10000)
    writer.write(stream)
    with pytest.raises(worker.ParserFailure, match='input_limit'):
        worker.preflight(stream.getvalue(), 'application/pdf')


def test_preflight_image_sets_bounded_size_and_physical_dpi():
    stream = io.BytesIO()
    Image.new('RGB', (2400, 1200), 'white').save(stream, format='PNG')
    normalized, name, original = worker.preflight(stream.getvalue(), 'image/png')
    assert name == 'source.png' and original == (2400, 1200)
    with Image.open(io.BytesIO(normalized)) as image:
        assert image.width <= 1800 and image.height <= 1800
        assert image.info['dpi'][0] == pytest.approx(144, abs=1)


class FakeParser:
    calls = None

    def __init__(self):
        self.calls = []

    def ready(self, timeout=0):
        return True

    def convert(self, data, media_type):
        self.calls.append((data, media_type))
        return worker.normalize_docling_document(document_fixture())

    def close(self):
        pass


def headers(**overrides):
    return {'Authorization': 'Bearer ' + TOKEN, 'Content-Type': 'application/pdf', 'X-Parser-Protocol': '1', **overrides}


def test_worker_defaults_to_deny_even_if_no_token_is_supplied(monkeypatch):
    monkeypatch.delenv('LEGAL_DOCUMENT_PARSER_TOKEN', raising=False)
    parser = FakeParser()
    with TestClient(create_app(parser)) as client:
        assert client.post('/v1/parse', content=b'private bytes', headers=headers()).status_code == 503
        assert client.get('/healthz').status_code == 503
    assert parser.calls == []


@pytest.mark.parametrize('path,extra,status', [
    ('/v1/parse', {'Authorization': 'Bearer wrong'}, 401),
    ('/v1/parse', {'Content-Type': 'application/json'}, 415),
    ('/v1/parse?url=https://external.invalid', {}, 400),
    ('/v1/parse', {'Content-Encoding': 'gzip'}, 415),
    ('/v1/parse', {'X-Parser-Protocol': '2'}, 400),
])
def test_worker_rejects_untrusted_transport_without_invoking_parser(monkeypatch, path, extra, status):
    monkeypatch.setenv('LEGAL_DOCUMENT_PARSER_TOKEN', TOKEN)
    parser = FakeParser()
    with TestClient(create_app(parser)) as client:
        response = client.post(path, content=b'secret text', headers=headers(**extra))
        assert response.status_code == status
        assert 'secret text' not in response.text and TOKEN not in response.text
    assert parser.calls == []


def test_authenticated_binary_route_executes_converter_and_returns_protocol(monkeypatch):
    monkeypatch.setenv('LEGAL_DOCUMENT_PARSER_TOKEN', TOKEN)
    parser = FakeParser()
    with TestClient(create_app(parser)) as client:
        assert client.get('/healthz', headers=headers()).json()['ready']
        response = client.post('/v1/parse', content=b'bounded PDF bytes', headers=headers())
        assert response.status_code == 200 and response.json()['version'] == 1
        assert response.headers['Cache-Control'] == 'no-store'
    assert parser.calls == [(b'bounded PDF bytes', 'application/pdf')]


def test_worker_does_not_expose_backend_exception(monkeypatch):
    monkeypatch.setenv('LEGAL_DOCUMENT_PARSER_TOKEN', TOKEN)
    class Failing(FakeParser):
        def convert(self, *args):
            raise RuntimeError('private filename or contract text ' + TOKEN)
    with TestClient(create_app(Failing())) as client:
        response = client.post('/v1/parse', content=b'private', headers=headers())
        assert response.status_code == 503
        assert TOKEN not in response.text and 'private filename' not in response.text


@pytest.mark.asyncio
async def test_worker_has_one_admitted_body_and_returns_busy_without_queue(monkeypatch):
    monkeypatch.setenv('LEGAL_DOCUMENT_PARSER_TOKEN', TOKEN)
    entered, release = threading.Event(), threading.Event()
    class Blocking(FakeParser):
        def convert(self, *args):
            entered.set()
            release.wait(timeout=2)
            return super().convert(*args)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(Blocking())), base_url='http://test') as client:
        first = asyncio.create_task(client.post('/v1/parse', content=b'one', headers=headers()))
        assert await asyncio.to_thread(entered.wait, 1)
        try:
            second = await client.post('/v1/parse', content=b'two', headers=headers())
            assert second.status_code == 429
        finally:
            release.set()
        assert (await first).status_code == 200


def _unresponsive_converter(connection):
    if os.name == 'posix':
        os.setsid()
    connection.send({'ready': True})
    connection.recv()
    time.sleep(10)


def test_hard_timeout_reaps_real_process_before_restarting(monkeypatch):
    monkeypatch.setenv('PARSER_HARD_TIMEOUT_SECONDS', '1')
    context = multiprocessing.get_context('spawn')
    parent, child = context.Pipe()
    engine = worker.ParserProcess()
    engine._connection = parent
    engine._process = context.Process(target=_unresponsive_converter, args=(child,), daemon=True)
    engine._process.start(); child.close()
    restarts = []
    def restart():
        engine.close()
        restarts.append(True)
    monkeypatch.setattr(engine, 'start', restart)
    try:
        assert engine.ready(5)
        started = time.monotonic()
        with pytest.raises(worker.ParserFailure, match='timeout'):
            engine.convert(b'synthetic input', 'application/pdf')
        assert time.monotonic() - started < 4
        assert restarts == [True] and engine._process is None
    finally:
        engine.close()


def test_sdk_convert_uses_binary_stream_limits_and_export_method(monkeypatch):
    # Exercise the actual worker call contract without importing/loading ML.
    import sys
    class DocumentStream:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
    monkeypatch.setitem(sys.modules, 'docling.datamodel.base_models', SimpleNamespace(DocumentStream=DocumentStream))
    calls = []
    class Converter:
        def convert(self, source, **kwargs):
            calls.append((source, kwargs))
            return SimpleNamespace(status=SimpleNamespace(value='success'),
                                   document=SimpleNamespace(export_to_dict=document_fixture))
    engine = object.__new__(worker.DoclingEngine)
    engine.converter = Converter()
    writer, stream = PdfWriter(), io.BytesIO()
    writer.add_blank_page(width=200, height=100); writer.write(stream)
    assert engine.convert(stream.getvalue(), 'application/pdf')['version'] == 1
    source, kwargs = calls[0]
    assert source.name == 'source.pdf' and source.stream.getvalue() == stream.getvalue()
    assert kwargs == {'max_num_pages': 4, 'max_file_size': 10 * 1024 * 1024, 'raises_on_error': False}


def test_real_docling_core_document_export_contract_when_installed():
    core = pytest.importorskip('docling_core.types.doc', reason='optional lightweight SDK schema check')
    doc = core.DoclingDocument(name='synthetic-contract')
    doc.add_page(page_no=1, size=core.Size(width=600, height=800))
    prov = core.ProvenanceItem(page_no=1, bbox=core.BoundingBox(l=50, t=50, r=550, b=90), charspan=(0, 14))
    doc.add_text(label=core.DocItemLabel.TEXT, text='Payment clause', prov=prov)
    doc.add_table(data=core.TableData(num_rows=1, num_cols=2, table_cells=[
        core.TableCell(text='Merged header', row_span=1, col_span=2,
                       start_row_offset_idx=0, end_row_offset_idx=1,
                       start_col_offset_idx=0, end_col_offset_idx=2, column_header=True)]), prov=prov)
    result = worker.normalize_docling_document(doc.export_to_dict())
    assert result['pages'][0]['items'][0]['text'] == 'Payment clause'
    assert result['pages'][0]['items'][1]['cells'][0]['col_span'] == 2


@pytest.mark.skipif(os.getenv('RUN_PRIVATE_DOCLING_SMOKE') != '1', reason='requires provisioned offline Docling worker models')
def test_real_prewarmed_docling_sdk_smoke():
    # Opt-in deployment gate, run inside the built worker image. It never
    # downloads models and never uses real user documents or a public service.
    from PIL import ImageDraw
    image = Image.new('RGB', (900, 400), 'white')
    ImageDraw.Draw(image).text((30, 60), 'PAYMENT CLAUSE AMOUNT 1000', fill='black', font_size=32)
    stream = io.BytesIO(); image.save(stream, format='PNG')
    result = worker.DoclingEngine().convert(stream.getvalue(), 'image/png')
    text = ' '.join(i.get('text', '') for p in result['pages'] for i in p['items'])
    assert '1000' in text and result['version'] == 1
