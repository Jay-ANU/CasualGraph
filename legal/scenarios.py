"""Versioned business scenarios, not legal classifications or bundled statutes.

Only repository-controlled data may define rules or public search topics. User
requests select a label/role; they cannot supply or override a scenario template.
"""
from __future__ import annotations
from copy import deepcopy
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re

VERSION = 1
CATALOG_PATH = Path(__file__).with_name('contract_scenarios.json')
BASE_IDS = frozenset({'capacity', 'performance', 'liability', 'termination', 'ip_data', 'disputes'})


@lru_cache(maxsize=1)
def _catalog() -> dict:
    data = json.loads(CATALOG_PATH.read_text(encoding='utf-8'))
    if data.get('version') != VERSION or not isinstance(data.get('scenarios'), list):
        raise ValueError('invalid_scenario_catalog')
    labels, ids, aliases, rule_ids = set(), set(), set(), set()
    for scene in data['scenarios']:
        if (not re.fullmatch(r'[a-z][a-z_]{1,40}', scene['id']) or scene['id'] in ids
                or scene['label'] in labels or not scene['roles'] or len(scene['rules']) != 3
                or not set(scene['overrides']).issubset(BASE_IDS)):
            raise ValueError('invalid_scenario_definition')
        ids.add(scene['id']); labels.add(scene['label'])
        roles = [r['value'] for r in scene['roles']]
        if len(roles) != len(set(roles)) or any(not r['focus'].strip() for r in scene['roles']):
            raise ValueError('invalid_scenario_roles')
        for alias in scene.get('aliases', []):
            if not alias or alias in aliases:
                raise ValueError('invalid_scenario_alias')
            aliases.add(alias)
        for rule in scene['rules']:
            if (not rule['id'].startswith('scenario_' + scene['id'] + '_') or rule['id'] in rule_ids
                    or any(not rule.get(key) for key in ('title', 'checks', 'query', 'keywords'))):
                raise ValueError('invalid_scenario_rule')
            rule_ids.add(rule['id'])
    if aliases & labels:
        raise ValueError('ambiguous_scenario_alias')
    data['revision'] = hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return data


def normalize_type(value: str, *, policy: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError('请选择有效的合同类型。')
    value = value.strip()
    if policy and value == '全部':
        return value
    for scene in _catalog()['scenarios']:
        if value == scene['label'] or value in scene.get('aliases', []):
            return scene['label']
    raise ValueError('不支持此合同类型，请刷新场景目录或明确选择其他商事合同。')


def get_scenario(value: str) -> dict:
    label = normalize_type(value)
    return deepcopy(next(s for s in _catalog()['scenarios'] if s['label'] == label))


def validate_role(contract_type: str, role: str) -> str:
    scene = get_scenario(contract_type)
    role = role.strip()
    if role not in [r['value'] for r in scene['roles']]:
        raise ValueError('我方角色与合同场景不匹配，请重新选择；不能沿用上一份合同的角色。')
    return role


def descriptor(scene: dict, role: str | None = None) -> dict:
    result = {key: deepcopy(scene[key]) for key in ('id', 'label', 'group', 'roles', 'materials', 'limits')}
    result.update(catalog_version=VERSION, catalog_revision=_catalog()['revision'],
                  checks=[{'id': r['id'], 'title': r['title']} for r in scene['rules']])
    if role is not None:
        result['role_focus'] = next(r['focus'] for r in scene['roles'] if r['value'] == role)
    return result


def catalog() -> dict:
    data = _catalog()
    return {'version': VERSION, 'revision': data['revision'], 'notice': data['notice'],
            'scenarios': [descriptor(s) for s in data['scenarios']]}


def matching_policies(policies: list[dict], contract_type: str, role: str) -> list[dict]:
    """Exact scenario + optional role. Never inherit purchase rules into sales."""
    label = normalize_type(contract_type)
    found = []
    for policy in policies:
        try:
            kind = normalize_type(policy.get('contract_type', ''), policy=True)
        except ValueError:
            continue
        if kind in ('全部', label) and (not policy.get('our_roles') or role in policy['our_roles']):
            found.append(deepcopy(policy))
    return found
