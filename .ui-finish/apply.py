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
