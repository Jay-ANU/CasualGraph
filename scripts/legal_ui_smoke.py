"""Actual React build regression with synthetic APIs, never production credentials."""
import traceback
from contextlib import contextmanager
import functools
import hashlib
import http.server
import json
import os
from pathlib import Path
import re
import threading
import time
from urllib.parse import parse_qs, urlparse
from playwright.sync_api import expect, sync_playwright

ROOT=Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))
from legal.scenarios import catalog, descriptor, get_scenario
SCENARIOS = catalog()
OUT=ROOT/'ui-artifacts'; OUT.mkdir(exist_ok=True)
class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if not (Path(self.directory)/self.path.lstrip('/').split('?')[0]).is_file():
            self.path='/index.html'
        super().do_GET()
    def log_message(self,*args):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',4173),functools.partial(Handler,directory=str(ROOT/'frontend/dist')))
threading.Thread(target=server.serve_forever,daemon=True).start()
contract={'id':'c1','name':'测试采购合同.txt','status':'redaction_pending','revision':1,'redaction_version':2,'format':'txt','matter_id':'m1','org_id':'o1','warnings':[], 'replacement_count':1,'reviews':[], 'blocks':[{'id':'p1','text':'【脱敏1】应在签约后支付全部价款，交货时间另行通知。','page':None}]}
finding={'id':'f1','rule_id':'performance','block_id':'p1','original_quote':contract['blocks'][0]['text'],'title':'付款与交货保障不匹配','kind':'commercial','severity':'high','impact':'我方预先承担全部资金风险。','reason':'付款条件未与确定的交货期限挂钩。','suggested_text':'【脱敏1】在交货验收后支付价款，交货应在签约后三十日内完成。','evidence_status':'not_applicable','missing_facts':[],'citations':[],'policy_ids':[],'verification_status':'supported','revision_allowed':True}
review={'id':'r1','contract_id':'c1','status':'completed','stage':'检查完成，等待人工逐条复核','resumable':False,'engine_version':2,'profile':{'model':{'id':'glm-5.2','provider':'ydata'},'review_mode':'multi_agent'},'error':None,'findings':[finding],'coverage':[{'rule_id':'performance','title':'交付、验收与付款','status':'reviewed','note':'合成测试样例'}],'sources':[],'decisions':{},'policies':[],'notice':'合成测试数据，不是法律结论。'}
review['collaboration']={'version':1,'max_parallel':3,'call_budget':40,'agents':[{'id':'legal','title':'法律风险审查','status':'completed','completed':2,'total':2,'note':''}]}
policies=[]; calls=[]; export_requests=[]; review_requests=[]; model_requests=[]; allowed={'value':True,'plan':'max','unavailable':False}
model_actions={'allowed':False,'reject_next_create':False}
model_catalog={'provider':'mixed','models':[{'id':'gpt-fixture','family':'GPT','provider':'ydata'},
    {'id':'claude-fixture','family':'Claude','provider':'anthropic'},{'id':'deepseek-fixture','family':'DeepSeek','provider':'ydata'},
    {'id':'kimi-fixture','family':'Kimi','provider':'ydata'},{'id':'glm-5.2','family':'GLM','provider':'ydata'}],
    'families':['GPT','Claude','DeepSeek','Kimi','GLM'],'default_model':'glm-5.2','notice':'synthetic','provider_errors':[]}
# The started review stays running until the test has checked the progress view.
running={'value':False,'step':0}
def running_review():
    # A multi-agent review mid-flight; the test advances `step` to show an agent finishing an item.
    step=running['step']
    agents=[{'id':'legal','title':'法律风险审查','status':'running','completed':step,'total':2,'note':f'第 {step+1}/2 项：付款与交付、验收'},
            {'id':'commercial','title':'公司利益审查','status':'running','completed':1,'total':2,'note':'第 2/2 项：违约责任、争议解决'},
            {'id':'policy','title':'公司规范审查','status':'not_applicable','completed':0,'total':0,'note':'本轮没有适用的公司规范，不自行生成公司制度。'},
            {'id':'critic','title':'证据与覆盖复核','status':'running','completed':1+step,'total':4,'note':''},
            {'id':'arbiter','title':'全文协调与冲突检查','status':'pending','completed':0,'total':1,'note':''}]
    return {**review,'status':'running','stage':'多个审查 Agent 正在分别检查合同','findings':[],'created_at':time.time()-95,
            'progress':{'phase':'collaboration','completed':1+step,'total':5},'metrics':{'model_calls':5+2*step},
            'collaboration':{**review['collaboration'],'agents':agents}}
def review_view():
    decisions=review['decisions']
    ids={f['id'] for f in review['findings']}
    pending=sum(decisions.get(fid,{}).get('decision') not in ('accepted','rejected') for fid in ids)
    selected=sum(decisions.get(fid,{}).get('decision') in ('accepted','draft') for fid in ids)
    fingerprint=hashlib.sha256(json.dumps({'decisions':decisions,'findings':review['findings']},sort_keys=True).encode()).hexdigest()
    return {**review,'export_state':{'ready':review['status'] in ('completed','partial'),'pending_count':pending,'selected_count':selected,
            'fingerprint':fingerprint,'confirmation_required':pending>0}}

