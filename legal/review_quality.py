"""Deterministic traceability/edit gates; not a certification of legal correctness."""
from __future__ import annotations
import hashlib
import json
import re
import unicodedata
from collections import Counter
from difflib import SequenceMatcher
from typing import Any
from legal.law_evidence import NON_AUTHORITIES

TOKENS = re.compile(r'【(?:补充)?脱敏\d+】')
ARTICLE = re.compile(r'第[一二三四五六七八九十百千万零〇两\d]+条')
ARTICLE_LABEL = re.compile(r'第[一二三四五六七八九十百千万零〇两\d]+条(?:之[一二三四五六七八九十\d]+)?')
CONTROL = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')
_DIGITS = {'零': 0, '〇': 0, '一': 1, '二': 2, '两': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9}
_UNITS = {'十': 10, '百': 100, '千': 1000, '万': 10000}
_QUOTES = str.maketrans({'“': '"', '”': '"', '„': '"', '‟': '"', '″': '"', '‘': "'", '’': "'", '‚': "'", '‛': "'"})

def text(value: Any, limit: int = 5000) -> str:
    return value[:limit] if isinstance(value, str) else ''

def rows(value: Any) -> list:
    return value if isinstance(value, list) else []

def norm(value: str) -> str:
    return re.sub(r'\s+', '', value)

def fold(value: str) -> tuple[str, list[int]]:
    """Comparable form (no whitespace, width-folded) plus each character's original offset."""
    chars, index = [], []
    for i, ch in enumerate(value):
        for c in unicodedata.normalize('NFKC', ch).translate(_QUOTES):
            if not c.isspace():
                chars.append(c)
                index.append(i)
    return ''.join(chars), index

def locate(quote: str, source: str) -> str | None:
    """The exact source span for a quote that differs only in spacing or character width.

    Models often retype U+3000 or full-width punctuation; the stored quote is always
    the original text, so anchors and redlines still match the document.
    """
    if not quote or not source:
        return None
    if quote in source:
        return quote
    needle = fold(quote)[0]
    if len(needle) < 2:
        return None
    haystack, index = fold(source)
    at = haystack.find(needle)
    if at < 0:
        return None
    return source[index[at]:index[at + len(needle) - 1] + 1]

def article_value(label: Any) -> int | None:
    """第五百八十五条 and 第585条 are the same number; compare by value, not spelling."""
    match = ARTICLE.search(label) if isinstance(label, str) else None
    if not match:
        return None
    body = match.group()[1:-1]
    if body.isdigit():
        return int(body)
    total = section = number = 0
    for ch in body:
        if ch in _DIGITS:
            number = _DIGITS[ch]
        elif ch in _UNITS:
            if _UNITS[ch] == 10000:
                total += (section + number) * 10000
                section = number = 0
            else:
                section += (number or 1) * _UNITS[ch]
                number = 0
        else:
            return None
    return total + section + number

def article_numbers(value: str) -> set[int]:
    return {n for n in (article_value(a) for a in ARTICLE.findall(value or '')) if n is not None}

def citations(value: Any, sources: list[dict]) -> list[dict]:
    source_map = {s['id']: s for s in sources}
    folded: dict[str, str] = {}
    found, seen = [], set()
    for row in rows(value)[:8]:
        if not isinstance(row, dict):
            continue
        sid = text(row.get('source_id'), 100)
        quote = text(row.get('supporting_quote'), 5001)
        source = source_map.get(sid)
        needle = fold(quote)[0]
        if not source or '[…]' in quote or not 12 <= len(needle) <= 5000:
            continue
        if sid not in folded:
            folded[sid] = fold(source.get('text', ''))[0]
        if needle not in folded[sid]:
            continue
        key = (sid, needle)
        if key not in seen:
            seen.add(key)
            found.append({'source_id': sid, 'supporting_quote': quote})
    return found

