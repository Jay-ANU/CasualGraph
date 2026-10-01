"""Landing page checks against the production build; APIs are mock fixtures, no credentials.

Covers: Chinese as the default language and the persisted English switch, the legal-agent
headline and calls to action, hero video playback (landscape on desktop, portrait on phones),
the pause control and its remembered preference, reduced motion, the pinned workflow story,
and layout without horizontal overflow from 320 to 1440 px in both languages.
"""
import functools
import http.server
import json
import os
import threading
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / 'frontend' / 'dist'
OUT = ROOT / 'ui-artifacts'
OUT.mkdir(exist_ok=True)
BASE = 'http://127.0.0.1:4174'
VIDEO = '.lp-hero-video'


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if not (BUILD / self.path.split('?')[0].lstrip('/')).is_file():
            self.path = '/index.html'
        super().do_GET()

    def log_message(self, *args):
        pass


server = http.server.ThreadingHTTPServer(('127.0.0.1', 4174), functools.partial(Handler, directory=str(BUILD)))
threading.Thread(target=server.serve_forever, daemon=True).start()
results, errors = [], []


def check(label, ok, detail=None):
    entry = {'check': label, 'passed': bool(ok)}
    if detail is not None:
        entry['detail'] = detail
    results.append(entry)
    print(json.dumps(entry, ensure_ascii=False), flush=True)


def api(route):
    # Signed-out visitor: the landing page needs no API, protected links send people to sign in.
    route.fulfill(status=401, content_type='application/json', body='{"detail":"Not authenticated"}',
                  headers={'Access-Control-Allow-Origin': '*'})


def chromium_executable(playwright):
    """Playwright's own Chromium when installed; otherwise one already under PLAYWRIGHT_BROWSERS_PATH."""
    if Path(playwright.chromium.executable_path).is_file():
        return None
    root = Path(os.environ.get('PLAYWRIGHT_BROWSERS_PATH') or '/opt/pw-browsers')
    found = sorted(root.glob('chromium-*/chrome-linux/chrome')) or sorted(root.glob('chromium_headless_shell-*/chrome-linux/headless_shell'))
    return str(found[-1]) if found else None


def context(browser, width, height, **options):
    ctx = browser.new_context(viewport={'width': width, 'height': height}, device_scale_factor=1, **options)
    ctx.route('http://127.0.0.1:8000/**', api)
    page = ctx.new_page()
    page.on('pageerror', lambda error: errors.append(str(error)))
    return ctx, page


def no_overflow(page, label):
    dims = page.evaluate('({scroll: document.documentElement.scrollWidth, viewport: innerWidth})')
    check(label, dims['scroll'] <= dims['viewport'] + 1, dims)


def video_playing(page, timeout=20000):
    page.wait_for_function(f"() => {{ const v = document.querySelector('{VIDEO}'); return v && !v.paused && v.currentTime > 0.25; }}", timeout=timeout)
    return page.evaluate(f"document.querySelector('{VIDEO}').currentSrc")


