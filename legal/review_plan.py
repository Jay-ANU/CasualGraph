"""Public-topic retrieval plans; contracts and user instructions never become search queries."""
from __future__ import annotations
from copy import deepcopy
import re

# Search topics, not a bundled legal database or conclusions of law.
TOPICS = {
    'prepayment': {'rule': 'performance', 'terms': ('预付款', '提前支付', '签约后支付', '全额支付'), 'query': '民法典 买卖合同 交付期限 预付款 履行 抗辩权', 'keywords': ['交付', '期限', '履行']},
    'acceptance': {'rule': 'performance', 'terms': ('验收', '检验', '视为合格', '异议期'), 'query': '民法典 买卖合同 检验期限 验收 异议', 'keywords': ['检验', '期限', '通知']},
    'exemption': {'rule': 'liability', 'terms': ('免责', '不承担', '责任上限', '赔偿总额'), 'query': '民法典 第五百零六条 免责条款 故意 重大过失 财产损失', 'keywords': ['第五百零六条', '免责', '故意']},
    'penalty': {'rule': 'liability', 'terms': ('违约金', '赔偿金'), 'query': '合同编通则司法解释 第六十五条 违约金 损失 百分之三十', 'keywords': ['第六十五条', '违约金', '损失']},
    'renewal': {'rule': 'termination', 'terms': ('自动续', '续约', '续期'), 'query': '民法典 自动续约 合同解除 通知 期限', 'keywords': ['解除', '通知', '期限']},
    'personal_data': {'rule': 'ip_data', 'terms': ('个人信息', '用户数据', '委托处理', '数据出境'), 'query': '个人信息保护法 委托处理 合同 第二十一条 提供 境外', 'keywords': ['委托', '个人信息', '境外']},
    'copyright': {'rule': 'ip_data', 'terms': ('知识产权', '著作权', '源代码', '委托作品'), 'query': '著作权法 委托作品 合同 著作权 归属', 'keywords': ['委托', '合同', '著作权']},
    'arbitration': {'rule': 'disputes', 'terms': ('仲裁',), 'query': '仲裁法 最新 修订 施行 仲裁协议 仲裁机构', 'keywords': ['仲裁协议', '施行', '仲裁机构']},
    'standard_terms': {'rule': 'capacity', 'terms': ('格式条款', '最终解释权', '单方变更'), 'query': '民法典 格式条款 提示说明 解释 第四百九十六条', 'keywords': ['格式条款', '提示', '说明']},
}
ROLE_FOCUS = {
    '采购方': '我方付款换取交付，重点检查预付保障、明确交期、验收权、缺陷救济和供应方责任；不要套用收款方目标。',
    '供应方': '我方交付换取收款，重点检查付款起算、验收拖延、回款条件、需求变更和不对称责任。',
    '服务提供方': '重点检查服务范围和变更、验收标准、回款、客户配合义务、既有成果和责任边界。',
    '服务接受方': '重点检查服务交付标准、验收救济、成果使用权、数据义务和退出交接。',
    '披露方': '重点检查保密信息范围、获准接触者、用途限制、返还销毁和泄露救济；同时考虑合理例外。',
    '接收方': '重点检查可识别信息范围、合理例外、合法披露、期限及不受控第三方带来的责任。',
}

def build_plan(base_rules: list[dict], blocks: list[dict], profile: dict, policies: list[dict]) -> list[dict]:
    full_text = '\n'.join(b['text'] for b in blocks)
    rules = deepcopy(base_rules)
    for rule in rules:
        matches = [(key, value) for key, value in TOPICS.items() if value['rule'] == rule['id'] and any(t in full_text for t in value['terms'])]
        rule['topics'] = [key for key, _ in matches]
        rule['queries'] = [{'query': t['query'], 'keywords': t['keywords']} for _, t in matches]
        rule['queries'].append({'query': rule['query'], 'keywords': rule['keywords']})
        rule['queries'] = rule['queries'][:3]
        rule['checks'] += '\n我方利益检查：' + ROLE_FOCUS.get(profile.get('our_role'), '立场不明时不要猜测。')
    for policy in policies:
        rules.append({'id': 'policy_' + policy['id'], 'title': policy['title'],
                      'checks': policy['text'], 'topics': [], 'queries': [], 'policy_id': policy['id']})
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
            parts = re.split(r'(?=第[一二三四五六七八九十百千万零〇两\d]+条)', body)
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