def law_refs(value: Any) -> list[dict]:
    """Statutes the model names from its own knowledge; labelled until official text is attached."""
    found, seen = [], set()
    for row in rows(value)[:8]:
        if not isinstance(row, dict):
            continue
        law = re.sub(r'\s+', ' ', text(row.get('law'), 120)).strip().strip('《》')
        label = ARTICLE_LABEL.search(text(row.get('article'), 60))
        article = label.group() if label else ''
        point = text(row.get('point'), 400).strip()
        if not law or CONTROL.search(law + article + point):
            continue
        key = (law, article_value(article))
        if key in seen:
            continue
        seen.add(key)
        found.append({'law': law, 'article': article, 'point': point, 'status': 'model_cited'})
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
    source_map = {s['id']: s for s in sources}
    # Contract clause numbers ("合同第八条") are facts of the document, not legal citations.
    contract_numbers = article_numbers('\n'.join(b['text'] for b in blocks))
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
        given, kind = text(item.get('original_quote'), 12001), item.get('kind')
        quote = locate(given, block_map[bid]['text']) if bid in block_map and given else None
        if (rid not in rule_map or kind not in ('legal', 'commercial', 'company_policy')
                or (bid and not quote) or (not bid and given) or not text(item.get('title')).strip()
                or not text(item.get('impact')).strip() or not text(item.get('reason')).strip()):
            rejected += 1
            continue
        pids = list(dict.fromkeys(p for p in rows(item.get('policy_ids')) if isinstance(p, str) and p in policy_ids))
        if kind == 'company_policy' and not pids:
            rejected += 1
            continue
        refs = citations(item.get('citations'), sources)
        if kind == 'legal':
            refs = [c for c in refs if source_map[c['source_id']].get('source_kind') not in NON_AUTHORITIES]
        laws = law_refs(item.get('law_refs')) if kind == 'legal' else []
        cited_numbers = article_numbers('\n'.join(source_map[c['source_id']].get('text', '') for c in refs))
        for ref in laws:
            if refs and ref['article'] and article_value(ref['article']) in cited_numbers:
                ref['status'] = 'source_matched'
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
        claims = text(item.get('reason')) + text(item.get('impact')) + text(item.get('title'))
        explained = contract_numbers | cited_numbers | {article_value(r['article']) for r in laws if r['article']}
        unexplained = list(dict.fromkeys(a for a in ARTICLE.findall(claims) if article_value(a) not in explained))
        if unexplained:
            warnings.append('意见提到的' + '、'.join(unexplained[:5]) + '未见于合同原文、所附依据或所列法条，请核对后再采纳。')
        evidence = ('source_matched' if refs else 'model_cited' if laws else 'unverified') if kind == 'legal' else 'not_applicable'
        findings.append({'id': 'f_' + hashlib.sha256(json.dumps(item, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16],
             'rule_id': rid, 'block_id': bid, 'original_quote': quote or '', 'kind': kind,
             'title': text(item.get('title'), 300), 'impact': text(item.get('impact'), 3000),
             'reason': text(item.get('reason'), 5000),
             'severity': item.get('severity') if item.get('severity') in ('high', 'medium', 'low') else 'medium',
             'suggested_text': suggestion, 'citations': refs, 'law_refs': laws, 'policy_ids': pids,
             'missing_facts': missing, 'validation_warnings': warnings, 'evidence_status': evidence,
             'version_status': 'needs_verification' if kind == 'legal' else 'not_applicable',
             'needs_confirmation': True, 'verification_status': 'pending', 'revision_allowed': False,
             'requires_legal_confirmation': kind == 'legal'})
    return {'coverage': coverage, 'findings': findings, 'rejected_findings': rejected}

def apply_verification(checked: dict, raw: Any) -> dict:
    """Every finding and every claimed coverage item needs an explicit disposition.

    Only an explicit "supported" enables one-click adoption. An uncertain finding keeps
    its analysis and proposed wording so a reviewer can still edit and adopt it by hand.
    """
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
        if disposition == 'rejected':
            f['suggested_text'] = ''
            f['title'] = '复核未支持：' + f['title'][:280]
            f['impact'] = '初审意见未通过复核，不能把它当成已经成立的风险。'
            f['reason'] = '逐项复核说明：' + reason
        elif disposition != 'supported':
            f['title'] = '待确认：' + f['title'][:280]
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
        located = locate(quote, by_id[bid]) if bid in by_id and quote else None
        if not value or not located or fold(value)[0] not in fold(located)[0]:
            rejected += 1
            continue
        facts.append({'name': text(item.get('name'), 80), 'value': value, 'block_id': bid, 'quote': located})
    return {'facts': facts, 'rejected_facts': rejected}

def model_blocks(blocks: list[dict]) -> list[dict]:
    """What a model needs from a paragraph. Offsets, anchors and redaction spans stay server-side."""
    return [{'id': b['id'], 'text': b['text'], **({'page': b['page']} if b.get('page') else {})} for b in blocks]

def finding_brief(f: dict) -> dict:
    """A finding reduced to what whole-contract compatibility checks need."""
    return {'finding_id': f['id'], 'kind': f['kind'], 'block_id': f.get('block_id'), 'title': f['title'][:120],
            'severity': f.get('severity'), 'impact': (f.get('impact') or '')[:200],
            'suggested_text': f.get('suggested_text', '') if f.get('revision_allowed') else ''}

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
    # Ultra-fast findings were never sent to a critic: counted by severity, labelled unverified.
    if f.get('verification_status') == 'skipped' and f.get('evidence_status') != 'unverified' and not f.get('missing_facts'):
        return 'quick'
    # Legal findings keep their evidence label (official text attached, model-cited or none);
    # the reviewer still confirms the legal basis before any legal edit is adopted.
    if f.get('verification_status') != 'supported' or f.get('evidence_status') == 'unverified' or f.get('missing_facts'):
        return 'unconfirmed'
    return 'supported'


def summary(findings: list[dict], coverage: list[dict]) -> dict:
    supported = [f for f in findings if finding_status(f) in ('supported', 'quick')]
    return {'high': sum(f['severity'] == 'high' for f in supported),
            'medium': sum(f['severity'] == 'medium' for f in supported),
            'low': sum(f['severity'] == 'low' for f in supported),
            'unconfirmed': sum(finding_status(f) == 'unconfirmed' for f in findings),
            'rejected_candidates': sum(finding_status(f) == 'rejected' for f in findings),
            'unverified': sum(finding_status(f) == 'quick' for f in findings),
            'needs_confirmation': sum(finding_status(f) != 'rejected' and (not f.get('revision_allowed') or f['kind'] == 'legal') for f in findings),
            'checked_rules': sum(c['status'] in ('reviewed', 'not_applicable') and c.get('verification_status') == 'supported' for c in coverage),
            'total_rules': len(coverage),
            'notice': ('极速模式的风险数为模型直接给出的结果，未经独立复核；已否定项单列。规则覆盖不等于合同风险覆盖。'
                       if any(finding_status(f) == 'quick' for f in findings) else
                       '风险数只包含经复核支持的意见；待核实和已否定项单列。规则覆盖不等于合同风险覆盖。')}


def apply_cross_edit_checks(findings: list[dict], raw: Any) -> None:
    """A reported conflict blocks one-click adoption; a missing check is flagged, not fatal.

    The exact combination a reviewer selects is verified again before any export, so a
    failed or incomplete whole-contract pass must not silently erase every proposal.
    """
    items = [r for r in rows(raw.get('proposal_checks')) if isinstance(r, dict)] if isinstance(raw, dict) else []
    by_id: dict[str, list[dict]] = {}
    for item in items:
        by_id.setdefault(text(item.get('finding_id'), 100), []).append(item)
    for finding in findings:
        if finding.get('revision_allowed') is not True:
            continue
        entries = by_id.get(finding['id'], [])
        statuses = {e.get('status') for e in entries}
        reason = next((text(e.get('reason'), 1200) for e in entries if text(e.get('reason')).strip()), '')
        if 'conflict' in statuses:
            finding.update(cross_edit_status='conflict', revision_allowed=False, needs_confirmation=True,
                           cross_edit_note=reason or '与其他拟议修改存在冲突。')
            finding.setdefault('validation_warnings', []).append('与其他拟议修改存在冲突，请人工合并后再采纳。')
        elif statuses == {'consistent'}:
            finding.update(cross_edit_status='supported', cross_edit_note=reason)
        else:
            finding.update(cross_edit_status='unchecked',
                           cross_edit_note=reason or '尚未完成与其他拟议修改的交叉核对；导出前仍会核验实际选择的修改组合。')
