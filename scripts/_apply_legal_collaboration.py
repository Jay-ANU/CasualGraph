"""One-time, hash-pinned integration on the feature branch; removed before merge."""
from pathlib import Path
import ast
import hashlib

EXPECTED = {
    'api/routers/contract_review.py': '4bc70ad9bb98df4cd910ae97c8c0a32478341720',
    'legal/review_store.py': '9340a99fd75dc89e75c179e52782561da794125d',
    'legal/review_engine.py': 'd21ce5944d4cd5a5bc191bf42a5de99703b780a9',
}
originals = {}
for name, expected in EXPECTED.items():
    data = Path(name).read_bytes()
    actual = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
    if actual != expected:
        raise RuntimeError('Baseline changed: ' + name)
    originals[name] = data.decode()

def replace(source, before, after):
    if source.count(before) != 1:
        raise RuntimeError('Non-unique patch anchor: ' + before[:100])
    return source.replace(before, after, 1)

def function(source, name):
    matches = [n for n in ast.parse(source).body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    if len(matches) != 1:
        raise RuntimeError('Function not unique: ' + name)
    node = matches[0]
    return ''.join(source.splitlines(keepends=True)[node.lineno-1:node.end_lineno])

source = originals['api/routers/contract_review.py']
methods = Path('scripts/_legal_router_methods.txt').read_text()
for name in ('_review_view', 'resume', 'decision'):
    source = replace(source, function(source, name), function(methods, name).rstrip() + '\n')
source = replace(source, '    fresh_review: bool = False', '    fresh_review: bool = False\n    instructions: str = Field(default="", max_length=1500)\n    review_mode: Literal["standard", "multi_agent"] = "multi_agent"')
source = replace(source, '    expected_version: int = Field(default=0, ge=0)', '    expected_version: int = Field(default=0, ge=0)\n    legal_basis_confirmed: bool = False\n    manual_edit_confirmed: bool = False')
source = replace(source, "'model_selection_version': 1}", "'model_selection_version': 1, 'review_engine_version': 2, 'followup_questions': True, 'collaboration_version': 1}")
source = replace(source, "'model_gateway': 'ydata', 'encryption_configured': encrypted,", "'model_gateway': 'ydata', 'encryption_configured': encrypted,\n            'review_engine_version': 2, 'followup_questions': True, 'collaboration_version': 1,")
source = replace(source, "    profile['model'] = selected", "    from legal.review_questions import redact_note\n    profile['instructions'] = redact_note(profile.get('instructions', ''), c['payload'])\n    profile['model'] = selected")
source = replace(source, "    snapshot = {'contract_revision': c['revision'],", "    snapshot = {'engine_version': 2, 'contract_revision': c['revision'],")
output = {'api/routers/contract_review.py': source.rstrip() + Path('scripts/_legal_router_additions.txt').read_text() + '\n'}
source = originals['legal/review_store.py']
source = replace(source, 'def decide(rid: str, user_id: str, finding_id: str, decision: str, text: str, expected_version: int):', 'def decide(rid: str, user_id: str, finding_id: str, decision: str, text: str, expected_version: int, *, legal_basis_confirmed: bool = False, manual_edit_confirmed: bool = False):')
source = replace(source, "            allowed = set(decode(cp['payload']).get('mapping', {}))", '''            contract_payload = decode(cp['payload'])
            if payload.get('engine_version') == 2:
                from legal.review_quality import edit_warnings
                if finding.get('revision_allowed') is not True or finding.get('verification_status') != 'supported' or finding.get('missing_facts'):
                    fail(409, '此建议未完成复核或缺少关键事实，不能直接纳入修订。')
                if finding['kind'] == 'legal' and legal_basis_confirmed is not True:
                    fail(409, '请先核对法条版本及适用条件，再确认纳入修订。')
                if text != finding.get('suggested_text') and manual_edit_confirmed is not True:
                    fail(409, '手工编辑后的文本需要明确确认。')
                original = next((b['text'] for b in contract_payload['redacted_blocks'] if b['id'] == finding.get('block_id')), '')
                if not original or edit_warnings(original, text):
                    fail(422, '修改范围、主体代称或文本完整性检查未通过，请人工核对。')
            allowed = set(contract_payload.get('mapping', {}))''')
source = replace(source, "                                 'user_id': user_id, 'version': expected_version + 1}", "                                 'user_id': user_id, 'version': expected_version + 1,\n                                 'legal_basis_confirmed': legal_basis_confirmed is True,\n                                 'manual_edit_confirmed': manual_edit_confirmed is True}")
output['legal/review_store.py'] = source.rstrip() + Path('scripts/_legal_store_additions.txt').read_text() + '\n'
output['legal/review_engine.py'] = replace(originals['legal/review_engine.py'], 'def run_review(rid: str):\n', '''def run_review(rid: str):
    # Existing jobs retain their original engine; new jobs explicitly pin v2.
    if store.review(rid)['payload'].get('engine_version') == 2:
        from legal.review_v2 import run_review as run_v2
        return run_v2(rid)
''')
for name, source in output.items():
    compile(source, name, 'exec')
for name, source in output.items():
    Path(name).write_text(source)
print('Applied exactly three hash-verified source changes. No secrets or deployment configuration modified.')
