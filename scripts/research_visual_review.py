"""Same fixture/viewport visual review. No live APIs, user account or model credit.

Run with --baseline --build PATH to capture the pre-refinement production build.
The baseline does not assert newly added citation behavior.
"""
import argparse
import json
import os
import shutil
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--build', type=Path, default=ROOT / 'frontend/build')
parser.add_argument('--out', type=Path, default=ROOT / 'ui-artifacts/refined')
parser.add_argument('--baseline', action='store_true')
args = parser.parse_args()
args.out.mkdir(parents=True, exist_ok=True)

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(args.build), **kw)
    def do_GET(self):
        if not (args.build / urlparse(self.path).path.lstrip('/')).is_file():
            self.path = '/index.html'
        super().do_GET()
    def log_message(self, *a):
        pass

server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
base = f'http://127.0.0.1:{server.server_port}'
USER = {'id': 'visual-fixture', 'username': 'Researcher', 'email': 'research@example.test', 'role': 'user', 'plan': 'free'}
DOC = {'id': 'visual-report', 'title': 'Sustainability report 2025', 'source': 'Sustainability report 2025.pdf', 'domain': 'environmental', 'source_type': 'pdf', 'chunk_count': 2, 'relationship_count': 0}
SOURCES = [
    {'chunk_id': 'report-1-p12', 'document_id': DOC['id'], 'document_title': DOC['title'], 'source': DOC['source'], 'page': 12, 'text': 'Our 2030 emissions target covers Scope 1 and Scope 2. Progress is measured against a 2020 baseline. Scope 3 emissions are not included in this target. This boundary applies to the reduction commitment discussed in this section and should not be interpreted as a claim that value-chain emissions are immaterial. The target will be reviewed as the inventory develops.'},
    {'chunk_id': 'report-1-p18', 'document_id': DOC['id'], 'document_title': DOC['title'], 'source': DOC['source'], 'page': 18, 'text': 'We are developing an inventory of supply-chain emissions. A separate Scope 3 reduction target has not yet been established. Reporting coverage and data collection methods are expected to evolve as more suppliers contribute information.'},
]
QUESTION = 'Does the emissions target include Scope 3?'
ANSWER = '### What the target covers\nThe report’s 2030 target covers **Scope 1 and Scope 2**, measured against a 2020 baseline. It does not include Scope 3. [report-1-p12]\n\n### What is still missing\nThe company is developing its supply-chain inventory, but has not established a separate Scope 3 reduction target. [report-1-p18]\n\nThis is a boundary on the disclosed target—not evidence that supply-chain emissions are falling.'
SESSION = {'id': 'visual-session', 'title': 'Climate target coverage', 'mode': 'ask', 'updated_at': '2026-09-07T11:00:00Z', 'message_count': 2}
MESSAGES = [{'role': 'user', 'content': QUESTION, 'timestamp': '2026-09-07T11:00:00Z'}, {'role': 'assistant', 'content': ANSWER, 'timestamp': '2026-09-07T11:00:01Z', 'data': {'sources': SOURCES, 'backend': 'deepseek_deep', 'reasoningMode': 'deep'}}]
MODEL = {'provider': 'deepseek', 'model': 'deepseek-v4-pro', 'configured': True, 'connectivity_verified': False, 'modes': {'flash': {'model': 'deepseek-v4-pro', 'configured': True, 'thinking': False}, 'deep': {'model': 'deepseek-v4-pro', 'configured': True, 'thinking': True}}}
results, errors = [], []
def check(name, ok):
    results.append({'check': name, 'passed': bool(ok)})
    if not ok: raise AssertionError(name)
def route_request(route):
    url = urlparse(route.request.url)
    if url.hostname not in ('127.0.0.1', 'localhost'):
        route.abort(); return
    if url.port == server.server_port:
        route.continue_(); return
    path = url.path
    if path == '/auth/me': data = {'user': USER}
    elif path == '/models/status': data = MODEL
    elif path == '/documents': data = {'documents': [DOC]}
    elif path.startswith('/documents/'): data = {'document': DOC}
    elif path == '/chat/sessions': data = {'sessions': [SESSION]}
    elif path.startswith('/chat/sessions/'): data = {'session': SESSION, 'messages': MESSAGES}
    else: data = {}
    route.fulfill(status=204 if route.request.method == 'OPTIONS' else 200, content_type='application/json', body=json.dumps(data), headers={'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*', 'Access-Control-Allow-Methods': '*'})

def shot(page, name):
    page.screenshot(path=str(args.out / name), animations='disabled')

