"""Deterministic traceability/edit gates; not a certification of legal correctness."""
from __future__ import annotations
import hashlib
import json
import re
from collections import Counter
from difflib import SequenceMatcher
from typing import Any

TOKENS = re.compile(r'【(?:补充)?脱敏\d+】')
ARTICLE = re.compile(r'第[一二三四五六七八九十百千万零〇两\d]+条')
CONTROL = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')

def text(value: Any, limit: int = 5000) -> str:
    return value[:limit] if isinstance(value, str) else ''

def rows(value: Any) -> list:
    return value if isinstance(value, list) else []

def norm(value: str) -> str:
    return re.sub(r'\s+', '', value)

def citations(value: Any, sources: list[dict]) -> list[dict]:
    source_map = {s['id']: s for s in sources}
    found, seen = [], set()
    for row in rows(value)[:8]:
        if not isinstance(row, dict):
            continue
        sid = text(row.get('source_id'), 100)
        quote = text(row.get('supporting_quote'), 5001)
        source = source_map.get(sid)
        if (not source or '[…]' in quote or not 12 <= len(norm(quote)) <= 5000
                or norm(quote) not in norm(source.get('text', ''))):
            continue
        key = (sid, norm(quote))
        if key not in seen:
            seen.add(key)
            found.append({'source_id': sid, 'supporting_quote': quote})
    return found

def edit_warnings(original: str, replacement: str) -> list[str]:
    """A replacement is whole-paragraph text, with the original sensitive tokens intact."""
    warnings = []
    if not replacement.strip() or len(replacement) > 12000 or CONTROL.search(replacement):
        warnings.append('修改文本为空、过长或包含非法字符。')
    if Counter(TOKENS.findall(original)) != Counter(TOKENS.findall(replacement)):
        warnings.append('建议改变了脱敏主体的出现次数，请人工核对主体及义务归属。')
    elif TOKENS.findall(original) != TOKENS.findall(replacement):
        warnings.append('建议交换了脱敏主体的顺序，可能改变权利义务方向；请重新审查。')
    if original == replacement:
        warnings.append('建议与原文相同。')
    elif len(original) > 20 and SequenceMatcher(None, original, replacement, autojunk=False).ratio() < .35:
        warnings.append('建议重写范围过大，请人工编辑，避免无关约定被删除。')
    return warnings

