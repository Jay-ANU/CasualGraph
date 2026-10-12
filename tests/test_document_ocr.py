"""Private OCR protocol, fault states and real source-page selection."""
import asyncio
import io
import json

import httpx
import pytest
from PIL import Image
from pypdf import PdfReader, PdfWriter

from legal import document_ocr as ocr


TOKEN = 'test-parser-token-with-at-least-32-characters'


@pytest.fixture(autouse=True)
def config(monkeypatch):
    monkeypatch.setenv('LEGAL_DOCUMENT_PARSER_URL', 'http://127.0.0.1:8090')
    monkeypatch.setenv('LEGAL_DOCUMENT_PARSER_TOKEN', TOKEN)


def picture():
    stream = io.BytesIO()
    Image.new('RGB', (400, 200), 'white').save(stream, format='PNG')
    return stream.getvalue()


def response_payload():
    return {'version': 1, 'status': 'complete', 'pages': [{'number': 1, 'width': 200, 'height': 100,
            'items': [{'type': 'paragraph', 'text': 'Payment in 30 days', 'bbox': [10, 10, 150, 25]},
                      {'type': 'table', 'bbox': [10, 40, 180, 90], 'cells': [
                          {'row': 0, 'col': 0, 'row_span': 1, 'col_span': 2, 'text': 'Merged title',
                           'bbox': [10, 40, 180, 60], 'header': True},
                          {'row': 1, 'col': 0, 'row_span': 1, 'col_span': 1, 'text': 'Amount', 'bbox': [10, 60, 90, 90]},
                          {'row': 1, 'col': 1, 'row_span': 1, 'col_span': 1, 'text': '1000', 'bbox': [90, 60, 180, 90]}]}]}]}


def transport(monkeypatch, handler):
    original = httpx.AsyncClient
    def client(**kwargs):
        assert kwargs['follow_redirects'] is False and kwargs['trust_env'] is False
        return original(transport=httpx.MockTransport(handler), **kwargs)
    monkeypatch.setattr(httpx, 'AsyncClient', client)


def test_image_request_auth_bounds_and_table_cells(monkeypatch):
    raw = picture()
    def handler(request):
        assert request.url == 'http://127.0.0.1:8090/v1/parse'
        assert request.content == raw
        assert request.headers['authorization'] == 'Bearer ' + TOKEN
        assert request.headers['x-parser-protocol'] == '1'
        return httpx.Response(200, json=response_payload())
    transport(monkeypatch, handler)
    result = ocr.recognize_image(raw, 'image/png')
    assert result['status'] == 'complete'
    assert result['blocks'][0]['bbox'] == [20, 20, 300, 50]
    cells = [b for b in result['blocks'] if b.get('table')]
    assert len(cells) == 3 and cells[0]['table']['col_span'] == 2
    assert cells[0]['table']['header'] is True
    assert len({b['table']['cell_id'] for b in cells}) == 3
    assert 'ocr_review_required' in {i['code'] for i in result['issues']}


@pytest.mark.parametrize('url', ['https://example.com', 'http://10.0.0.1', 'https://parser.internal/?secret=1',
                               'https://user:pass@parser.internal', 'ftp://127.0.0.1', 'http://127.0.0.1/path'])
def test_public_or_unsafe_endpoints_never_receive_source(monkeypatch, url):
    monkeypatch.setenv('LEGAL_DOCUMENT_PARSER_URL', url)
    transport(monkeypatch, lambda _: pytest.fail('unapproved endpoint received document'))
    result = ocr.recognize_image(picture(), 'image/png')
    assert result['status'] == 'pending'
    assert result['issues'][0]['code'] == 'ocr_configuration_invalid'
    assert url not in json.dumps(ocr.ocr_status())


def test_unconfigured_means_no_network_no_false_complete(monkeypatch):
    monkeypatch.delenv('LEGAL_DOCUMENT_PARSER_URL')
    monkeypatch.delenv('LEGAL_DOCUMENT_PARSER_TOKEN')
    transport(monkeypatch, lambda _: pytest.fail('unconfigured worker received document'))
    result = ocr.recognize_image(picture(), 'image/png')
    assert not ocr.ocr_status()['configured']
    assert result['status'] == 'pending' and not result['blocks']


