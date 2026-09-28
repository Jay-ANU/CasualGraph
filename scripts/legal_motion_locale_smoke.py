"""Browser regression for original legal motion and zh/en UI; synthetic APIs only."""
import functools
import http.server
import json
import os
import re
from pathlib import Path
import sys
import threading
from urllib.parse import urlparse
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from legal.scenarios import catalog
OUT = ROOT / 'ui-artifacts'
OUT.mkdir(exist_ok=True)
class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if not (Path(self.directory) / self.path.lstrip('/').split('?')[0]).is_file():
            self.path = '/index.html'
        super().do_GET()
    def log_message(self, *args): pass

contract = {'id': 'locale-c1', 'name': '中文原件保持不变.txt', 'status': 'ready', 'revision': 1,
    'redaction_version': 2, 'format': 'txt', 'matter_id': 'm1', 'org_id': 'o1', 'warnings': [],
    'replacement_count': 1, 'reviews': [], 'created_at': 1759000000,
    'blocks': [{'id': 'p1', 'text': '【脱敏1】应在验收后支付价款。', 'page': None}]}
calls = []
def api(route):
    req = route.request
    path = urlparse(req.url).path
    calls.append((req.method, path))
    headers = {'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*', 'Access-Control-Allow-Methods': '*'}
    if req.method == 'OPTIONS':
        route.fulfill(status=204, headers=headers); return
    data = {
        '/auth/me': {'user': {'id': 'u1', 'username': 'Synthetic', 'role': 'user', 'plan': 'max'}},
        '/legal/access': {'allowed': True, 'plan': 'max', 'required_plan': 'max'},
        '/legal/workspace': {'matter_id': 'm1', 'org_id': 'o1'},
        '/matters': {'matters': [{'id': 'm1', 'org_id': 'o1', 'name': 'Synthetic matter'}]},
        '/legal/capabilities': {'encryption_configured': True, 'model_configured': True,
            'review_engine_version': 2, 'scenario_catalog': catalog(),
            'review_tiers': ['ultra_fast', 'fast', 'standard', 'deep'],
            'upload_disclosure': {'version': 'original-upload-v1', 'notice': 'Synthetic disclosure', 'storage_region': 'Test'}},
        '/legal/models': {'models': [{'id': 'fixture-model', 'family': 'GPT'}], 'families': ['GPT'], 'default_model': 'fixture-model'},
        '/legal/policies': {'policies': []},
        '/legal/contracts': {'contracts': [contract]},
        '/legal/contracts/locale-c1': contract,
    }.get(path)
    route.fulfill(status=200 if data is not None else 404, headers=headers,
        content_type='application/json', body=json.dumps(data or {'detail': 'Unhandled synthetic request'}, ensure_ascii=False))

contrast_checks = []
def readable_dark_heading(page, selector, background_selector):
    """Guard the actual computed foreground, including inherited opacity."""
    fg, bg, opacity = page.locator(selector).evaluate(r"""(el, background) => {
        const rgb = value => value.match(/[\d.]+/g).slice(0, 3).map(Number);
        let opacity = 1;
        for (let node = el; node; node = node.parentElement) opacity *= Number(getComputedStyle(node).opacity);
        return [rgb(getComputedStyle(el).color), rgb(getComputedStyle(document.querySelector(background)).backgroundColor), opacity];
    }""", background_selector)
    def luminance(rgb):
        linear = [(v / 255 / 12.92 if v / 255 <= .04045 else ((v / 255 + .055) / 1.055) ** 2.4) for v in rgb]
        return sum(v * w for v, w in zip(linear, (.2126, .7152, .0722)))
    top, bottom = sorted((luminance(fg), luminance(bg)), reverse=True)
    ratio = (top + .05) / (bottom + .05)
    assert ratio >= 4.5 and opacity >= .99, (selector, ratio, opacity)
    contrast_checks.append({'selector': selector, 'width': page.viewport_size['width'], 'ratio': round(ratio, 2)})

def layout(page, label):
    for width in (320, 390, 768, 1024, 1440):
        page.set_viewport_size({'width': width, 'height': 900})
        page.evaluate('window.scrollTo(0, 0)')
        # Wait for fonts/layout, not a guessed delay that photographs a fade mid-frame.
        page.evaluate('document.fonts.ready')
        if page.locator('#cg-hero-title').count():
            readable_dark_heading(page, '#cg-hero-title', '.cg-hero')
            readable_dark_heading(page, '#cg-hero-title em', '.cg-hero')
            readable_dark_heading(page, '.cg-home-cta h2', '.cg-home-cta')
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2'), (label, width)
        page.screenshot(path=str(OUT / f'{label}-{width}.png'), full_page=True, animations='disabled')