headers={'Access-Control-Allow-Origin':'*','Access-Control-Allow-Methods':'GET,POST,PUT,PATCH,DELETE,OPTIONS','Access-Control-Allow-Headers':'authorization,content-type'}
def route_api(route):
    req=route.request; path=urlparse(req.url).path; method=req.method; calls.append((method,path))
    if method=='OPTIONS':route.fulfill(status=204,headers=headers);return
    status,data=200,{}
    if path=='/auth/me':data={'user':{'id':'u1','username':'测试法务','email':'test@example.com','role':'user','plan':'max'}}
    elif path=='/legal/access':
        status=503 if allowed['unavailable'] else 200
        data={'allowed':allowed['value'],'plan':allowed['plan'],'required_plan':'max'}
    elif path=='/legal/workspace':data={'matter_id':'m1','org_id':'o1'}
    elif path=='/matters':data={'matters':[{'id':'m1','org_id':'o1','name':'合成测试事项'}]}
    elif path=='/legal/capabilities':data={'model_gateway':'mixed','model_selection_version':2,'review_tiers':['ultra_fast','fast','standard','deep'],'model_configured':True,'encryption_configured':True,'review_engine_version':2,'followup_questions':True,'collaboration_version':1,'audit_foundation_version':1,'draft_release_version':2,'scenario_catalog':SCENARIOS,'scenario_catalog_version':1,'upload_disclosure':{'version':'original-upload-v1','notice':'合成上传说明：原件先到后端再脱敏。','storage_region':'合成环境'},'law_search':{'provider':'synthetic','notice':'test'}}
    elif path=='/legal/models':data=model_catalog
    elif path=='/legal/contracts' and method=='GET':data={'contracts':[contract] if any(m=='POST' and p==path for m,p in calls) else []}
    elif path=='/legal/contracts' and method=='POST':
        assert b'original_upload_confirmed' in req.post_data_buffer and b'original-upload-v1' in req.post_data_buffer
        data=contract
    elif path=='/legal/contracts/c1':data=contract
    elif path=='/legal/contracts/c1/original-text':data={'blocks':[{'id':'p1','text':'原件对照合成姓名：张三','page':None}]}
    elif path.endswith('/redaction'):
        if req.post_data_json.get('confirmed'):contract['status']='ready'
        data={'blocks':contract['blocks'],'confirmed':req.post_data_json.get('confirmed')}
    elif path=='/legal/contracts/c1/reviews':
        payload=req.post_data_json
        review_requests.append(payload)
        model=next(m for m in model_catalog['models'] if m['id']==payload['model_id'])
        assert payload['external_processing_provider']==model['provider']
        assert payload['external_processing_confirmed'] is True and contract['status']=='ready'
        if model_actions['reject_next_create']:
            model_actions['reject_next_create']=False
            route.fulfill(status=409,headers=headers,content_type='application/json',body=json.dumps({'detail':{
                'error':'legal_model_provider_changed','message':'所选模型的处理方已变化，请重新选择模型并确认外部处理方。'}},ensure_ascii=False));return
        assert (payload['model_id'],payload['review_tier'],payload['review_mode']) in (
            ('glm-5.2','deep','multi_agent'),('claude-fixture','ultra_fast','standard'))
        assert payload['our_party']=={'block_id':'p1','quote':'【脱敏1】'}
        assert payload['contract_type']=='销售合同' and payload['our_role']=='销售方'
        assert payload['scenario_revision']==SCENARIOS['revision']
        assert payload['our_role']=='销售方' and payload['instructions']=='重点关注付款安排'
        assert payload['transaction_context']=={'performance_stage':'谈判中','attachments_status':'未知','business_priority':'付款与回款','deal_value':'1000000.05','currency':'CNY'}
        review['profile'].update(model=dict(model),review_tier=payload['review_tier'],review_mode=payload['review_mode'],instructions=payload['instructions'],
            transaction_context=payload['transaction_context'], contract_type=payload['contract_type'], our_role=payload['our_role'], our_party=payload['our_party'], scenario=descriptor(get_scenario('销售合同'),'销售方'))
        review['review_tier']=payload['review_tier']
        review['transaction_brief']={'version':1,'context':payload['transaction_context'],'context_source':'user_statement_not_independently_verified',
            'material_references':[], 'gaps':[{'code':'date_unknown','message':'交易日期未提供，法律时间适用仍需核验。','source':'not_provided'}],
            'notice':'合成背景，不是已核实交易事实。'}
        review['evidence_health']={'queried_topics':6,'topics_with_sources':4,'failed_or_empty_topics':2,'source_count':0,'non_authoritative_sources':0,'version_pending':0,'status':'gaps','notice':'合成检索状态。'}
        contract['reviews']=[{'id':'r1','status':'completed'}]
        if payload['review_tier']=='ultra_fast':
            running['value']=False
            review.update(status='completed',stage='极速审查完成，修订稿已就绪，可直接查看、修改并导出。',findings=[finding],
                decisions={'f1':{'decision':'draft','text':finding['suggested_text'],'version':1,'source':'model',
                    'manual_edit_confirmed':False,'legal_basis_confirmed':False}})
            review.pop('draft_check',None);review.pop('draft_approval',None)
            data=review_view()
        else:running['value']=True;data=running_review()
    elif path=='/legal/reviews/r1':data=running_review() if running['value'] else review_view()
    elif path.startswith('/legal/reviews/r1/findings/'):
        fid=path.rsplit('/',1)[1];payload=req.post_data_json
        old=review['decisions'].get(fid,{})
        assert payload['expected_version']==old.get('version',0)
        data={**payload,'version':old.get('version',0)+1,'source':'user'}
        review['decisions'][fid]=data
    elif path=='/legal/reviews/r1/draft-approval':
        raise AssertionError('Export must not call model-approval endpoints')
    elif path=='/legal/reviews/r1/draft-check':
        assert model_actions['allowed'],'Export must not call model-check endpoints'
        payload=req.post_data_json
        assert payload['external_processing_provider']==review['profile']['model']['provider']
        assert payload['external_processing_confirmed'] is True
        model_requests.append({'action':'check','provider':payload['external_processing_provider']})
        review['draft_check']={'id':'optional','fingerprint':review_view()['export_state']['fingerprint'],'final_hash':'synthetic',
            'status':'verified','checks':[],'whole_contract':{'status':'supported','reason':'合成可选复核完成。'},'missing_facts':[]}
        data=review_view()
    elif path=='/legal/reviews/r1/export':
        query=parse_qs(urlparse(req.url).query);export_requests.append(query)
        view=review_view();state=view['export_state']
        if query.get('format')==['json']:
            data=view
        elif query.get('fingerprint') != [state['fingerprint']]:
            status=409;data={'detail':{'code':'export_stale','message':'修订稿已变化，请刷新后重新导出。',
                'pending_count':state['pending_count'],'fingerprint':state['fingerprint']}}
        elif state['pending_count'] and query.get('confirmed') != ['true']:
            status=409;data={'detail':{'code':'export_confirmation_required','message':'请确认待处理项。',
                'pending_count':state['pending_count'],'fingerprint':state['fingerprint']}}
        else:
            blocks=[]
            for block in contract['blocks']:
                revised=next((review['decisions'][f['id']]['text'] for f in review['findings'] if f.get('block_id')==block['id']
                    and review['decisions'].get(f['id'],{}).get('decision') in ('accepted','draft')),None)
                blocks.append(revised or block['text'])
            text='\n'.join(blocks)
            mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document' if query.get('format')==['docx'] else 'text/plain; charset=utf-8'
            route.fulfill(status=200,headers=headers,content_type=mime,body=text);return
    elif path=='/legal/reviews/r1/questions':
        if method=='GET':data={'messages':[]}
        else:
            assert model_actions['allowed'],'Questions require an explicit user action'
            payload=req.post_data_json
            assert payload['external_processing_provider']==review['profile']['model']['provider']
            assert payload['external_processing_confirmed'] is True
            model_requests.append({'action':'question','provider':payload['external_processing_provider']})
            data={'id':f'q{len(model_requests)}','question':payload['question'],'answer':'合成回答：请核对合同付款节点。','status':'completed','block_refs':[{'block_id':'p1','quote':'【脱敏1】'}]}
    elif path=='/legal/policies' and method=='GET':data={'policies':policies}
    elif path=='/legal/policies' and method=='POST':
        assert req.post_data_json['contract_type']=='销售合同' and req.post_data_json['our_roles']==['销售方']
        data={**req.post_data_json,'id':'policy1','version':1}; policies.append(data)
    else:status,data=404,{'detail':'Unhandled synthetic route: '+path}
    route.fulfill(status=status,headers=headers,content_type='application/json',body=json.dumps(data,ensure_ascii=False))
