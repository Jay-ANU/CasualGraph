"""Role-scoped specialist contracts. They confer no additional permissions."""
from __future__ import annotations
from copy import deepcopy
from dataclasses import dataclass

@dataclass(frozen=True)
class Specialist:
    id: str
    title: str
    kind: str
    instructions: str

SPECIALISTS = (
    Specialist('legal', '法律风险审查', 'legal', '只判断法律效力、法定义务与可执行性。法律依据只能来自本轮外部原文，版本及适用条件不足时待确认。商业不利不是违法。'),
    Specialist('commercial', '公司利益审查', 'commercial', '从我方交易角色检查付款、交付、责任和退出成本。解释风险如何落到我方，提出可协商的条件；不作法律效力结论，不虚构公司底线。'),
    Specialist('policy', '公司规范审查', 'company_policy', '仅检查本轮固定版本公司规范的偏离、例外和审批要求。每项意见引用真实policy_id；公司规范不是法律，未提供的底线不得补造。'),
)

def build_tasks(plan: list[dict], batch_size: int = 3) -> list[dict]:
    if not 1 <= batch_size <= 6:
        raise ValueError('invalid_agent_batch_size')
    ordinary = [rule for rule in plan if not rule.get('policy_id')]
    policies = [rule for rule in plan if rule.get('policy_id')]
    tasks = []
    for specialist in SPECIALISTS:
        assigned = policies if specialist.id == 'policy' else ordinary
        for offset in range(0, len(assigned), batch_size):
            rules = []
            for original in assigned[offset:offset + batch_size]:
                rule = deepcopy(original)
                rule['origin_rule_id'] = rule['id']
                rule['id'] = specialist.id + ':' + rule['id']
                rule['title'] = specialist.title + ' / ' + rule['title']
                rules.append(rule)
            tasks.append({'id': specialist.id + ':' + str(offset), 'agent_id': specialist.id,
                          'title': specialist.title, 'kind': specialist.kind,
                          'instructions': specialist.instructions, 'rules': rules})
    return tasks

def enforce_specialist_scope(result: dict, task: dict) -> dict:
    checked = deepcopy(result)
    accepted, invalid_rules = [], set()
    for finding in checked.get('findings', []):
        if finding.get('kind') != task['kind']:
            checked['rejected_findings'] = checked.get('rejected_findings', 0) + 1
            invalid_rules.add(finding.get('rule_id'))
            continue
        finding.update(agent_id=task['agent_id'], agent_title=task['title'])
        accepted.append(finding)
    checked['findings'] = accepted
    for item in checked.get('coverage', []):
        item['agent_id'] = task['agent_id']
        if item.get('rule_id') in invalid_rules:
            item.update(status='needs_information', verification_status='uncertain',
                        note='候选意见超出本 Agent 职责，需要重新检查。')
    return checked

def initial_team(tasks: list[dict]) -> list[dict]:
    return [{'id': spec.id, 'title': spec.title,
             'status': 'pending' if any(t['agent_id'] == spec.id for t in tasks) else 'not_applicable',
             'completed': 0, 'total': sum(t['agent_id'] == spec.id for t in tasks),
             'note': '' if spec.id != 'policy' or any(t['agent_id'] == 'policy' for t in tasks)
             else '本轮没有适用的公司规范，不自行生成公司制度。'} for spec in SPECIALISTS]