try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=chromium_executable(p),
                                    args=['--no-sandbox', '--disable-dev-shm-usage', '--autoplay-policy=no-user-gesture-required'])

        # Desktop, motion allowed, first visit.
        ctx, page = context(browser, 1440, 900)
        page.goto(BASE + '/', wait_until='domcontentloaded')
        heading = page.get_by_role('heading', level=1, name='你的 AI 法务团队逐条守护每一份合同')
        heading.wait_for()
        check('Chinese is the default language', page.evaluate('document.documentElement.lang') == 'zh-CN')
        check('Legal agent headline', heading.count() == 1)
        nav = page.get_by_role('navigation', name='主导航').get_by_role('link')
        check('Navigation leads with the legal agent', nav.first.inner_text().strip() == '法务 Agent' and nav.first.get_attribute('href') == '/legal')
        check('Hero call to action opens the legal desk', page.get_by_role('link', name='开始审查合同').first.get_attribute('href') == '/legal')
        check('Contract scenarios listed for assistive tech', '软件许可合同' in (page.locator('#scenarios .sr-only').text_content() or ''))
        check('Five agents described', page.locator('.lp-net-list li').count() == 5)
        source = video_playing(page)
        check('Hero video plays the landscape cut on desktop', 'hero-legal-1080' in source, source)
        page.wait_for_timeout(2600)
        page.screenshot(path=str(OUT / 'landing-hero-zh.png'))

        page.get_by_role('button', name='暂停背景动效').click()
        page.wait_for_timeout(300)
        check('Pausing stops the video', page.evaluate(f"document.querySelector('{VIDEO}').paused"))
        page.reload(wait_until='domcontentloaded')
        page.get_by_role('button', name='播放背景动效').wait_for()
        page.wait_for_timeout(1500)
        check('The pause is remembered after a reload', page.evaluate(f"(() => {{ const v = document.querySelector('{VIDEO}'); return !v || v.paused; }})()"))
        page.get_by_role('button', name='播放背景动效').click()
        video_playing(page)
        check('Playing again resumes the video', True)

        story = page.evaluate("() => { const el = document.querySelector('.lp-story'); return { top: el.getBoundingClientRect().top + scrollY, span: el.offsetHeight - innerHeight }; }")
        steps = []
        for i in range(5):
            page.evaluate(f"window.scrollTo(0, {story['top']} + {story['span']} * {(i + 0.5) / 5})")
            page.wait_for_timeout(700)
            steps.append(page.locator('.lp-story-steps [aria-current="step"] strong').inner_text())
        check('Scrolling walks through the five workflow steps', steps == ['上传合同', '自动脱敏', '设定立场', '多 Agent 审查', '逐条处理，导出修订'], steps)
        page.wait_for_timeout(3200)
        page.screenshot(path=str(OUT / 'landing-story-zh.png'))
        cards = page.locator('.lp-card')
        for i in range(cards.count()):
            cards.nth(i).scroll_into_view_if_needed()
            page.wait_for_timeout(150)
        page.wait_for_timeout(1200)
        check('Capability cards revealed on scroll', page.locator('.lp-card.is-in').count() == cards.count() == 8, page.locator('.lp-card.is-in').count())

        page.evaluate('window.scrollTo(0, 0)')
        page.get_by_role('group', name='界面语言').first.get_by_role('button', name='EN').click()
        english = page.get_by_role('heading', level=1, name='Your AI legal team, on every clause.')
        english.wait_for()
        check('English switch translates the page', page.evaluate('document.documentElement.lang') == 'en' and page.get_by_role('link', name='Review a contract').count() >= 1)
        page.locator('.lp-card').last.scroll_into_view_if_needed()
        page.wait_for_timeout(1400)
        shown = page.evaluate("[...document.querySelectorAll('.lp-card')].filter(el => getComputedStyle(el).opacity === '1').length")
        check('Sections revealed before the switch stay visible in English', shown == 8, shown)
        page.evaluate('window.scrollTo(0, 0)')
        page.reload(wait_until='domcontentloaded')
        page.get_by_role('heading', level=1, name='Your AI legal team, on every clause.').wait_for()
        check('English is remembered after a reload', page.get_by_role('navigation', name='Primary').get_by_role('link', name='Legal Agent').count() == 1)
        page.wait_for_timeout(2600)
        page.screenshot(path=str(OUT / 'landing-hero-en.png'))

        for lang in ('en', 'zh'):
            page.evaluate(f"localStorage.setItem('causalgraph.lang', '{lang}')")
            for width, height in ((320, 720), (390, 844), (768, 1024), (1024, 800), (1440, 900)):
                page.set_viewport_size({'width': width, 'height': height})
                page.goto(BASE + '/', wait_until='domcontentloaded')
                page.get_by_role('heading', level=1).wait_for()
                page.wait_for_timeout(250)
                no_overflow(page, f'No horizontal overflow at {width}px ({lang})')
        page.screenshot(path=str(OUT / 'landing-full-zh.png'), full_page=True)
        ctx.close()

        # Phone: the portrait cut, composed for a tall screen.
        ctx, page = context(browser, 390, 844, is_mobile=True, has_touch=True)
        page.goto(BASE + '/', wait_until='domcontentloaded')
        source = video_playing(page)
        check('Phones get the portrait cut', 'hero-legal-portrait' in source, source)
        page.get_by_role('button', name='打开菜单').click()
        check('Mobile menu lists the legal agent', page.get_by_role('navigation', name='移动端导航').get_by_role('link', name='法务 Agent').is_visible())
        page.wait_for_timeout(1500)
        page.screenshot(path=str(OUT / 'landing-mobile-zh.png'))
        ctx.close()

        # Reduced motion: no playback, everything readable immediately.
        ctx, page = context(browser, 1440, 900, reduced_motion='reduce')
        page.goto(BASE + '/', wait_until='domcontentloaded')
        page.get_by_role('heading', level=1).wait_for()
        page.wait_for_timeout(1500)
        check('Reduced motion keeps the video still', page.evaluate(f"(() => {{ const v = document.querySelector('{VIDEO}'); return !v || (v.paused && v.currentTime === 0); }})()"))
        check('Reduced motion shows the headline at once', page.evaluate("getComputedStyle(document.querySelector('.lp-ch')).opacity") == '1')
        check('Reduced motion hides the pause control', page.get_by_role('button', name='暂停背景动效').count() == 0)
        page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        page.wait_for_timeout(300)
        hidden = page.evaluate("[...document.querySelectorAll('[data-reveal]')].filter(el => getComputedStyle(el).opacity !== '1').length")
        check('Reduced motion reveals every section without animation', hidden == 0, hidden)
        ctx.close()

        check('No browser JavaScript errors', not errors, errors)
        browser.close()
except Exception as exc:
    check('Browser run completed', False, str(exc))
finally:
    (OUT / 'landing-results.json').write_text(json.dumps({'backend': 'mock fixtures only', 'results': results, 'javascript_errors': errors}, indent=2, ensure_ascii=False))
    server.shutdown()

if any(not result['passed'] for result in results):
    raise SystemExit('Landing page verification failed; see ui-artifacts/landing-results.json')