@pytest.mark.parametrize('status', [301, 401, 429, 500, 503])
def test_worker_failures_and_redirects_remain_generic(monkeypatch, status):
    transport(monkeypatch, lambda _: httpx.Response(status, headers={'Location': 'https://external.invalid'},
                                                    text='secret document phrase ' + TOKEN))
    result = ocr.recognize_image(picture(), 'image/png')
    assert result['status'] == 'pending'
    assert TOKEN not in json.dumps(result) and 'secret document' not in json.dumps(result)


def test_timeout_and_shared_budget_prevent_unbounded_image_calls(monkeypatch):
    calls = []
    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout('secret exception text')
    transport(monkeypatch, handler)
    budget = ocr.OCRBudget(max_requests=1)
    assert ocr.recognize_image(picture(), 'image/png', budget=budget)['issues'][0]['code'] == 'ocr_timeout'
    assert ocr.recognize_image(picture(), 'image/png', budget=budget)['issues'][0]['code'] == 'ocr_budget_exceeded'
    assert len(calls) == 1


def test_whole_request_deadline_includes_waiting_for_response_headers(monkeypatch):
    async def handler(request):
        await asyncio.sleep(1)
        return httpx.Response(200, json=response_payload())
    transport(monkeypatch, handler)
    result = ocr.recognize_image(picture(), 'image/png', budget=ocr.OCRBudget(seconds=.03))
    assert result['issues'][0]['code'] == 'ocr_timeout'


@pytest.mark.parametrize('mutate', [
    lambda d: d.update(version=2),
    lambda d: d['pages'][0].update(width=float('inf')),
    lambda d: d['pages'][0]['items'][0].update(bbox=[10, 10, 5000, 20]),
    lambda d: d['pages'][0]['items'][1]['cells'][0].update(col_span=10000),
    lambda d: d['pages'][0]['items'][1]['cells'][1].update(row=0),
])
def test_invalid_worker_structure_is_not_trusted(monkeypatch, mutate):
    payload = response_payload(); mutate(payload)
    transport(monkeypatch, lambda _: httpx.Response(200, content=json.dumps(payload).encode(),
                                                    headers={'Content-Type': 'application/json'}))
    result = ocr.recognize_image(picture(), 'image/png')
    assert result['status'] == 'pending'
    assert result['issues'][0]['code'] == 'ocr_invalid_response'


def test_oversized_response_is_rejected_before_json_parse(monkeypatch):
    monkeypatch.setattr(ocr, 'MAX_RESPONSE_BYTES', 100)
    transport(monkeypatch, lambda _: httpx.Response(200, json=response_payload()))
    assert ocr.recognize_image(picture(), 'image/png')['issues'][0]['code'] == 'ocr_invalid_response'


def test_pdf_request_contains_only_selected_page_and_remaps_page_numbers(monkeypatch):
    writer = PdfWriter()
    for size in [(500, 700), (200, 100), (300, 500)]:
        writer.add_blank_page(width=size[0], height=size[1])
    stream = io.BytesIO(); writer.write(stream)
    def handler(request):
        selected = PdfReader(io.BytesIO(request.content))
        assert len(selected.pages) == 1 and float(selected.pages[0].mediabox.width) == 200
        return httpx.Response(200, json=response_payload())
    transport(monkeypatch, handler)
    result = ocr.recognize_pdf_pages(stream.getvalue(), [2])
    assert result['pages'][0]['number'] == 2
    assert result['pages'][0]['width'] == 200


def test_missing_worker_page_is_partial_not_complete(monkeypatch):
    payload = response_payload(); payload['pages'] = []
    transport(monkeypatch, lambda _: httpx.Response(200, json=payload))
    result = ocr.recognize_image(picture(), 'image/png')
    assert result['status'] == 'partial' and not result['blocks']
