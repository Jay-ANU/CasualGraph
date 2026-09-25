"""Follow-up tests with real SQLite/encryption, fixture-scoped synthetic APIs."""
import copy
import json
import sqlite3
import sys
import types
from contextlib import contextmanager
import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from legal import review_questions as questions, review_store as store

@pytest.fixture
def qdb(tmp_path, monkeypatch):
    path = tmp_path/'questions.db'
    cipher = Fernet(Fernet.generate_key())
    @contextmanager
    def transaction():
        conn = sqlite3.connect(path);conn.row_factory = sqlite3.Row
        try:
            conn.execute('BEGIN IMMEDIATE');yield conn;conn.commit()
        except BaseException:
            conn.rollback();raise
        finally:conn.close()
    monkeypatch.setattr(store,'transaction',transaction)
    monkeypatch.setattr(store,'encode',lambda x:cipher.encrypt(json.dumps(x,ensure_ascii=False).encode()))
    monkeypatch.setattr(store,'decode',lambda x:json.loads(cipher.decrypt(x)))
    monkeypatch.setattr(store,'audit',lambda *args,**kwargs:None)
    redaction=types.ModuleType('legal.contract_documents')
    def redact(blocks):
        value=copy.deepcopy(blocks)
        value[0]['text']=value[0]['text'].replace('13812345678','【脱敏1】')
        return value, {'【脱敏1】':'13812345678'} if '13812345678' in blocks[0]['text'] else {}
    redaction.redact_blocks=redact
    monkeypatch.setitem(sys.modules,'legal.contract_documents',redaction)
    return path

def context():
    return ({'id':'r1','status':'completed','payload':{'profile':{'external_processing_provider':'ydata','model':{'id':'glm-5.2','provider':'ydata'}},'findings':[]}},
            {'id':'c1','matter_id':'m1','org_id':'o1','payload':{'redacted_blocks':[{'id':'p1','text':'甲方收到货物后付款。'}],'mapping':{'【脱敏1】':'真实公司'}}})
def answer(*args,**kwargs):
    return {'answer':'付款应结合收到货物这一约定确认。','block_refs':[{'block_id':'p1','quote':'甲方收到货物后付款。'}],'citations':[],'uncertain':True}
def test_new_note_masks_do_not_rename_contract_tokens(qdb):
    value=questions.redact_note('真实公司（【脱敏1】）电话13812345678',{'mapping':{'【脱敏1】':'真实公司'}})
    assert value=='【脱敏1】（【脱敏1】）电话【补充脱敏1】'
    assert '\ue000' not in value
def test_followup_idempotency_and_encryption(qdb,monkeypatch):
    calls=[]
    def model(*args):calls.append(args);return answer()
    monkeypatch.setattr(questions.ydata,'chat_json',model)
    r,c=context()
    first=questions.ask(r,c,{'id':'u1'},'真实公司应该何时付款？','req1',lambda:None)
    assert questions.ask(r,c,{'id':'u1'},'真实公司应该何时付款？','req1',lambda:None)==first
    assert len(calls)==1 and first['question'].startswith('【脱敏1】')
    assert '真实公司'.encode() not in qdb.read_bytes()
    assert '应该何时付款'.encode() not in qdb.read_bytes()
    assert questions.history('r1','u2')==[]
    assert len(questions.history('r1','u1'))==1
def test_reused_request_id_different_question_rejected(qdb,monkeypatch):
    monkeypatch.setattr(questions.ydata,'chat_json',answer)
    r,c=context(); questions.ask(r,c,{'id':'u1'},'问题一','req1',lambda:None)
    with pytest.raises(HTTPException) as err:questions.ask(r,c,{'id':'u1'},'问题二','req1',lambda:None)
    assert err.value.status_code==409
def test_question_permission_revocation_never_publishes_answer(qdb,monkeypatch):
    monkeypatch.setattr(questions.ydata,'chat_json',answer)
    invocations=[]
    def authorize():
        invocations.append(1)
        if len(invocations)==3:raise HTTPException(403,'revoked')
    r,c=context()
    with pytest.raises(HTTPException):questions.ask(r,c,{'id':'u1'},'付款安排？','req1',authorize)
    records=questions.history('r1','u1')
    assert records[0]['status']=='failed' and not records[0]['answer']
def test_questions_bounded_to_four_per_minute(qdb,monkeypatch):
    monkeypatch.setattr(questions.ydata,'chat_json',answer)
    r,c=context()
    for i in range(4):questions.ask(r,c,{'id':'u1'},'付款安排？',f'req{i}',lambda:None)
    with pytest.raises(HTTPException) as err:questions.ask(r,c,{'id':'u1'},'付款安排？','req5',lambda:None)
    assert err.value.status_code==429
@pytest.mark.parametrize('raw',[None,[],{'answer':'x'*4001},{'answer':'合同已经违法','block_refs':[{'block_id':'p1','quote':'甲方收到货物后付款。'}]}])
def test_invalid_followup_fails_closed(raw):
    _,c=context();result=questions.validate_answer(raw,c['payload']['redacted_blocks'],[])
    assert result['uncertain'] is True and not result['citations']
