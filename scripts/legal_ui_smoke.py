"""Actual React build regression with synthetic APIs, never production credentials."""
import functools
import http.server
import json
from pathlib import Path
import threading
from urllib.parse import urlparse
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
policies=[]; calls=[]; allowed={'value':True,'plan':'max','unavailable':False}
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
    elif path=='/legal/capabilities':data={'model_configured':True,'encryption_configured':True,'review_engine_version':2,'followup_questions':True,'collaboration_version':1,'audit_foundation_version':1,'draft_release_version':1,'scenario_catalog':SCENARIOS,'scenario_catalog_version':1,'upload_disclosure':{'version':'original-upload-v1','notice':'合成上传说明：原件先到后端再脱敏。','storage_region':'合成环境'},'law_search':{'provider':'synthetic','notice':'test'}}
    elif path=='/legal/models':data={'models':[{'id':'gpt-fixture','family':'GPT'},{'id':'claude-fixture','family':'Claude'},{'id':'deepseek-fixture','family':'DeepSeek'},{'id':'kimi-fixture','family':'Kimi'},{'id':'glm-5.2','family':'GLM'}],'families':['GPT','Claude','DeepSeek','Kimi','GLM'],'default_model':'glm-5.2','notice':'synthetic'}
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
        assert payload['model_id']=='glm-5.2' and payload['external_processing_provider']=='ydata'
        assert payload['external_processing_confirmed'] is True and contract['status']=='ready'
        assert payload['review_mode']=='multi_agent'
        assert payload['our_party']=={'block_id':'p1','quote':'【脱敏1】'}
        assert payload['contract_type']=='销售合同' and payload['our_role']=='销售方'
        assert payload['scenario_revision']==SCENARIOS['revision']
        assert payload['our_role']=='销售方' and payload['instructions']=='重点关注付款安排'
        assert payload['transaction_context']=={'performance_stage':'谈判中','attachments_status':'未知','business_priority':'付款与回款','deal_value':'1000000.05','currency':'CNY'}
        review['profile'].update(transaction_context=payload['transaction_context'], contract_type=payload['contract_type'], our_role=payload['our_role'], our_party=payload['our_party'], scenario=descriptor(get_scenario('销售合同'),'销售方'))
        review['transaction_brief']={'version':1,'context':payload['transaction_context'],'context_source':'user_statement_not_independently_verified',
            'material_references':[], 'gaps':[{'code':'date_unknown','message':'交易日期未提供，法律时间适用仍需核验。','source':'not_provided'}],
            'notice':'合成背景，不是已核实交易事实。'}
        review['evidence_health']={'queried_topics':6,'topics_with_sources':4,'failed_or_empty_topics':2,'source_count':0,'non_authoritative_sources':0,'version_pending':0,'status':'gaps','notice':'合成检索状态。'}
        contract['reviews']=[{'id':'r1','status':'completed'}]; data=review
    elif path=='/legal/reviews/r1':data=review
    elif path=='/legal/reviews/r1/findings/f1':
        data={**req.post_data_json,'version':1};review['decisions']['f1']=data
    elif path=='/legal/reviews/r1/draft-check':
        assert req.post_data_json['external_processing_confirmed'] is True
        review['draft_check']={'id':'dc1','fingerprint':'a'*64,'final_hash':'b'*64,'status':'verified','checks':[{'finding_id':'f1','status':'supported','reason':'合成对比通过。'}],'whole_contract':{'status':'consistent','reason':'合成全文对比。'},'missing_facts':[]}
        data=review
    elif path=='/legal/reviews/r1/draft-approval':
        assert req.post_data_json=={'fingerprint':'a'*64,'confirmed':True}
        review['draft_approval']={'fingerprint':'a'*64,'final_hash':'b'*64,'user_id':'u1'}
        data=review
    elif path=='/legal/reviews/r1/export':data=review
    elif path=='/legal/reviews/r1/questions':data={'messages':[]}
    elif path=='/legal/policies' and method=='GET':data={'policies':policies}
    elif path=='/legal/policies' and method=='POST':
        assert req.post_data_json['contract_type']=='销售合同' and req.post_data_json['our_roles']==['销售方']
        data={**req.post_data_json,'id':'policy1','version':1}; policies.append(data)
    else:status,data=404,{'detail':'Unhandled synthetic route: '+path}
    route.fulfill(status=status,headers=headers,content_type='application/json',body=json.dumps(data,ensure_ascii=False))
