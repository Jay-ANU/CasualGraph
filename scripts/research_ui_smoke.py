"""Browser smoke verification against the production build; APIs are mock fixtures."""
import json
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / 'frontend' / 'build'
OUT = ROOT / 'ui-artifacts'
OUT.mkdir(exist_ok=True)

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BUILD), **kwargs)
    def do_GET(self):
        if not (BUILD / self.path.split('?')[0].lstrip('/')).is_file():
            self.path = '/index.html'
        super().do_GET()
    def log_message(self, *args):
        pass

server = ThreadingHTTPServer(('127.0.0.1', 4173), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
USER = {'id': 'ui-smoke', 'username': 'Researcher', 'email': 'researcher@example.test', 'role': 'user', 'plan': 'free'}
MODEL = {'provider': 'deepseek', 'model': 'deepseek-v4-pro', 'configured': True, 'connectivity_verified': False, 'modes': {'flash': {'model': 'deepseek-v4-pro', 'configured': True, 'thinking': False}, 'deep': {'model': 'deepseek-v4-pro', 'configured': True, 'thinking': True}}}
SESSION = {'id': 'smoke-session', 'title': 'Research question', 'selected_document_id': '', 'mode': 'ask', 'created_at': '2026-09-07T10:00:00Z', 'updated_at': '2026-09-07T10:00:00Z', 'message_count': 0}
SOURCE = {'chunk_id': 'report-1-p12', 'document_id': 'report-1', 'document_title': 'UI smoke test report', 'source': 'UI smoke test report', 'text': 'Synthetic browser fixture: this paragraph exists solely for testing citations.', 'score': 0.91, 'relevance_score': 0.91, 'page': 12}
ANSWER = 'This is a **browser test response**, not a live model answer. The citation opens the test evidence [report-1-p12].'
state = {'model': 'configured', 'documents': []}
requests = []
results = []
errors = []

def api(route):
    req = route.request
    path = urlparse(req.url).path
    requests.append({'method': req.method, 'path': path, 'body': req.post_data})
    data, code = {}, 200
    if req.method == 'OPTIONS':
        route.fulfill(status=204, headers={'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*', 'Access-Control-Allow-Methods': '*'})
        return
    if path == '/auth/me':
        data = {'user': USER}
    elif path == '/models/status':
        data = json.loads(json.dumps(MODEL))
        if state['model'] == 'error':
            code, data = 503, {'detail': 'Synthetic unavailable response'}
        elif state['model'] == 'missing':
            data['configured'] = False
            for mode in data['modes'].values():
                mode['configured'] = False
    elif path == '/documents':
        data = {'documents': state['documents']}
    elif path == '/chat/sessions':
        data = {'sessions': []} if req.method == 'GET' else {'session': SESSION}
    elif path.startswith('/chat/sessions/'):
        data = {'session': SESSION, 'messages': []}
    elif path == '/rag/ask/stream':
        frames = [
            {'type': 'meta', 'payload': {'mode': 'ask', 'stream_stage': 'context_ready', 'sources': [SOURCE]}},
            {'type': 'token', 'text': ANSWER[:40]},
            {'type': 'token', 'text': ANSWER[40:]},
            {'type': 'done', 'payload': {'answer': ANSWER, 'backend': 'deepseek_deep', 'sources': [SOURCE], 'mode': 'ask', 'reasoning_mode': 'deep', 'retrieval_strategy': 'hybrid', 'partial': False}},
        ]
        route.fulfill(status=200, content_type='text/event-stream', body=''.join('data: ' + json.dumps(f) + '\n\n' for f in frames), headers={'Access-Control-Allow-Origin': '*'})
        return
    elif path.startswith('/documents/'):
        data = next((d for d in state['documents'] if d['id'] == path.rsplit('/', 1)[-1]), {})
    route.fulfill(status=code, content_type='application/json', body=json.dumps(data), headers={'Access-Control-Allow-Origin': '*'})

def check(label, ok, detail=None):
    entry = {'check': label, 'passed': bool(ok)}
    if detail is not None:
        entry['detail'] = detail
    results.append(entry)
    print(json.dumps(entry), flush=True)

def overflow(page):
    return page.evaluate('({scroll:document.documentElement.scrollWidth,viewport:innerWidth})')

def no_overflow(page, label):
    dims = overflow(page)
    check(label, dims['scroll'] <= dims['viewport'], dims)

try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
        context = browser.new_context(viewport={'width': 1440, 'height': 1000}, device_scale_factor=1, reduced_motion='reduce')
        context.route('http://127.0.0.1:8000/**', api)
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto('http://127.0.0.1:4173/', wait_until='networkidle')
        check('Home heading', page.get_by_role('heading', name='From disclosures to clearer decisions.').count() == 1)
        check('Home action empty disabled', page.get_by_role('button', name='Start research', exact=True).is_disabled())
        no_overflow(page, 'Desktop homepage no horizontal overflow')
        page.screenshot(path=str(OUT / 'home-desktop.png'), full_page=True)
        page.get_by_role('textbox', name='Ask a research question').fill('Check climate evidence')
        page.get_by_role('button', name='Start research', exact=True).click()
        page.wait_for_url('**/login')
        check('Unauthenticated research opens login', '/login' in page.url)
        page.evaluate('(u)=>{localStorage.setItem("token","ui-smoke-token");localStorage.setItem("user",JSON.stringify(u))}', USER)
        page.goto('http://127.0.0.1:4173/agent', wait_until='networkidle')
        page.get_by_text('Fast answers · configured', exact=True).wait_for()
        check('DeepSeek status displayed', page.get_by_text('DeepSeek V4 Pro', exact=True).count() == 1)
        check('Empty library not populated with sample', page.get_by_text('Start with a report, or ask a general question', exact=True).count() == 1)
        no_overflow(page, 'Desktop workspace no horizontal overflow')
        page.screenshot(path=str(OUT / 'workspace-desktop.png'), full_page=True)
        page.get_by_role('button', name='Deep', exact=True).click()
        check('Deep mode status follows toggle', page.get_by_text('Deep reasoning · configured', exact=True).count() == 1)
        page.locator('.research-model summary').click()
        check('Status disclaims live credit check', page.get_by_text('Configuration detected, not a live connection or credit check.', exact=False).is_visible())
        page.locator('.research-model summary').click()
        page.locator('.research-starters > button').first.click()
        question = page.get_by_role('textbox', name='Research question', exact=True)
        check('Starter fills and focuses question', bool(question.input_value()) and question.evaluate('(e)=>e===document.activeElement'))
        page.get_by_role('button', name='View library').click()
        check('Library entry navigates', page.locator('.research-welcome').count() == 0)
        page.goto('http://127.0.0.1:4173/agent', wait_until='networkidle')
        page.get_by_role('button', name='Bring your own evidence', exact=False).click()
        check('Upload entry navigates', page.locator('.research-welcome').count() == 0)
        page.goto('http://127.0.0.1:4173/agent', wait_until='networkidle')
        page.get_by_role('button', name='Deep', exact=True).click()
        page.get_by_role('textbox', name='Research question', exact=True).fill('Explain this test citation')
        page.get_by_role('button', name='Send', exact=True).click()
        page.get_by_text('browser test response', exact=False).first.wait_for(timeout=10000)
        check('Streamed answer rendered', page.get_by_text('browser test response', exact=False).count() > 0)
        sent = [r for r in requests if r['path'] == '/rag/ask/stream']
        check('Deep mode included in request', bool(sent) and json.loads(sent[-1]['body']).get('reasoning_mode') == 'deep')
        page.screenshot(path=str(OUT / 'workspace-answer.png'), full_page=True)
        for mode in ['missing', 'error']:
            state['model'] = mode
            page.goto('http://127.0.0.1:4173/agent', wait_until='networkidle')
            expected = 'Server API key required' if mode == 'missing' else 'Model status unavailable'
            page.get_by_text(expected, exact=True).wait_for()
            check(f'Model {mode} state displayed', True)
            if mode == 'error':
                state['model'] = 'configured'
                page.get_by_role('button', name='Retry model status').click()
                page.get_by_text('DeepSeek V4 Pro', exact=True).wait_for()
                check('Model retry recovers', True)
        for width, height in [(390, 844), (768, 1024), (1024, 900), (1280, 900)]:
            page.set_viewport_size({'width': width, 'height': height})
            page.goto('http://127.0.0.1:4173/', wait_until='networkidle')
            no_overflow(page, f'Home {width}px no horizontal overflow')
            if width == 390:
                page.screenshot(path=str(OUT / 'home-mobile.png'), full_page=True)
                page.get_by_role('button', name='Open menu', exact=True).click()
                check('Mobile menu opens', page.get_by_role('link', name='Research', exact=True).is_visible())
            page.goto('http://127.0.0.1:4173/agent', wait_until='networkidle')
            no_overflow(page, f'Workspace {width}px no horizontal overflow')
            if width == 390:
                page.screenshot(path=str(OUT / 'workspace-mobile.png'), full_page=True)
        check('No browser JavaScript errors', not errors, errors)
        context.close()
        browser.close()
except Exception as exc:
    check('Browser run completed', False, str(exc))
    try:
        page.screenshot(path=str(OUT / 'failure.png'), full_page=True)
    except Exception:
        pass
finally:
    (OUT / 'browser-results.json').write_text(json.dumps({'backend': 'mock fixtures only', 'results': results, 'requests': requests}, indent=2))
    server.shutdown()

if any(not result['passed'] for result in results):
    raise SystemExit('Browser verification failed; see ui-artifacts/browser-results.json')
