"""Explicit upload disclosure and a single redaction pass for review supplements.

Configured region is an operator declaration, not a verified compliance status.
Nothing in this module certifies lawful transfer, retention or vendor processing.
"""
from __future__ import annotations
from copy import deepcopy
import os
import re
from uuid import uuid4
from legal.contract_documents import redact_blocks

NOTICE_VERSION = 'original-upload-v1'


def disclosure() -> dict:
    return {'version': NOTICE_VERSION, 'storage_region': os.getenv('LEGAL_STORAGE_REGION', '').strip()[:120] or '未核验，请向运营方确认',
            'region_verified': False, 'provider': 'ydata', 'raw_upload_before_redaction': True,
            'notice': '上传的是原件，会先传至 CasualGraph 后端解析并加密保存，再在后端脱敏；不是浏览器本地脱敏。'
                      '后续经 YData 外发的正文、补充要求和公司规范须另行确认。'
                      '地域、保留期限及处理方协议需运营方核验；勾选不构成合规认证。敏感真实材料请先完成组织审批。'}


def redact_materials(contract_payload: dict, policies: list[dict], instructions: str) -> tuple[list[dict], str]:
    """One joint namespace, so two policies never assign one token to two people."""
    cloned = deepcopy(policies)
    values = [instructions]
    for policy in cloned:
        values.extend([policy['title'], policy['text']])
    protected: dict[str, str] = {}
    nonce = uuid4().hex
    def protect(match):
        marker = '\ue000' + nonce + ':' + str(len(protected)) + '\ue001'
        protected[marker] = match.group()
        return marker
    blocks = []
    for i, value in enumerate(values):
        for token, entity in sorted(contract_payload.get('mapping', {}).items(), key=lambda x: len(x[1]), reverse=True):
            value = value.replace(entity, token)
        value = re.sub(r'【(?:补充)?脱敏\d+】', protect, value)
        blocks.append({'id': str(i), 'text': value})
    output, mapping = redact_blocks(blocks)
    masked = []
    for block in output:
        value = block['text']
        for token in mapping:
            value = value.replace(token, token.replace('脱敏', '补充脱敏'))
        for marker, token in protected.items():
            value = value.replace(marker, token)
        masked.append(value)
    for i, policy in enumerate(cloned):
        policy['title'], policy['text'] = masked[1 + 2 * i:3 + 2 * i]
    return cloned, masked[0]


def bind_party(value: dict | None, blocks: list[dict]) -> dict:
    from fastapi import HTTPException
    if not value:
        raise HTTPException(422, '请指定我方主体所在段落及逐字原文；选择交易角色不能代替主体确认。')
    bid, quote = value.get('block_id'), value.get('quote', '')
    block = next((b for b in blocks if b['id'] == bid), None)
    if not block or not isinstance(quote, str) or not 2 <= len(quote.strip()) <= 200 or quote not in block['text']:
        raise HTTPException(422, '我方主体必须绑定本版本脱敏正文中的逐字片段，不能使用猜测或旧版位置。')
    return {'block_id': bid, 'quote': quote, 'confirmed_by': 'user'}