try:
    with sync_playwright() as p:
        browser=p.chromium.launch()
        for plan in ('free','pro','unavailable'):
            allowed.update(value=False,plan=plan,unavailable=plan=='unavailable')
            context=browser.new_context()
            context.add_init_script("localStorage.setItem('token','synthetic');localStorage.setItem('user',JSON.stringify({id:'u1',role:'user',plan:'max'}));")
            page=context.new_page();page.route('http://127.0.0.1:8000/**',route_api)
            start=len(calls);page.goto('http://127.0.0.1:4173/legal');page.wait_for_timeout(800)
            expect(page.get_by_role('button',name='选择一份合同开始')).to_have_count(0)
            assert not any(path in ('/legal/workspace','/legal/models','/legal/contracts') for _,path in calls[start:])
            context.close()
        allowed.update(value=True,plan='max',unavailable=False)
        context=browser.new_context(viewport={'width':1440,'height':1000})
        context.add_init_script("localStorage.setItem('token','synthetic');localStorage.setItem('user',JSON.stringify({id:'u1',role:'user',plan:'max'}));")
        page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('dialog',lambda d:d.accept());page.route('http://127.0.0.1:8000/**',route_api)
        page.goto('http://127.0.0.1:4173/legal')
        page.get_by_role('heading',name='今天需要审查哪份合同？').wait_for()
        expect(page.get_by_label('审查模型')).to_have_value('glm-5.2');assert page.locator('optgroup').count()==5
        page.screenshot(path=str(OUT/'legal-v2-welcome-desktop.png'),full_page=True)
        page.get_by_role('button',name='销售合同',exact=True).click()
        page.get_by_label('审查关注点').fill('重点关注付款安排')
        page.locator('input[type=file]').set_input_files({'name':'test.txt','mimeType':'text/plain','buffer':'合成合同'.encode()})
        page.get_by_role('button',name='对照真实原文（仅有编辑权限可见）').click()
        expect(page.get_by_text('原件对照合成姓名：张三',exact=False)).to_be_visible()
        page.get_by_role('button',name='关闭真实原文对照').click()
        page.get_by_role('button',name='已检查，确认脱敏',exact=True).click()
        expect(page.get_by_label('我方角色')).to_have_value('')
        # All configured routes and role sets render from the backend catalogue.
        expect(page.get_by_label('合同类型',exact=True)).to_have_value('销售合同')
        for scene in SCENARIOS['scenarios']:
            page.get_by_label('合同类型',exact=True).select_option(scene['label'])
            expect(page.get_by_label('我方角色')).to_have_value('')
            expect(page.get_by_label('我方角色').locator('option')).to_have_count(len(scene['roles'])+1)
            page.get_by_label('我方角色').select_option(scene['roles'][0]['value'])
        page.get_by_label('合同类型',exact=True).select_option('销售合同')
        expect(page.get_by_label('我方角色')).to_have_value('')
        page.get_by_label('我方角色').select_option('销售方')
        page.get_by_label('我方主体所在段落').select_option('p1')
        page.get_by_label('我方主体原文').fill('【脱敏1】')
        page.get_by_text('交易背景与法律适用',exact=True).click()
        page.get_by_label('履行阶段').select_option('谈判中')
        page.get_by_label('关键附件状态').select_option('未知')
        page.get_by_label('业务优先级').select_option('付款与回款')
        page.get_by_label('交易金额',exact=True).fill('-3')
        expect(page.get_by_text('交易金额必须是非负数字，最多两位小数，不使用单位或科学计数法。',exact=True)).to_be_visible()
        page.get_by_label('交易金额',exact=True).fill('1000000.05')
        consent=page.get_by_label('允许将脱敏正文、补充要求及适用公司规范经 YData 网关发送给所选模型。')
        consent.check();page.get_by_label('合同类型',exact=True).select_option('保密协议');expect(consent).not_to_be_checked()
        expect(page.get_by_label('我方角色')).to_have_value('')
        consent.check()
        expect(page.get_by_role('button',name='开始审查',exact=True)).to_be_disabled()
        page.get_by_label('合同类型',exact=True).select_option('销售合同');page.get_by_label('我方角色').select_option('销售方')
        consent.check();page.get_by_label('审查方式').select_option('standard');expect(consent).not_to_be_checked()
        page.get_by_label('审查方式').select_option('multi_agent')
        consent.check();page.get_by_label('审查模型').select_option('claude-fixture');expect(consent).not_to_be_checked()
        page.get_by_label('审查模型').select_option('glm-5.2');consent.check()
        page.screenshot(path=str(OUT/'legal-scenario-setup.png'),full_page=True)
        page.get_by_role('button',name='开始审查',exact=True).click()
        page.get_by_role('heading',name='有 1 项值得进一步处理').wait_for()
        expect(page.get_by_label('协作进度')).to_be_visible()
        expect(page.get_by_label('交易背景与资料缺口')).to_be_visible()
        expect(page.get_by_text('1000000.05 CNY',exact=True)).to_be_visible()
        expect(page.get_by_text('有 2 项检索未取得来源，不能据此排除法律风险。',exact=True)).to_be_visible()
        expect(page.get_by_label('本轮场景清单')).to_contain_text('销售合同')
        expect(page.get_by_label('本轮场景清单')).to_contain_text('账期、对账与扣款')
        page.get_by_role('button',name='接受修改',exact=True).click()
        page.locator('.lv-decision').filter(has_text='已纳入修订').wait_for()
        expect(page.get_by_role('button',name='导出文字修改稿',exact=True)).to_be_disabled()
        page.get_by_label('允许将当前脱敏修订组合交给原审查模型复核。').check()
        page.get_by_role('button',name='核验所选修订',exact=True).click()
        page.get_by_label('我已核对当前完整修改组合、法律适用及剩余风险，确认生成这份修订稿。').check()
        page.get_by_role('button',name='确认当前修订组合',exact=True).click()
        expect(page.get_by_role('button',name='导出文字修改稿',exact=True)).to_be_enabled()
        with page.expect_download() as download:page.get_by_role('button',name='导出审查报告',exact=True).click()
        download.value.save_as(OUT/'synthetic-review.md')
        page.screenshot(path=str(OUT/'legal-v2-review-desktop.png'),full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        page.get_by_role('button',name='关闭原文面板').click()
        # Wait for the responsive sidebar transition instead of capturing a
        # half-open drawer during desktop-to-mobile resizing.
        page.wait_for_function("document.querySelector('.lv-sidebar').getBoundingClientRect().right <= 1")
        page.get_by_role('button',name='打开导航',exact=True).click()
        expect(page.locator('.lv-backdrop')).to_be_visible()
        page.wait_for_function("Math.abs(document.querySelector('.lv-sidebar').getBoundingClientRect().left) <= 1")
        expect(page.get_by_role('button',name='关闭导航',exact=True)).to_be_focused()
        page.keyboard.press('Escape')
        expect(page.locator('.lv-backdrop')).to_have_count(0)
        page.wait_for_function("document.querySelector('.lv-sidebar').getBoundingClientRect().right <= 1")
        expect(page.get_by_role('button',name='打开导航',exact=True)).to_be_focused()
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
        page.locator('.lv-conversation').evaluate('(el) => { el.scrollTop = 0; }')
        page.screenshot(path=str(OUT/'legal-v2-mobile.png'),full_page=True)
        page.set_viewport_size({'width':1440,'height':1000})
        page.wait_for_function("document.querySelector('.lv-sidebar').getBoundingClientRect().left >= 0")
        page.goto('http://127.0.0.1:4173/legal?contract=c1')
        page.get_by_role('button',name='本轮审查设置',exact=False).click()
        expect(page.get_by_label('合同类型',exact=True)).to_have_value('销售合同')
        expect(page.get_by_label('我方角色')).to_have_value('销售方')
        page.locator('.lv-navigation button').filter(has_text='公司规范').click()
        page.get_by_label('规范标题').fill('合成销售账期要求')
        page.get_by_label('规范适用合同').select_option('销售合同')
        page.get_by_role('checkbox',name='销售方',exact=True).check()
        page.get_by_label('规范适用合同').select_option('租赁合同')
        expect(page.get_by_role('checkbox',name='出租方',exact=True)).not_to_be_checked()
        page.get_by_label('规范适用合同').select_option('销售合同')
        page.get_by_role('checkbox',name='销售方',exact=True).check()
        page.get_by_label('审查要求').fill('仅用于合成测试：销售方核对回款起算条件，不是法律规则。')
        page.get_by_role('button',name='保存规范',exact=True).click()
        expect(page.locator('.lv-policy-type').filter(has_text='销售方')).to_be_visible()
        page.screenshot(path=str(OUT/'legal-scenario-policy.png'),full_page=True)
        page.get_by_role('button',name='新建审查').click()
        page.locator('input[type=file]').set_input_files({'name':'new.txt','mimeType':'text/plain','buffer':'第二份合成合同'.encode()})
        page.get_by_text('交易背景与法律适用',exact=True).click()
        expect(page.get_by_label('合同类型',exact=True)).to_have_value('采购合同')
        expect(page.get_by_label('我方角色')).to_have_value('')
        expect(page.get_by_label('履行阶段')).to_have_value('未知')
        expect(page.get_by_label('交易金额',exact=True)).to_have_value('')
        assert not errors,errors
        browser.close()
    print('PASS: actual built UI with synthetic APIs: Max gate, 20 scenarios, role scopes, frozen settings, policies, decisions, report, mobile.')
finally:server.shutdown()