@contextmanager
def capture_failure():
    try:
        yield
    except Exception:
        try:
            (OUT/'failure.txt').write_text(traceback.format_exc() + '\nACTIVE: ' + str(page.evaluate('document.activeElement.outerHTML')), encoding='utf-8')
            page.screenshot(path=str(OUT/'failure.png'), full_page=True)
            (OUT/'failure.html').write_text(page.content(), encoding='utf-8')
        except Exception:
            pass
        raise

AXE_VIOLATIONS = []
def settle(page):
    """Wait for entrance animations; looping ones (live progress) are left running."""
    page.evaluate("""() => Promise.all(document.getAnimations()
        .filter(a => a.effect && a.effect.getComputedTiming().endTime !== Infinity)
        .map(a => a.finished.catch(() => null)))""")
def audit_layout(page, label):
    """Real DOM reflow and optional axe checks; synthetic data only."""
    widths = (320, 390, 768, 1024, 1440)
    for width in widths:
        page.set_viewport_size({'width': width, 'height': 960 if width >= 768 else 844})
        page.wait_for_timeout(80)
        settle(page)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2'), (label, width)
        page.screenshot(path=str(OUT/f'{label}-{width}.png'), full_page=True)
    axe_path = os.getenv('AXE_CORE_PATH')
    if axe_path:
        page.add_script_tag(path=axe_path)
        result = page.evaluate("""async () => await axe.run('.legal-v2', {runOnly: {type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']}})""")
        (OUT/f'{label}-axe.json').write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
        violations = [{ 'id': v['id'], 'impact': v['impact'], 'nodes': [n['target'] for n in v['nodes']] } for v in result['violations']]
        AXE_VIOLATIONS.extend([{'state': label, **v} for v in violations])