try:
    with sync_playwright() as p:
        options = {'headless': True}
        if os.getenv('CHROMIUM_PATH'): options['executable_path'] = os.environ['CHROMIUM_PATH']
        browser = p.chromium.launch(**options)
        context = browser.new_context(viewport={'width': 1440, 'height': 1000}, reduced_motion='reduce')
        context.route('**/*', route_request)
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(base, wait_until='networkidle')
        check('Homepage loads', page.locator('h1').count() == 1)
        shot(page, 'home-desktop.png')
        page.screenshot(path=str(args.out / 'home-full.png'), full_page=True, animations='disabled')
        if not args.baseline:
            check('Decorative canvas removed', page.locator('canvas.research-globe').count() == 0)
            page.get_by_role('button', name='Hide sources', exact=True).click()
            expect(page.locator('#preview-evidence')).to_have_count(0)
            page.get_by_role('button', name='View source 2:', exact=False).click()
            expect(page.locator('#preview-evidence .is-selected')).to_have_attribute('data-source-id', 'example-2025-18')
            check('Homepage citation opens its exact passage', True)
        page.evaluate('(u)=>{localStorage.setItem("token","visual-fixture");localStorage.setItem("user",JSON.stringify(u));localStorage.setItem("causalgraph_agent_current_session_id_v1","visual-session")}', USER)
        page.goto(base + '/agent', wait_until='networkidle')
        expect(page.get_by_text('What the target covers', exact=True)).to_be_visible()
        # Close the existing process panel in both versions for the same answer state.
        close = page.get_by_role('button', name='Close process drawer', exact=True)
        if close.count(): close.last.click()
        page.locator('.research-conversation').evaluate('(e)=>e.scrollTop=0')
        shot(page, 'answer-desktop.png')
        if not args.baseline:
            check('No redundant open-desk CTA on the desk', page.get_by_role('link', name='Open Research Desk', exact=True).count() == 0)
            page.get_by_role('button', name='View source 1:', exact=False).click()
            expect(page.locator('.research-evidence-drawer .is-selected')).to_have_attribute('data-source-id', 'report-1-p12')
            expect(page.get_by_text('Page 12', exact=True)).to_be_visible()
            check('Real answer opens the corresponding source', True)
            paragraph = page.locator('.research-evidence-drawer blockquote').first
            check('Full excerpt is not line-clamped', paragraph.evaluate('(e)=>getComputedStyle(e).webkitLineClamp') in ('none', '0'))
        else:
            page.get_by_role('button', name='View all evidence', exact=False).click()
        shot(page, 'evidence-desktop.png')
        if not args.baseline:
            page.keyboard.press('Escape')
            expect(page.locator('.research-evidence-drawer')).to_have_count(0)
            check('Escape closes evidence and restores citation focus', page.get_by_role('button', name='View source 1:', exact=False).evaluate('(e)=>document.activeElement===e'))
            check('Citation interactions preserve the answer', page.locator('.research-answer').inner_text().find('What is still missing') >= 0)
        for width in (390, 768, 1024, 1280):
            page.set_viewport_size({'width': width, 'height': 900})
            page.goto(base, wait_until='networkidle')
            check(f'Home fits {width}px', page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
            if width == 390: shot(page, 'home-mobile.png')
            page.goto(base + '/agent', wait_until='networkidle')
            expect(page.get_by_text('What the target covers', exact=True)).to_be_visible()
            close = page.get_by_role('button', name='Close process drawer', exact=True)
            if close.count(): close.last.click()
            check(f'Answer fits {width}px', page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
            if not args.baseline:
                page.get_by_role('button', name='View source 2:', exact=False).click()
                expect(page.locator('.research-evidence-drawer .is-selected')).to_have_attribute('data-source-id', 'report-1-p18')
                check(f'Selected source fits {width}px', page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
                if width == 390:
                    shot(page, 'evidence-mobile.png')
                    page.get_by_role('button', name='Close process drawer').last.focus()
                    page.keyboard.press('Tab')
                    check('Mobile keyboard focus remains inside evidence', page.evaluate('!!document.activeElement.closest(".research-evidence-drawer")'))
                page.keyboard.press('Escape')
        check('No browser page errors', not errors)
        browser.close()
finally:
    server.shutdown()
    (args.out/'visual-results.json').write_text(json.dumps({'fixture': 'synthetic excerpts only; same content and viewport for before/after', 'baseline': args.baseline, 'checks': results, 'errors': errors}, indent=2))
print(f'{len(results)} visual/interaction checks passed. Screenshots: {args.out}')