server = http.server.ThreadingHTTPServer(('127.0.0.1', 4185), functools.partial(Handler, directory=str(ROOT / 'frontend/dist')))
threading.Thread(target=server.serve_forever, daemon=True).start()
BASE = 'http://127.0.0.1:4185'
try:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.getenv('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or None)
        context = browser.new_context(locale='en-US', viewport={'width': 1440, 'height': 1000})
        context.route('http://127.0.0.1:8000/**', api)
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.goto(BASE)
        expect(page.locator('html')).to_have_attribute('lang', 'zh-CN')
        expect(page.locator('#cg-hero-title')).to_contain_text('让每一份合同')
        page.wait_for_function("document.querySelector('video')?.currentTime > 0.15", timeout=15000)
        assert page.locator('video').evaluate('(v) => v.muted && v.loop && v.playsInline')
        page.get_by_role('button', name='暂停动态效果', exact=True).click()
        expect(page.get_by_role('button', name='播放动态效果', exact=True)).to_be_visible()
        time_before = page.locator('video').evaluate('(v) => v.currentTime')
        page.wait_for_timeout(250)
        # A paused video retains its current frame instead of jumping to the poster.
        expect(page.locator('.cg-legal-motion')).to_have_class(re.compile(r'has-frame'))
        assert abs(page.locator('video').evaluate('(v) => v.currentTime') - time_before) < .1
        page.get_by_role('button', name='播放动态效果', exact=True).click()
        page.wait_for_function("!document.querySelector('video').paused")
        page.evaluate("window.scrollTo(0, document.querySelector('#legal-workflow').offsetTop)")
        page.wait_for_function("document.querySelector('video').paused")
        page.evaluate('window.scrollTo(0, 0)')
        page.wait_for_function("!document.querySelector('video').paused")
        page.get_by_role('button', name='暂停动态效果', exact=True).click()
        page.reload()
        page.wait_for_load_state('networkidle')
        assert page.locator('video').get_attribute('src') is None
        page.get_by_role('button', name='播放动态效果', exact=True).click()
        page.wait_for_function("document.querySelector('video').currentTime > .1")
        # An OS preference change takes effect while the page is already open.
        page.emulate_media(reduced_motion='reduce')
        expect(page.locator('video')).to_have_count(0)
        page.emulate_media(reduced_motion='no-preference')
        page.wait_for_function("document.querySelector('video')?.currentTime > .1")
        layout(page, 'motion-home-zh')
        page.get_by_role('button', name='EN', exact=True).click()
        expect(page).to_have_url(BASE + '/en')
        expect(page.locator('html')).to_have_attribute('lang', 'en')
        assert '让每' not in page.locator('#cg-hero-title').inner_text()
        page.locator('.cg-scenario-tabs button').nth(1).click()
        expect(page.locator('.cg-scenario-tabs button').nth(1)).to_have_attribute('aria-pressed', 'true')
        layout(page, 'motion-home-en')
        page.goto(BASE + '/')
        expect(page.locator('html')).to_have_attribute('lang', 'en')
        page.goto(BASE + '/zh')
        expect(page.locator('html')).to_have_attribute('lang', 'zh-CN')
        page.locator('.cg-hero-actions a').first.click()
        expect(page).to_have_url(BASE + '/login')
        page.get_by_role('button', name='EN', exact=True).click()
        expect(page.locator('input[type=email]')).to_be_visible()
        layout(page, 'motion-login-en')
        page.screenshot(path=str(OUT / 'motion-login-en.png'), full_page=True)
        assert not errors, errors
        context.close()

        # Reduced motion must not download or mount the decorative video.
        context = browser.new_context(reduced_motion='reduce')
        page = context.new_page()
        video_requests = []
        page.on('request', lambda request: video_requests.append(request.url) if request.url.endswith('.mp4') else None)
        page.goto(BASE + '/en')
        expect(page.locator('video')).to_have_count(0)
        expect(page.locator('.cg-motion-poster')).to_be_visible()
        assert not video_requests
        context.close()

        # Data-saving connections show a poster until the user explicitly plays it.
        context = browser.new_context()
        context.add_init_script("Object.defineProperty(navigator, 'connection', { value: { saveData: true }, configurable: true });")
        page = context.new_page()
        page.goto(BASE + '/en', wait_until='networkidle')
        assert page.locator('video').get_attribute('src') is None
        page.get_by_role('button', name='Play motion', exact=True).click()
        page.wait_for_function("document.querySelector('video').currentTime > .1")
        context.close()

        # Asset failure falls back to the poster without hiding primary actions.
        context = browser.new_context()
        page = context.new_page()
        page.route('**/media/legal-motion.mp4', lambda route: route.abort())
        page.goto(BASE)
        expect(page.locator('video')).to_have_count(0)
        expect(page.locator('.cg-motion-caption')).to_contain_text('静态预览')
        expect(page.locator('.cg-motion-poster')).to_be_visible()
        expect(page.locator('.cg-hero-actions a').first).to_be_visible()
        context.close()

        # Language selection must preserve live form state and raw backend enums.
        context = browser.new_context(viewport={'width': 1440, 'height': 1000})
        context.add_init_script("localStorage.setItem('token','synthetic');")
        context.route('http://127.0.0.1:8000/**', api)
        page = context.new_page()
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.goto(BASE + '/legal')
        expect(page.locator('.lv-motion-welcome h2')).to_be_visible()
        # The existing library entrance is finite. Check its settled state.
        page.evaluate("""async () => {
            const finite = document.getAnimations().filter(a => Number.isFinite(a.effect?.getTiming().iterations));
            await Promise.all(finite.map(a => a.finished.catch(() => {})));
        }""")
        readable_dark_heading(page, '.lv-motion-welcome h2', '.lv-motion-welcome')
        page.screenshot(path=str(OUT / 'motion-library-zh.png'), full_page=True, animations='disabled')
        page.goto(BASE + '/legal?contract=locale-c1')
        page.get_by_label('合同类型', exact=True).select_option('销售合同')
        page.get_by_role('radio', name='销售方', exact=True).check()
        page.get_by_label('审查重点', exact=True).fill('保留这段用户输入，不要翻译。')
        page.get_by_text('交易信息（选填）', exact=True).click()
        page.get_by_label('履行阶段', exact=True).select_option('谈判中')
        page.evaluate("window.formNode = document.querySelector('textarea[maxlength=\"1500\"]')")
        reads = sum(method == 'GET' and path == '/legal/contracts/locale-c1' for method, path in calls)
        page.get_by_role('button', name='EN', exact=True).click()
        expect(page).to_have_url(BASE + '/legal?contract=locale-c1&lang=en')
        expect(page.get_by_label('Contract type', exact=True)).to_have_value('销售合同')
        expect(page.locator('input[name=legal-our-role]:checked')).to_have_value('销售方')
        expect(page.locator('textarea[maxlength="1500"]')).to_have_value('保留这段用户输入，不要翻译。')
        assert page.evaluate("window.formNode === document.querySelector('textarea[maxlength=\"1500\"]')")
        assert sum(method == 'GET' and path == '/legal/contracts/locale-c1' for method, path in calls) == reads
        assert page.locator('select').evaluate_all("nodes => nodes.some(s => s.value === '谈判中' && s.selectedOptions[0].textContent === 'Under negotiation')")
        expect(page.locator('.lv-para')).to_contain_text('【脱敏1】应在验收后支付价款。')
        assert not any(method in ('POST', 'PUT', 'PATCH', 'DELETE') for method, _ in calls)
        layout(page, 'motion-setup-en')
        page.get_by_role('button', name='中文', exact=True).click()
        expect(page.get_by_label('合同类型', exact=True)).to_have_value('销售合同')
        expect(page.get_by_label('履行阶段', exact=True)).to_have_value('谈判中')
        assert not errors, errors
        context.close()
        browser.close()
    (OUT / 'motion-locale-results.json').write_text(json.dumps({'status': 'passed', 'contrast_checks': contrast_checks, 'locales': ['zh-CN', 'en'],
        'widths': [320, 390, 768, 1024, 1440], 'checks': ['default Chinese', 'language persistence', 'explicit URLs',
        'real video playback', 'pause/resume keeps frame', 'pause preference on reload', 'offscreen pause', 'live reduced-motion changes', 'dark-heading contrast', 'save-data opt-in playback', 'reduced motion', 'asset fallback', 'auth redirect',
        'form identity', 'contract deep link', 'unchanged API enum values', 'original contract unchanged', 'no write requests']}, indent=2))
    print('Legal motion and locale browser checks passed.')
finally:
    server.shutdown()
