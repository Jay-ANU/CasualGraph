"""Frozen, provenance-labelled transaction context and bounded material-gap gates.

User statements are not verified contract facts. No network/model calls here.
"""
from __future__ import annotations
from copy import deepcopy
from decimal import Decimal
import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

VERSION = 1


class TransactionContext(BaseModel):
    model_config = ConfigDict(extra='forbid')
    performance_stage: Literal['拟签署', '谈判中', '已签署未履行', '履行中', '发生争议', '未知'] = '未知'
    attachments_status: Literal['已提供全部关键附件', '存在未提供附件', '无附件', '未知'] = '未知'
    business_priority: Literal['付款与回款', '交付与验收', '责任限制', '退出与解除', '知识产权', '保密与数据', '综合审查'] = '综合审查'
    deal_value: Decimal | None = Field(default=None, ge=0, le=Decimal('1000000000000'), max_digits=15, decimal_places=2, allow_inf_nan=False)
    currency: Literal['CNY', 'USD', 'EUR', 'HKD', 'OTHER'] = 'CNY'

    @field_validator('deal_value', mode='before')
    @classmethod
    def validate_amount(cls, value):
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
            raise ValueError('金额必须是非负十进制数，不能是布尔值或对象。')
        if isinstance(value, str) and not re.fullmatch(r'\d{1,13}(?:\.\d{1,2})?', value):
            raise ValueError('金额请使用最多两位小数的非负数字，不使用单位或科学计数法。')
        return value


def material_references(blocks: list[dict]) -> list[dict]:
    """Flag explicit references, not every occurrence of the word attachment."""
    refs = []
    pattern = re.compile(r'(?:详见|参见|依据|按照|根据|以|见)[^。；\n]{0,18}(?:附件|附表|技术规格书|工作说明书)|(?:附件|附表)\s*[一二三四五六七八九十\dA-Z]')
    for b in blocks:
        matches = list(pattern.finditer(b['text']))
        if matches:
            # Retain the full block ID; excerpts remain exact substrings.
            refs.append({'block_id': b['id'], 'quote': matches[0].group(), 'source': 'contract_text'})
    return refs


def build_brief(profile: dict, blocks: list[dict], warnings: list[str]) -> dict:
    context = deepcopy(profile.get('transaction_context') or {})
    refs = material_references(blocks)
    state = context.get('attachments_status', '未知')
    missing, barriers = [], []
    if context.get('performance_stage', '未知') == '未知':
        missing.append({'code': 'stage_unknown', 'message': '履行阶段未提供，不能假定合同尚未签署。', 'source': 'not_provided'})
    if not profile.get('transaction_date'):
        missing.append({'code': 'date_unknown', 'message': '交易日期未提供，法律时间适用仍需核验。', 'source': 'not_provided'})
    if state == '存在未提供附件' or (refs and state in ('未知', '无附件')):
        message = ('你填写了“无附件”，但正文引用了附件或外部规格，请核对资料。' if state == '无附件' else
                   '存在未提供或尚未确认的附件；无法从当前材料确认依赖附件的具体约定。')
        missing.append({'code': 'attachment_gap', 'message': message, 'source': 'user_statement_and_contract' if refs else 'user_statement'})
        barriers = [r['block_id'] for r in refs]
    if warnings:
        missing.append({'code': 'parsing_limits', 'message': '文件解析存在范围限制，请核对提示中的内容是否影响本轮判断。', 'source': 'parser'})
    return {'version': VERSION, 'context': context, 'context_source': 'user_statement_not_independently_verified',
            'transaction_date': profile.get('transaction_date'), 'our_party': deepcopy(profile.get('our_party')),
            'material_references': refs, 'gaps': missing, 'blocked_edit_blocks': barriers,
            'included_blocks': len(blocks), 'parsing_warnings': list(warnings),
            'notice': '用户填写的交易背景、原文事实和资料缺口分开保存；声明附件齐全不等于系统已验证齐全。'}


def apply_material_gates(checked: dict, brief: dict | None) -> None:
    """An edited paragraph depending on unavailable material cannot pass by omission."""
    if not brief:
        return
    blocked = set(brief.get('blocked_edit_blocks', []))
    gap = '本段引用的附件或规格尚未确认完整，需补充材料后新建审查。'
    for f in checked.get('findings', []):
        if f.get('block_id') not in blocked:
            continue
        if gap not in f.setdefault('missing_facts', []):
            f['missing_facts'].append(gap)
        if gap not in f.setdefault('validation_warnings', []):
            f['validation_warnings'].append(gap)
        f.update(revision_allowed=False, needs_confirmation=True)
