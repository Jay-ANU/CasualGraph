"""Apply an exact, checksum-validated patch prepared against the feature branch."""
import hashlib
import json
from pathlib import Path

root = Path.cwd().resolve()
changes = json.loads(Path('.ui-finish/changes.json').read_text())
for name, change in changes.items():
    path = (root / name).resolve()
    assert path.is_relative_to(root)
    assert name.startswith('frontend/src/') or name in ('scripts/legal_motion_locale_smoke.py', 'scripts/research_ui_smoke.py')
    before = path.read_text()
    assert hashlib.sha256(before.encode()).hexdigest() == change['base'], f'Unexpected base: {name}'
    after = before
    for start, end, replacement in reversed(change['edits']):
        assert 0 <= start <= end <= len(before)
        after = after[:start] + replacement + after[end:]
    assert hashlib.sha256(after.encode()).hexdigest() == change['result'], f'Invalid result: {name}'
    path.write_text(after)
    print('Checksum verified:', name)

# Correct screenshot timing, without changing contrast thresholds or UI behavior.
path = root / 'scripts/legal_motion_locale_smoke.py'
s = path.read_text()
old = "page.set_viewport_size({'width': width, 'height': 900})\n        # Wait"
assert s.count(old) == 1
s = s.replace(old, "page.set_viewport_size({'width': width, 'height': 900})\n        page.evaluate('window.scrollTo(0, 0)')\n        # Wait")
old = "        readable_dark_heading(page, '.lv-motion-welcome h2', '.lv-motion-welcome')"
assert s.count(old) == 1
s = s.replace(old, '''        # The existing library entrance is finite. Check its settled state.
        page.evaluate("""async () => {
            const finite = document.getAnimations().filter(a => Number.isFinite(a.effect?.getTiming().iterations));
            await Promise.all(finite.map(a => a.finished.catch(() => {})));
        }""")
        readable_dark_heading(page, '.lv-motion-welcome h2', '.lv-motion-welcome')''')
assert hashlib.sha256(s.encode()).hexdigest() == '25c30324a00673d4f13ae1e81bfcc07d9ecbf1bbbde666442c0696963fe442ab'
path.write_text(s)
