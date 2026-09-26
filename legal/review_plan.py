"""Frozen review plans: which checks run, from whose side. Search is planned by the model.

Plans carry no search queries. Legal research is planned per contract by the model
(legal.research); contracts and user instructions never become fixed search templates.
"""
from __future__ import annotations
from copy import deepcopy
from legal.external_law import article_units

ROLE_FOCUS = {
    '采购方': '我方付款换取交付，重点检查预付保障、明确交期、验收权、缺陷救济和供应方责任；不要套用收款方目标。',
    '供应方': '我方交付换取收款，重点检查付款起算、验收拖延、回款条件、需求变更和不对称责任。',
    '服务提供方': '重点检查服务范围和变更、验收标准、回款、客户配合义务、既有成果和责任边界。',
    '服务接受方': '重点检查服务交付标准、验收救济、成果使用权、数据义务和退出交接。',
    '披露方': '重点检查保密信息范围、获准接触者、用途限制、返还销毁和泄露救济；同时考虑合理例外。',
    '接收方': '重点检查可识别信息范围、合理例外、合法披露、期限及不受控第三方带来的责任。',
}
_SEARCH_FIELDS = ('query', 'keywords', 'queries', 'topics')


def _review_only(rule: dict) -> dict:
    for key in _SEARCH_FIELDS:
        rule.pop(key, None)
    return rule


def build_plan(base_rules: list[dict], blocks: list[dict], profile: dict, policies: list[dict], *, scenario: dict | None = None) -> list[dict]:
    rules = deepcopy(base_rules)
    for rule in rules:
        if scenario:
            rule.update(deepcopy(scenario.get('overrides', {}).get(rule['id'], {})))
            if rule['id'] == 'termination':
                rule['checks'] = '核对期限、终止事由、通知、补救和终止后存续义务；退款、退货只在该场景实际涉及时适用。'
        focus = (next((r['focus'] for r in scenario['roles'] if r['value'] == profile.get('our_role')), '立场不明时不要猜测。')
                 if scenario else ROLE_FOCUS.get(profile.get('our_role'), '立场不明时不要猜测。'))
        rule['checks'] += '\n我方利益检查：' + focus
        _review_only(rule)
    if scenario:
        for source in scenario['rules']:
            specific = deepcopy(source)
            specific['checks'] += '\n我方利益检查：' + profile['scenario']['role_focus']
            rules.append(_review_only(specific))
    for policy in policies:
        rules.append({'id': 'policy_' + policy['id'], 'title': policy['title'],
                      'checks': policy['text'], 'policy_id': policy['id']})
    return rules

def relevant_evidence(sources: list[dict], limit: int = 24000) -> list[dict]:
    """Keep complete article units. Mark excerpt scope; never trim a provision mid-sentence."""
    result, seen, used = [], set(), 0
    for source in sources:
        if source['id'] in seen:
            continue
        seen.add(source['id'])
        body = source.get('text', '')
        allowance = min(8000, limit - used)
        if allowance <= 0:
            break
        if len(body) > allowance:
            parts = article_units(body)
            selected, size = [], 0
            for part in parts:
                separator_length = len('\n[…]\n') if selected else 0
                if size + len(part) + separator_length <= allowance:
                    selected.append(part)
                    size += len(part) + separator_length
            body = '\n[…]\n'.join(selected)
            if not body.strip():
                continue
        used += len(body)
        result.append({**source, 'text': body, 'review_excerpt': len(body) < len(source.get('text', ''))})
    return result