def validate(raw: Any, rules: list[dict], blocks: list[dict], sources: list[dict], policies: list[dict]) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    rule_map = {r['id']: r for r in rules}
    block_map = {b['id']: b for b in blocks}
    policy_ids = {p['id'] for p in policies}
    supplied_rows = [c for c in rows(raw.get('coverage')) if isinstance(c, dict)]
    counts = Counter(text(c.get('rule_id'), 100) for c in supplied_rows)
    supplied = {text(c.get('rule_id'), 100): c for c in supplied_rows}
    coverage = []
    for rule in rules:
        c = supplied.get(rule['id'], {})
        status = c.get('status')
        if (counts[rule['id']] != 1 or status not in ('reviewed', 'not_applicable', 'needs_information')
                or not text(c.get('note')).strip()):
            status = 'not_reviewed'
        coverage.append({'rule_id': rule['id'], 'title': rule['title'], 'status': status,
                         'note': text(c.get('note'), 1200), 'verification_status': 'pending'})
    candidates = rows(raw.get('findings'))
    rejected = max(0, len(candidates) - 30)
    if not isinstance(raw.get('findings'), list):
        rejected += 1
    findings = []
    for item in candidates[:30]:
        if not isinstance(item, dict):
            rejected += 1
            continue
        rid = text(item.get('rule_id'), 100)
        bid = text(item.get('block_id'), 100) or None
        quote, kind = text(item.get('original_quote'), 12001), item.get('kind')
        if (rid not in rule_map or kind not in ('legal', 'commercial', 'company_policy')
                or (bid and (bid not in block_map or not quote or quote not in block_map[bid]['text']))
                or (not bid and quote) or not text(item.get('title')).strip()
                or not text(item.get('impact')).strip() or not text(item.get('reason')).strip()):
            rejected += 1
            continue
        pids = list(dict.fromkeys(p for p in rows(item.get('policy_ids')) if isinstance(p, str) and p in policy_ids))
        if kind == 'company_policy' and not pids:
            rejected += 1
            continue
        refs = citations(item.get('citations'), sources)
        evidence_ok = kind != 'legal' or bool(refs)
        missing = [text(s, 500) for s in rows(item.get('missing_facts'))[:10] if isinstance(s, str) and s.strip()]
        warnings = []
        if not isinstance(item.get('missing_facts'), list):
            warnings.append('模型没有提供有效的待确认事实清单。')
        suggestion = text(item.get('suggested_text'), 12001)
        if suggestion and bid:
            warnings.extend(edit_warnings(block_map[bid]['text'], suggestion))
        if not bid:
            suggestion = ''
            warnings.append('缺失条款需要人工选择插入位置，不能自动覆盖现有段落。')
        if len(suggestion) > 12000 or CONTROL.search(suggestion):
            suggestion = ''
        if missing:
            warnings.append('缺少会影响判断的交易事实，补充后应重新审查。')
        source_map = {s['id']: s for s in sources}
        cited_text = '\n'.join(source_map[c['source_id']].get('text', '') for c in refs)
        claims = text(item.get('reason')) + text(item.get('impact')) + text(item.get('title'))
        if kind == 'legal' and any(a not in cited_text for a in ARTICLE.findall(claims)):
            evidence_ok = False
            warnings.append('意见中的条号不在所引来源内，不能据此下结论。')
        f = {'id': 'f_' + hashlib.sha256(json.dumps(item, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16],
             'rule_id': rid, 'block_id': bid, 'original_quote': quote, 'kind': kind,
             'title': text(item.get('title'), 300), 'impact': text(item.get('impact'), 3000),
             'reason': text(item.get('reason'), 5000),
             'severity': item.get('severity') if item.get('severity') in ('high', 'medium', 'low') else 'medium',
             'suggested_text': suggestion if evidence_ok else '', 'citations': refs, 'policy_ids': pids,
             'missing_facts': missing, 'validation_warnings': warnings,
             'evidence_status': 'source_matched' if kind == 'legal' and evidence_ok else ('unverified' if kind == 'legal' else 'not_applicable'),
             'version_status': 'needs_verification' if kind == 'legal' else 'not_applicable',
             'needs_confirmation': True, 'verification_status': 'pending', 'revision_allowed': False,
             'requires_legal_confirmation': kind == 'legal'}
        if not evidence_ok:
            f.update(title='待核实：' + rule_map[rid]['title'], severity='medium',
                     impact='未取得足够的可核验依据，不能据此认定违法、无效或不存在风险。',
                     reason='引文或条号校验未通过。请补充正式规定的原文、版本和适用条件。')
        findings.append(f)
    return {'coverage': coverage, 'findings': findings, 'rejected_findings': rejected}

def apply_verification(checked: dict, raw: Any) -> dict:
    """Every finding and every claimed coverage item needs an explicit disposition."""
    raw = raw if isinstance(raw, dict) else {}
    items = [r for r in rows(raw.get('checks')) if isinstance(r, dict)]
    counts = Counter(text(r.get('finding_id'), 100) for r in items)
    index = {text(r.get('finding_id'), 100): r for r in items}
    for f in checked['findings']:
        audit = index.get(f['id'], {})
        disposition, reason = audit.get('status'), text(audit.get('reason'), 1800)
        if counts[f['id']] != 1 or disposition not in ('supported', 'uncertain', 'rejected') or not reason.strip():
            disposition, reason = 'uncertain', '本条意见未得到完整的逐项复核，不能直接纳入修订。'
        f['verification_status'], f['verification_note'] = disposition, reason
        f['revision_allowed'] = bool(disposition == 'supported' and audit.get('replacement_supported') is True
                                     and f['suggested_text'] and not f['missing_facts']
                                     and not f['validation_warnings'] and f['evidence_status'] != 'unverified')
        if disposition != 'supported':
            f['suggested_text'] = ''
            f['evidence_status'] = 'unverified'
            f['title'] = ('复核未支持：' if disposition == 'rejected' else '待确认：') + f['title'][:280]
            if disposition == 'rejected':
                f['impact'] = '初审意见未通过复核，不能把它当成已经成立的风险。'
                f['reason'] = '逐项复核说明：' + reason
            else:
                f['reason'] = '当前意见尚未得到充分支持。' + f['reason']
        f['needs_confirmation'] = f['kind'] == 'legal' or not f['revision_allowed']
    checks = [r for r in rows(raw.get('coverage_checks')) if isinstance(r, dict)]
    check_counts = Counter(text(r.get('rule_id'), 100) for r in checks)
    by_rule = {text(r.get('rule_id'), 100): r for r in checks}
    for c in checked['coverage']:
        item = by_rule.get(c['rule_id'], {})
        supported = check_counts[c['rule_id']] == 1 and item.get('status') == 'covered' and bool(text(item.get('reason')).strip())
        c['verification_status'] = 'supported' if supported else 'uncertain'
        c['verification_note'] = text(item.get('reason'), 1200) or '本项覆盖未得到完整复核。'
        if not supported and c['status'] in ('reviewed', 'not_applicable'):
            c['status'] = 'needs_information'
    return checked

def validate_facts(raw: Any, blocks: list[dict]) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    by_id = {b['id']: b['text'] for b in blocks}
    facts, rejected = [], 0
    for item in rows(raw.get('facts'))[:16]:
        if not isinstance(item, dict):
            rejected += 1
            continue
        bid, quote, value = text(item.get('block_id'), 100), text(item.get('quote'), 1200), text(item.get('value'), 500)
        if not value or not quote or bid not in by_id or quote not in by_id[bid] or value not in quote:
            rejected += 1
            continue
        facts.append({'name': text(item.get('name'), 80), 'value': value, 'block_id': bid, 'quote': quote})
    return {'facts': facts, 'rejected_facts': rejected}

def consolidate(batches: dict) -> tuple[list[dict], list[dict]]:
    """Keep conflicting replacements even when their issue title and quote agree."""
    found, seen, coverage = [], set(), []
    for _, batch in sorted(batches.items()):
        coverage.extend(batch.get('coverage', []))
        for f in batch.get('findings', []):
            key = (f['kind'], f.get('block_id'), norm(f['title']), norm(f['original_quote']), norm(f.get('suggested_text', '')))
            if key in seen:
                continue
            seen.add(key)
            found.append(dict(f))
    targets: dict[str, set[str]] = {}
    for f in found:
        if f.get('block_id') and f.get('revision_allowed'):
            targets.setdefault(f['block_id'], set()).add(f['suggested_text'])
    for f in found:
        if len(targets.get(f.get('block_id'), set())) > 1:
            f['conflict_group'] = f['block_id']
    rank = {'high': 0, 'medium': 1, 'low': 2}
    found.sort(key=lambda f: (rank[f['severity']], f.get('block_id') or '', f['id']))
    return found, coverage

def finding_status(f: dict) -> str:
    if f.get('verification_status') == 'rejected':
        return 'rejected'
    if f.get('verification_status') != 'supported' or f.get('evidence_status') == 'unverified' or f.get('missing_facts'):
        return 'unconfirmed'
    return 'supported'


def summary(findings: list[dict], coverage: list[dict]) -> dict:
    supported = [f for f in findings if finding_status(f) == 'supported']
    return {'high': sum(f['severity'] == 'high' for f in supported),
            'medium': sum(f['severity'] == 'medium' for f in supported),
            'low': sum(f['severity'] == 'low' for f in supported),
            'unconfirmed': sum(finding_status(f) == 'unconfirmed' for f in findings),
            'rejected_candidates': sum(finding_status(f) == 'rejected' for f in findings),
            'needs_confirmation': sum(finding_status(f) != 'rejected' and (not f.get('revision_allowed') or f['kind'] == 'legal') for f in findings),
            'checked_rules': sum(c['status'] in ('reviewed', 'not_applicable') and c.get('verification_status') == 'supported' for c in coverage),
            'total_rules': len(coverage),
            'notice': '风险数只包含已获模型及证据支持的候选意见；待核实和已否定项单列。规则覆盖不等于合同风险覆盖。'}


def apply_cross_edit_checks(findings: list[dict], raw: Any) -> None:
    """Every proposed edit needs an explicit whole-contract compatibility result."""
    raw = raw if isinstance(raw, dict) else {}
    items = [r for r in rows(raw.get('proposal_checks')) if isinstance(r, dict)]
    counts = Counter(text(r.get('finding_id'), 100) for r in items)
    index = {text(r.get('finding_id'), 100): r for r in items}
    for finding in findings:
        if finding.get('revision_allowed') is not True:
            continue
        item = index.get(finding['id'], {})
        reason = text(item.get('reason'), 1200)
        passed = counts[finding['id']] == 1 and item.get('status') == 'consistent' and bool(reason.strip())
        finding['cross_edit_status'] = 'supported' if passed else 'uncertain'
        finding['cross_edit_note'] = reason or '尚未确认本建议与其他拟议修改同时采用时是否一致。'
        if not passed:
            finding['revision_allowed'] = False
            finding['needs_confirmation'] = True
            finding.setdefault('validation_warnings', []).append('跨条款修改一致性未通过，暂不能直接纳入修订。')
