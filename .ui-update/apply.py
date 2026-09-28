import hashlib, json
from pathlib import Path
sha = lambda text: hashlib.sha256(text.encode('utf-8')).hexdigest()
for part in sorted(Path('.ui-update').glob('patch-*.json')):
    payload = json.loads(part.read_text())
    # Correct two transcription offsets; the result checksum remains mandatory.
    if part.name == 'patch-3.json':
        for edit in payload['frontend/src/legal/ScenarioPicker.tsx']['edits']:
            if edit[:2] == [462, 4626]: edit[1] = 462
        for edit in payload['frontend/src/legal/TopBar.tsx']['edits']:
            if edit[:2] == [3116, 3116]:
                edit[2] = ')} title={t("界面语言不会翻译合同原文或模型生成的审查内容。")}'
    for name, spec in payload.items():
        assert name.startswith('frontend/') or name == '.github/workflows/ci.yml', name
        path = Path(name)
        before = path.read_text()
        assert sha(before) == spec['base'], f'Base checksum mismatch: {name}'
        after = before
        for start, end, replacement in reversed(spec['edits']):
            assert 0 <= start <= end <= len(before), name
            after = after[:start] + replacement + after[end:]
        assert sha(after) == spec['result'], f'Result checksum mismatch: {name}'
        path.write_text(after)
        print('Applied and verified', name)