try:
    with sync_playwright() as p, capture_failure():
        browser=p.chromium.launch(executable_path=os.getenv('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or None)
        for plan in ('free','pro','unavailable'):
            allowed.update(value=False,plan=plan,unavailable=plan=='unavailable')
            context=browser.new_context()
            context.add_init_script("localStorage.setItem('token','synthetic');localStorage.setItem('user',JSON.stringify({id:'u1',role:'user',plan:'max'}));")
            page=context.new_page();page.route('http://127.0.0.1:8000/**',route_api)
            start=len(calls);page.goto('http://127.0.0.1:4173/legal');page.wait_for_timeout(800)
            expect(page.get_by_role('button',name='选择文件',exact=True)).to_have_count(0)
            assert not any(path in ('/legal/workspace','/legal/models','/legal/contracts') for _,path in calls[start:])
            if plan=='pro':
                page.set_viewport_size({'width':1440,'height':900});page.wait_for_timeout(600)
                page.screenshot(path=str(OUT/'legal-gate.png'))
            context.close()
        allowed.update(value=True,plan='max',unavailable=False)
        context=browser.new_context(viewport={'width':1440,'height':1000})
        context.add_init_script("localStorage.setItem('token','synthetic');localStorage.setItem('user',JSON.stringify({id:'u1',role:'user',plan:'max'}));")
        page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('dialog',lambda d:d.accept());page.route('http://127.0.0.1:8000/**',route_api)
        page.goto('http://127.0.0.1:4173/legal')
        page.get_by_role('heading',name='合同库').wait_for()
        expect(page.get_by_role('button',name='选择文件',exact=True)).to_be_enabled()
        # Model choice is not a first-screen decision; it lives in the review settings.
        expect(page.get_by_label('审查模型')).to_have_count(0)
        page.screenshot(path=str(OUT/'legal-v2-welcome-desktop.png'),full_page=True)
        audit_layout(page, 'legal-welcome')
        page.set_viewport_size({'width':1440,'height':1000})
        page.locator('input[type=file]').set_input_files({'name':'test.txt','mimeType':'text/plain','buffer':'合成合同'.encode()})
        dialog = page.get_by_role('dialog', name='上传确认')
        expect(dialog).to_be_visible()
        assert not any(method == 'POST' and path == '/legal/contracts' for method, path in calls)
        expect(dialog.get_by_role('button', name='取消', exact=True)).to_be_focused()
        for _ in range(6):
            page.keyboard.press('Tab')
            assert page.evaluate("document.querySelector('dialog').contains(document.activeElement)")
        page.keyboard.press('Escape')
        expect(dialog).to_have_count(0)
        assert not any(method == 'POST' and path == '/legal/contracts' for method, path in calls)
        page.locator('input[type=file]').set_input_files({'name':'test.txt','mimeType':'text/plain','buffer':'合成合同'.encode()})
        page.screenshot(path=str(OUT/'legal-upload-consent.png'), full_page=True)
        page.get_by_role('button', name='同意并上传', exact=True).click()
        # Redaction: the paper shows the placeholders; the original is only fetched on request.
        steps=page.get_by_role('list',name='合同审查步骤')
        expect(steps.locator('[aria-current="step"]')).to_have_text('1脱敏')
        expect(page.get_by_role('region',name='合同正文').locator('.lv-redacted')).to_have_count(1)
        compare=page.get_by_role('button',name='对照原件',exact=True)
        compare.click();expect(compare).to_have_attribute('aria-pressed','true')
        expect(page.get_by_text('原件对照合成姓名：张三',exact=False)).to_be_visible()
        compare.click();expect(compare).to_have_attribute('aria-pressed','false')
        expect(page.get_by_text('原件对照合成姓名：张三',exact=False)).to_have_count(0)
        page.screenshot(path=str(OUT/'legal-redaction.png'))
        page.get_by_role('button',name='确认脱敏',exact=True).click()
        page.get_by_role('button',name='确认并继续',exact=True).click()
        expect(page.get_by_role('radiogroup',name='我方身份').get_by_role('radio',checked=True)).to_have_count(0)
        expect(page.get_by_label('审查模型')).to_have_value('glm-5.2')
        expect(page.get_by_label('审查模型').locator('optgroup')).to_have_count(5)
        # All configured routes and role sets render from the backend catalogue.
        expect(page.get_by_label('合同类型',exact=True)).to_have_value('采购合同')
        for scene in SCENARIOS['scenarios']:
            page.get_by_label('合同类型',exact=True).select_option(scene['label'])
            expect(page.get_by_role('radiogroup',name='我方身份').get_by_role('radio',checked=True)).to_have_count(0)
            expect(page.get_by_role('radiogroup',name='我方身份').get_by_role('radio')).to_have_count(len(scene['roles']))
            page.get_by_role('radiogroup',name='我方身份').get_by_role('radio',name=scene['roles'][0]['value'],exact=True).check()
        page.get_by_label('合同类型',exact=True).select_option('销售合同')
        expect(page.get_by_role('radiogroup',name='我方身份').get_by_role('radio',checked=True)).to_have_count(0)
        page.get_by_role('radiogroup',name='我方身份').get_by_role('radio',name='销售方',exact=True).check()
        # Party suggestions quote the contract verbatim; nothing is pre-selected.
        parties=page.get_by_role('group',name='从原文选择主体片段')
        expect(parties.get_by_role('button',pressed=True)).to_have_count(0)
        # The quote names the button; the line it came from describes it.
        expect(parties.get_by_role('button', name='【脱敏1】', exact=True)).to_have_accessible_description(re.compile('应在签约后支付'))
        # The same quote can be picked on the paper, and both stay in step.
        page.get_by_role('button', name='在正文中选择我方主体：【脱敏1】', exact=True).click()
        expect(parties.get_by_role('button', name='【脱敏1】', exact=True)).to_have_attribute('aria-pressed','true')
        expect(page.get_by_role('button', name='在正文中选择我方主体：【脱敏1】', exact=True)).to_have_attribute('aria-pressed','true')
        page.get_by_label('审查重点',exact=True).fill('重点关注付款安排')
        page.get_by_text('交易信息（选填）',exact=True).click()
        page.get_by_label('履行阶段').select_option('谈判中')
        page.get_by_label('关键附件状态').select_option('未知')
        page.get_by_label('业务优先级').select_option('付款与回款')
        page.get_by_label('交易金额',exact=True).fill('-3')
        expect(page.get_by_text('金额格式有误：仅支持数字，最多两位小数。',exact=True)).to_be_visible()
        page.get_by_label('交易金额',exact=True).fill('1000000.05')
        consent=page.get_by_label('同意将脱敏后的合同文本、审查重点及适用的公司规范经 YData 网关提交所选模型分析')
        consent.check();page.get_by_label('合同类型',exact=True).select_option('保密协议');expect(consent).not_to_be_checked()
        expect(page.get_by_role('radiogroup',name='我方身份').get_by_role('radio',checked=True)).to_have_count(0)
        consent.check()
        expect(page.get_by_role('button',name='开始审查',exact=True)).to_be_disabled()
        page.get_by_label('合同类型',exact=True).select_option('销售合同');page.get_by_role('radiogroup',name='我方身份').get_by_role('radio',name='销售方',exact=True).check()
        # Four tiers; standard is the default, and changing the tier withdraws the model-processing consent.
        tiers=page.get_by_role('radiogroup',name='审查档位')
        expect(tiers.get_by_role('radio')).to_have_count(4)
        expect(page.get_by_role('radio',name='标准审查',exact=True)).to_be_checked()
        consent.check();page.get_by_role('radio',name='极速审查',exact=True).check();expect(consent).not_to_be_checked()
        expect(page.get_by_text('不检索法规、不做独立复核',exact=False)).to_be_visible()
        page.get_by_role('radio',name='深度审查',exact=True).check()
        consent.check();page.get_by_label('审查模型').select_option('claude-fixture')
        claude_consent=page.get_by_label('同意将脱敏后的合同文本、审查重点及适用的公司规范提交 Anthropic 官方 API，由所选 Claude 模型分析')
        expect(claude_consent).not_to_be_checked()
        expect(page.get_by_text('处理方：Anthropic 官方 API',exact=True)).to_be_visible()
        # A catalogue refresh can change the recipient while keeping the same model id.
        claude_model=next(m for m in model_catalog['models'] if m['id']=='claude-fixture')
        claude_consent.check();claude_model['provider']='ydata'
        page.get_by_role('button',name='刷新模型列表',exact=True).click()
        expect(consent).not_to_be_checked()
        expect(page.get_by_label('审查模型')).to_have_value('claude-fixture')
        consent.check();claude_model['provider']='anthropic'
        page.get_by_role('button',name='刷新模型列表',exact=True).click()
        expect(claude_consent).not_to_be_checked()
        page.get_by_label('审查模型').select_option('glm-5.2');consent.check()
        page.screenshot(path=str(OUT/'legal-scenario-setup.png'),full_page=True)
        page.get_by_role('button',name='开始审查',exact=True).click()
        # While the review runs, the phase, each agent's current item, elapsed time and a live feed are shown.
        expect(page.get_by_role('heading',name='审查中')).to_be_visible()
        agents=page.get_by_label('协作进度')
        expect(agents).to_be_visible()
        expect(page.get_by_role('list',name='审查阶段').locator('[aria-current="step"]')).to_have_text('分项审查')
        expect(page.get_by_role('progressbar',name='审查完成度')).to_have_attribute('aria-valuetext','分项审查 · 已完成 1/4 项')
        expect(agents).to_contain_text('第 1/2 项：付款与交付、验收')
        expect(page.get_by_label('审查进度').get_by_text(re.compile(r'^\d+:\d{2}$'))).to_be_visible()
        feed=page.get_by_role('log',name='审查动态')
        expect(feed).to_contain_text('已提交审查')
        running['step']=1  # an agent finishes an item; the next poll turns that into feed entries
        expect(feed).to_contain_text('法律风险审查完成第 1/2 项',timeout=8000)
        expect(feed).to_contain_text('法律风险审查 · 第 2/2 项：付款与交付、验收')
        audit_layout(page, 'legal-live')
        page.set_viewport_size({'width':1440,'height':1000})
        running['value']=False  # the next 2.5 s poll returns the completed review
        tabs=page.get_by_role('tablist',name='审查结果视图')
        tabs.wait_for(timeout=15000)
        expect(steps.locator('[aria-current="step"]')).to_have_text('4处理')
        expect(page.get_by_role('region',name='审查结果')).to_contain_text('条批注')
        # The finding is numbered on the paper, in the clause outline and in the rail, and opens selected.
        marker=page.get_by_role('button',name='第 1 条批注：付款与交货保障不匹配',exact=True)
        expect(marker).to_be_visible()
        expect(page.get_by_role('navigation',name='条款目录').locator('.lv-marker')).to_have_count(1)
        expect(page.locator('#legal-finding-f1 .lv-note-row')).to_have_attribute('aria-expanded','true')
        marker.click()
        expect(page.locator('#legal-block-p1')).to_have_class(re.compile('is-selected'))
        # How the result was reached lives under 依据.
        tabs.get_by_role('tab',name='依据').click()
        expect(page.get_by_label('交易背景与资料缺口')).to_be_visible()
        expect(page.get_by_text('1000000.05 CNY',exact=True)).to_be_visible()
        expect(page.get_by_text('2 项检索未获取到来源，相关风险无法排除。',exact=True)).to_be_visible()
        expect(page.get_by_label('本轮场景清单')).to_contain_text('销售合同')
        expect(page.get_by_label('本轮场景清单')).to_contain_text('账期、对账与扣款')
        tabs.get_by_role('tab',name=re.compile('^批注')).click()
        audit_layout(page, 'legal-results')
        page.set_viewport_size({'width':1440,'height':1000})
        page.get_by_role('button',name='采纳修改',exact=True).click()
        page.locator('.lv-decided').filter(has_text='已采纳').wait_for()
        # The adopted edit is written into the paper as a redline.
        expect(page.locator('#legal-block-p1 ins').first).to_be_visible()
        expect(page.locator('#legal-block-p1 .lv-marker.is-revised')).to_have_count(1)
        # Zero pending items: one click downloads, with no confirmation or model endpoint.
        export_count=len(export_requests)
        with page.expect_download() as direct:
            page.locator('.lv-handled').get_by_role('button',name='导出',exact=True).click()
        direct.value.save_as(OUT/'synthetic-direct-revision.txt')
        assert len(export_requests)==export_count+1 and 'confirmed' not in export_requests[-1]
        expect(page.get_by_role('dialog')).to_have_count(0)
        assert (OUT/'synthetic-direct-revision.txt').read_text()==finding['suggested_text']
        # A user may export unchanged text too; pending work prompts once and cancel does no work.
        page.locator('.lv-decided').get_by_role('button',name='撤销',exact=True).click()
        expect(page.get_by_role('button',name='采纳修改',exact=True)).to_be_visible()
        steps.get_by_role('button',name='导出',exact=True).click()
        expect(steps.locator('[aria-current="step"]')).to_have_text('5导出')
        expect(page.get_by_role('button',name='导出修订文本',exact=True)).to_be_enabled()
        expect(page.get_by_role('button',name='确认修订',exact=True)).to_have_count(0)
        export_count=len(export_requests)
        page.get_by_role('button',name='导出修订文本',exact=True).click()
        confirm=page.get_by_role('dialog',name='导出确认')
        expect(confirm).to_contain_text('还有 1 项待处理')
        assert len(export_requests)==export_count
        page.keyboard.press('Escape')
        expect(page.get_by_role('dialog')).to_have_count(0)
        assert len(export_requests)==export_count
        page.get_by_role('button',name='导出修订文本',exact=True).click()
        with page.expect_download() as revision:
            page.get_by_role('button',name='确认导出',exact=True).click()
        revision.value.save_as(OUT/'synthetic-revision.txt')
        assert len(export_requests)==export_count+1 and export_requests[-1]['confirmed']==['true']
        assert (OUT/'synthetic-revision.txt').read_text()==contract['blocks'][0]['text']
        with page.expect_download() as download:page.get_by_role('button',name='导出报告',exact=True).click()
        download.value.save_as(OUT/'synthetic-review.md')
        assert not any(path.endswith(('/draft-check','/draft-approval')) for _,path in calls)
        page.screenshot(path=str(OUT/'legal-v2-review-desktop.png'))
        # On a phone the rail and the paper share the screen through one switch.
        page.set_viewport_size({'width':390,'height':844})
        views=page.get_by_role('group',name='工作区视图')
        expect(views).to_be_visible()
        expect(page.get_by_role('region',name='合同正文')).to_be_hidden()
        views.get_by_role('button',name='修订稿',exact=True).click()
        expect(page.get_by_role('region',name='合同正文')).to_be_visible()
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
        page.screenshot(path=str(OUT/'legal-v2-mobile.png'),full_page=True)
        page.set_viewport_size({'width':1440,'height':1000})
        page.goto('http://127.0.0.1:4173/legal?contract=c1')
        steps.get_by_role('button',name='设置',exact=True).click()
        expect(page.get_by_label('合同类型',exact=True)).to_have_value('销售合同')
        expect(page.get_by_role('radio',name='销售方',exact=True)).to_be_checked()
        page.get_by_role('button',name=re.compile('^公司规范')).click()
        page.get_by_label('规范名称').fill('合成销售账期要求')
        page.get_by_label('规范适用合同').select_option('销售合同')
        page.get_by_role('checkbox',name='销售方',exact=True).check()
        page.get_by_label('规范适用合同').select_option('租赁合同')
        expect(page.get_by_role('checkbox',name='出租方',exact=True)).not_to_be_checked()
        page.get_by_label('规范适用合同').select_option('销售合同')
        page.get_by_role('checkbox',name='销售方',exact=True).check()
        page.get_by_label('规范内容').fill('仅用于合成测试：销售方核对回款起算条件，不是法律规则。')
        page.get_by_role('button',name='保存规范',exact=True).click()
        expect(page.locator('.lv-policy-type').filter(has_text='销售方')).to_be_visible()
        page.screenshot(path=str(OUT/'legal-scenario-policy.png'),full_page=True)
        page.get_by_role('button',name='合同库',exact=True).click()
        expect(page.get_by_role('button',name='选择文件',exact=True)).to_be_focused()
        page.set_viewport_size({'width':390,'height':844})
        page.locator('input[type=file]').set_input_files({'name':'new.txt','mimeType':'text/plain','buffer':'第二份合成合同'.encode()})
        page.get_by_role('button', name='同意并上传', exact=True).click()
        page.get_by_text('交易信息（选填）',exact=True).click()
        expect(page.get_by_label('合同类型',exact=True)).to_have_value('采购合同')
        expect(page.get_by_role('radiogroup',name='我方身份').get_by_role('radio',checked=True)).to_have_count(0)
        expect(page.get_by_role('region',name='合同正文')).to_be_hidden()
        expect(page.get_by_label('履行阶段')).to_have_value('未知')
        expect(page.get_by_label('交易金额',exact=True)).to_have_value('')
        assert not errors,errors
        # English interface: switched in the desk's own top bar; Chinese stays the default.
        page.set_viewport_size({'width':1440,'height':1000})
        page.goto('http://127.0.0.1:4173/legal')
        page.get_by_role('heading',name='合同库').wait_for()
        assert page.evaluate('document.documentElement.lang')=='zh-CN'
        page.get_by_role('group',name='界面语言').get_by_role('button',name='EN').click()
        expect(page.get_by_role('heading',name='Contract library')).to_be_visible()
        expect(page.get_by_role('button',name='Choose file',exact=True)).to_be_enabled()
        assert page.evaluate('document.documentElement.lang')=='en'
        for width in (320, 390, 768, 1024, 1440):
            page.set_viewport_size({'width':width,'height':960 if width>=768 else 844})
            page.wait_for_timeout(80)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2'), ('legal-en', width)
        page.screenshot(path=str(OUT/'legal-en-welcome.png'),full_page=True)
        # The finished review, in English: the desk's own labels switch; contract text and findings stay as written.
        page.goto('http://127.0.0.1:4173/legal?contract=c1')
        page.get_by_role('tablist',name='Result views').wait_for(timeout=15000)
        expect(page.get_by_role('list',name='Contract review steps').locator('[aria-current="step"]')).to_have_text('4Resolve')
        page.wait_for_timeout(600)
        page.screenshot(path=str(OUT/'legal-en-results.png'))
        page.goto('http://127.0.0.1:4173/legal')
        page.get_by_role('heading',name='Contract library').wait_for()
        page.get_by_role('group',name='Interface language').get_by_role('button',name='中文').click()
        expect(page.get_by_role('heading',name='合同库')).to_be_visible()
        assert not errors,errors
        # Both fast tiers land directly on the readable model draft, including on phones.
        saved_review=json.loads(json.dumps(review));saved_contract=json.loads(json.dumps(contract))
        for tier in ('ultra_fast','fast'):
            review.clear();review.update(json.loads(json.dumps(saved_review)))
            review.update(review_tier=tier)
            review['profile']['review_tier']=tier
            review['decisions']={'f1':{'decision':'draft','text':finding['suggested_text'],'version':1,'source':'model',
                                     'manual_edit_confirmed':False,'legal_basis_confirmed':False}}
            review['draft_check']={'id':'optional','fingerprint':'old','final_hash':'old','status':'rejected','checks':[],
                                   'whole_contract':{'status':'conflict','reason':'合成模型复核异议。'},'missing_facts':['合成未决事实。']}
            page.set_viewport_size({'width':390,'height':844})
            page.goto('http://127.0.0.1:4173/legal?contract=c1')
            paper=page.get_by_role('region',name='合同正文')
            expect(paper).to_be_visible()
            expect(page.get_by_role('group',name='修订稿显示方式').get_by_role('button',name='修订稿',exact=True)).to_have_attribute('aria-pressed','true')
            expect(page.locator('#legal-block-p1 .lv-para')).to_contain_text(finding['suggested_text'])
            expect(page.locator('#legal-block-p1 ins')).to_have_count(0)
            page.get_by_role('button',name='导出修订稿',exact=True).click()
            expect(page.get_by_role('dialog',name='导出确认')).to_contain_text('还有 1 项待处理')
            with page.expect_download() as draft_download:
                page.get_by_role('button',name='确认导出',exact=True).click()
            draft_download.value.save_as(OUT/f'{tier}-model-draft.txt')
            assert (OUT/f'{tier}-model-draft.txt').read_text()==finding['suggested_text']
            assert review['decisions']['f1']['source']=='model' and review['decisions']['f1']['decision']=='draft'
            # Direct editing is available without first undoing or claiming a legal check.
            page.get_by_role('group',name='工作区视图').get_by_role('button',name='批注',exact=True).click()
            page.get_by_role('button',name='编辑',exact=True).click()
            edited='【脱敏1】在交货验收后三十日内付款，交付日期由双方书面约定。'
            page.get_by_label('编辑本段修订',exact=True).fill(edited)
            page.get_by_role('button',name='保存修改',exact=True).click()
            expect(page.locator('.lv-decided')).to_contain_text('已采纳')
            assert review['decisions']['f1']['legal_basis_confirmed'] is False
            assert review['decisions']['f1']['manual_edit_confirmed'] is False
            page.get_by_role('group',name='工作区视图').get_by_role('button',name='修订稿',exact=True).click()
            expect(page.locator('#legal-block-p1 .lv-para')).to_contain_text(edited)
            with page.expect_download() as edited_download:
                page.get_by_role('button',name='导出修订稿',exact=True).click()
            expect(page.get_by_role('dialog')).to_have_count(0)
            edited_download.value.save_as(OUT/f'{tier}-edited-draft.txt')
            assert (OUT/f'{tier}-edited-draft.txt').read_text()==edited
            assert 'confirmed' not in export_requests[-1]
            audit_layout(page,f'legal-{tier}-draft')
        # A changed draft invalidates a previous confirmation and refreshes the preview.
        review['decisions']['f1'].update(decision='draft',source='model')
        page.goto('http://127.0.0.1:4173/legal?contract=c1')
        page.get_by_role('button',name='导出修订稿',exact=True).click()
        expect(page.get_by_role('dialog',name='导出确认')).to_contain_text('还有 1 项待处理')
        review['findings'].append({**finding,'id':'f2','block_id':None,'title':'合成未决条款','suggested_text':''})
        page.get_by_role('button',name='确认导出',exact=True).click()
        expect(page.get_by_role('dialog')).to_have_count(0)
        expect(page.get_by_role('status').filter(has_text='修订稿已更新，请查看后再次导出。')).to_be_visible()
        page.get_by_role('button',name='导出修订稿',exact=True).click()
        expect(page.get_by_role('dialog',name='导出确认')).to_contain_text('还有 2 项待处理')
        with page.expect_download():page.get_by_role('button',name='确认导出',exact=True).click()
        # A model disagreement remains an actionable note, not an export or editing veto.
        review.clear();review.update(json.loads(json.dumps(saved_review)))
        review['findings'][0].update(verification_status='rejected',revision_allowed=False,verification_note='模型对该建议存在异议。')
        review['decisions']={}
        page.set_viewport_size({'width':1440,'height':1000})
        page.goto('http://127.0.0.1:4173/legal?contract=c1')
        expect(page.get_by_text('模型对该建议存在异议。',exact=True)).to_be_visible()
        page.get_by_role('button',name='采纳修改',exact=True).click()
        expect(page.locator('.lv-decided')).to_contain_text('已采纳')
        with page.expect_download():page.get_by_role('button',name='导出修订稿',exact=True).click()
        # No findings and no edits still allow a one-click export; Word also offers an explicit TXT option.
        review['findings']=[];review['decisions']={}
        page.goto('http://127.0.0.1:4173/legal?contract=c1')
        with page.expect_download():page.locator('.lv-handled').get_by_role('button',name='导出',exact=True).click()
        expect(page.get_by_role('dialog')).to_have_count(0)
        contract.update(format='docx',name='测试采购合同.docx')
        page.goto('http://127.0.0.1:4173/legal?contract=c1')
        page.get_by_role('list',name='合同审查步骤').get_by_role('button',name='导出',exact=True).click()
        with page.expect_download() as word_download:page.get_by_role('button',name='导出 Word 修订版',exact=True).click()
        assert word_download.value.suggested_filename.endswith('.docx')
        with page.expect_download() as text_download:page.get_by_role('button',name='导出文字稿',exact=True).click()
        assert text_download.value.suggested_filename.endswith('.txt') and export_requests[-1]['format']==['txt']
        assert not any(path.endswith(('/draft-check','/draft-approval')) for _,path in calls)
        review.clear();review.update(saved_review);contract.clear();contract.update(saved_contract)
        assert not errors,errors
        # The two recipients are exercised only through explicit model actions after all export-only checks.
        model_actions['allowed']=True
        review['decisions']={'f1':{'decision':'draft','text':finding['suggested_text'],'version':1,'source':'model',
                                 'manual_edit_confirmed':False,'legal_basis_confirmed':False}}
        page.goto('http://127.0.0.1:4173/legal?contract=c1')
        for provider in ('ydata','anthropic'):
            if provider=='anthropic':
                steps.get_by_role('button',name='设置',exact=True).click()
                page.get_by_label('审查模型').select_option('claude-fixture')
                page.get_by_role('radio',name='极速审查',exact=True).check()
                expect(claude_consent).not_to_be_checked()
                page.get_by_role('group',name='界面语言').get_by_role('button',name='EN').click()
                expect(page.get_by_label('I agree to send the redacted contract, my review focus and the applicable company policies to the selected Claude model through the Anthropic official API')).not_to_be_checked()
                expect(page.get_by_text('Recipient: Anthropic official API',exact=True)).to_be_visible()
                page.get_by_role('group',name='Interface language').get_by_role('button',name='中文').click()
                # A server-side route change between choosing and starting refreshes the list and revokes consent.
                model_actions['reject_next_create']=True
                model_refreshes=sum(path=='/legal/models' and method=='GET' for method,path in calls)
                claude_consent.check();page.get_by_role('button',name='重新审查',exact=True).click()
                expect(page.get_by_role('alert').filter(has_text='处理方已变化')).to_be_visible()
                expect(claude_consent).not_to_be_checked()
                expect(page.get_by_role('button',name='重新审查',exact=True)).to_be_disabled()
                expect(page.get_by_role('button',name='刷新模型列表',exact=True)).to_be_enabled()
                assert sum(path=='/legal/models' and method=='GET' for method,path in calls)>model_refreshes
                claude_consent.check();page.get_by_role('button',name='重新审查',exact=True).click()
                expect(page.get_by_role('tablist',name='审查结果视图')).to_be_visible()
                assert review_requests[-1]['model_id']=='claude-fixture'
                assert review_requests[-1]['external_processing_provider']=='anthropic'
                assert review['profile']['model']['provider']=='anthropic'
                expect(page.locator('#legal-block-p1 .lv-para')).to_contain_text(finding['suggested_text'])
                page.screenshot(path=str(OUT/'legal-anthropic-draft.png'),full_page=True)
            recipient='Anthropic 官方 API' if provider=='anthropic' else 'YData 网关'
            page.get_by_role('tablist',name='审查结果视图').get_by_role('tab',name='问答',exact=True).click()
            question_consent=page.get_by_role('checkbox',name=re.compile('^同意将问题及脱敏材料.*'+recipient))
            expect(question_consent).not_to_be_checked()
            page.get_by_label('追问本轮审查',exact=True).fill('请说明付款节点。')
            expect(page.get_by_role('button',name='发送追问',exact=True)).to_be_disabled()
            question_consent.check();page.get_by_role('button',name='发送追问',exact=True).click()
            expect(page.get_by_text('合成回答：请核对合同付款节点。',exact=True)).to_be_visible()
            assert model_requests[-1]=={'action':'question','provider':provider}
            steps.get_by_role('button',name='导出',exact=True).click()
            page.get_by_text('可选：复核当前修订稿',exact=True).click()
            check_consent=page.get_by_role('checkbox',name=re.compile('^同意将当前修改.*'+recipient))
            expect(check_consent).not_to_be_checked()
            expect(page.get_by_role('button',name='开始复核',exact=True)).to_be_disabled()
            check_consent.check();page.get_by_role('button',name='开始复核',exact=True).click()
            expect(page.get_by_text('合成可选复核完成。',exact=True)).to_be_visible()
            assert model_requests[-1]=={'action':'check','provider':provider}
            # Official Claude's auto-draft still exports after one user confirmation, with no extra model call.
            model_count=len(model_requests)
            page.get_by_role('button',name='导出修订文本',exact=True).click()
            expect(page.get_by_role('dialog',name='导出确认')).to_contain_text('还有 1 项待处理')
            with page.expect_download() as routed_download:page.get_by_role('button',name='确认导出',exact=True).click()
            routed_download.value.save_as(OUT/f'{provider}-revision.txt')
            assert (OUT/f'{provider}-revision.txt').read_text()==finding['suggested_text']
            assert len(model_requests)==model_count
        assert model_requests==[{'action':'question','provider':'ydata'},{'action':'check','provider':'ydata'},
                               {'action':'question','provider':'anthropic'},{'action':'check','provider':'anthropic'}]
        assert review_requests[0]['model_id']=='glm-5.2' and review_requests[0]['external_processing_provider']=='ydata'
        assert not any(path.endswith('/draft-approval') for _,path in calls)
        assert not errors,errors
        # Reduced motion: the desk renders fully with no animation left running.
        still=browser.new_context(viewport={'width':1440,'height':900},reduced_motion='reduce')
        still.add_init_script("localStorage.setItem('token','synthetic');localStorage.setItem('user',JSON.stringify({id:'u1',role:'user',plan:'max'}));")
        quiet=still.new_page();quiet.route('http://127.0.0.1:8000/**',route_api)
        quiet.goto('http://127.0.0.1:4173/legal');quiet.get_by_role('heading',name='合同库').wait_for()
        assert quiet.evaluate('document.getAnimations().length')==0
        still.close()
        assert not AXE_VIOLATIONS, AXE_VIOLATIONS
        browser.close()
    print('PASS: actual built UI with synthetic APIs: Max gate, library, redaction compare, 20 scenarios, party picking on paper, live review, numbered findings, user-controlled export, fast model drafts, direct edits, stale confirmation, disputed findings, Word/TXT choices, policies, mobile, English switch, Anthropic official Claude and YData routing, recipient-bound consent, provider refresh, explicit follow-up and optional check.')
except Exception:
    try:
        page.screenshot(path=str(OUT/'failure.png'), full_page=True)
        (OUT/'failure.html').write_text(page.content(), encoding='utf-8')
    except Exception:
        pass
    raise
finally:server.shutdown()
