"""Actual React build regression with synthetic APIs, never production credentials."""
import traceback
from contextlib import contextmanager
import functools
import http.server
import json
import os
from pathlib import Path
import re
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
        contract['reviews']=[{'id':'r1','status':'completed'}]
        data={**review,'status':'running','stage':'正在审查付款与交付条款','findings':[],'progress':{'phase':'review','completed':1,'total':6}}
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
    elif path=='/legal/reviews/r1/export':
        if urlparse(req.url).query == 'format=txt':
            route.fulfill(status=200, headers=headers, content_type='text/plain; charset=utf-8', body='合成修订稿，不是法律结论。'); return
        data=review
    elif path=='/legal/reviews/r1/questions':data={'messages':[]}
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
def audit_layout(page, label):
    """Real DOM reflow and optional axe checks; synthetic data only."""
    widths = (320, 390, 768, 1024, 1440)
    for width in widths:
        page.set_viewport_size({'width': width, 'height': 960 if width >= 768 else 844})
        page.wait_for_timeout(80)
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
            context.close()
        allowed.update(value=True,plan='max',unavailable=False)
        context=browser.new_context(viewport={'width':1440,'height':1000})
        context.add_init_script("localStorage.setItem('token','synthetic');localStorage.setItem('user',JSON.stringify({id:'u1',role:'user',plan:'max'}));")
        page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('dialog',lambda d:d.accept());page.route('http://127.0.0.1:8000/**',route_api)
        page.goto('http://127.0.0.1:4173/legal')
        page.get_by_role('heading',name='合同风险审查').wait_for()
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
        compare=page.get_by_role('button',name='对照原件',exact=True)
        compare.click();expect(compare).to_have_attribute('aria-pressed','true')
        expect(page.get_by_text('原件对照合成姓名：张三',exact=False)).to_be_visible()
        compare.click();expect(compare).to_have_attribute('aria-pressed','false')
        expect(page.get_by_text('原件对照合成姓名：张三',exact=False)).to_have_count(0)
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
        expect(page.get_by_role('group',name='从原文选择主体片段').get_by_role('button',pressed=True)).to_have_count(0)
        # The quote names the button; the line it came from describes it.
        expect(page.get_by_role('group', name='从原文选择主体片段').get_by_role('button', name='【脱敏1】', exact=True)).to_have_accessible_description(re.compile('应在签约后支付'))
        page.get_by_role('group', name='从原文选择主体片段').get_by_role('button', name='【脱敏1】', exact=True).click()
        expect(page.get_by_role('group', name='从原文选择主体片段').get_by_role('button', name='【脱敏1】', exact=True)).to_have_attribute('aria-pressed','true')
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
        consent.check();page.get_by_role('radio',name='标准审查',exact=True).check();expect(consent).not_to_be_checked()
        page.get_by_role('radio',name='深度审查',exact=True).check()
        consent.check();page.get_by_label('审查模型').select_option('claude-fixture');expect(consent).not_to_be_checked()
        page.get_by_label('审查模型').select_option('glm-5.2');consent.check()
        page.screenshot(path=str(OUT/'legal-scenario-setup.png'),full_page=True)
        page.get_by_role('button',name='开始审查',exact=True).click()
        # While the review runs, progress and the collaborating review dimensions are shown.
        expect(page.get_by_role('heading',name='审查中')).to_be_visible()
        expect(page.get_by_label('协作进度')).to_be_visible()
        page.get_by_role('heading',name='审查结果').wait_for(timeout=15000)
        expect(page.get_by_label('风险分布')).to_contain_text('审查意见')
        expect(page.get_by_label('交易背景与资料缺口')).to_be_visible()
        expect(page.get_by_text('1000000.05 CNY',exact=True)).to_be_visible()
        expect(page.get_by_text('2 项检索未获取到来源，相关风险无法排除。',exact=True)).to_be_visible()
        expect(page.get_by_label('本轮场景清单')).to_contain_text('销售合同')
        expect(page.get_by_label('本轮场景清单')).to_contain_text('账期、对账与扣款')
        page.get_by_label('查找审查意见').fill('不存在的条件')
        expect(page.get_by_text('没有符合条件的意见', exact=True)).to_be_visible()
        page.get_by_role('button', name='清除筛选', exact=True).click()
        page.locator('.lv-work').evaluate('(el) => { el.scrollTop = 0; }')
        audit_layout(page, 'legal-results')
        page.set_viewport_size({'width':1440,'height':1000})
        page.get_by_role('button',name='采纳修改',exact=True).click()
        page.locator('.lv-decision').filter(has_text='已采纳').wait_for()
        expect(page.get_by_role('button',name='导出修订文本',exact=True)).to_be_disabled()
        page.get_by_label('同意将已采纳修改（脱敏）提交原审查模型核验').check()
        page.get_by_role('button',name='开始核验',exact=True).click()
        page.get_by_label('已核对全部修改及剩余风险，确认生成修订版').check()
        page.get_by_role('button',name='确认修订',exact=True).click()
        expect(page.get_by_role('button',name='导出修订文本',exact=True)).to_be_enabled()
        export_count = sum(path == '/legal/reviews/r1/export' for _, path in calls)
        page.get_by_role('button',name='导出修订文本',exact=True).click()
        expect(page.get_by_role('dialog', name='导出确认')).to_be_visible()
        assert sum(path == '/legal/reviews/r1/export' for _, path in calls) == export_count
        page.keyboard.press('Escape')
        expect(page.get_by_role('dialog')).to_have_count(0)
        page.get_by_role('button',name='导出修订文本',exact=True).click()
        with page.expect_download() as revision:
            page.get_by_role('button',name='确认导出',exact=True).click()
        revision.value.save_as(OUT/'synthetic-revision.txt')
        with page.expect_download() as download:page.get_by_role('button',name='导出报告',exact=True).click()
        download.value.save_as(OUT/'synthetic-review.md')
        page.locator('.lv-work').evaluate('(el) => { el.scrollTop = 0; }')
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
        page.locator('.lv-work').evaluate('(el) => { el.scrollTop = 0; }')
        page.screenshot(path=str(OUT/'legal-v2-mobile.png'),full_page=True)
        page.set_viewport_size({'width':1440,'height':1000})
        page.wait_for_function("document.querySelector('.lv-sidebar').getBoundingClientRect().left >= 0")
        page.goto('http://127.0.0.1:4173/legal?contract=c1')
        page.get_by_role('button',name='审查设置',exact=False).click()
        expect(page.get_by_label('合同类型',exact=True)).to_have_value('销售合同')
        expect(page.get_by_role('radio',name='销售方',exact=True)).to_be_checked()
        page.locator('.lv-navigation button').filter(has_text='公司规范').click()
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
        page.get_by_role('button',name='新建审查').click()
        expect(page.get_by_role('button',name='选择文件',exact=True)).to_be_focused()
        page.set_viewport_size({'width':390,'height':844})
        page.locator('input[type=file]').set_input_files({'name':'new.txt','mimeType':'text/plain','buffer':'第二份合成合同'.encode()})
        page.get_by_role('button', name='同意并上传', exact=True).click()
        page.get_by_text('交易信息（选填）',exact=True).click()
        expect(page.get_by_label('合同类型',exact=True)).to_have_value('采购合同')
        expect(page.get_by_role('radiogroup',name='我方身份').get_by_role('radio',checked=True)).to_have_count(0)
        expect(page.get_by_label('脱敏合同正文')).to_have_count(0)
        expect(page.get_by_label('履行阶段')).to_have_value('未知')
        expect(page.get_by_label('交易金额',exact=True)).to_have_value('')
        assert not errors,errors
        assert not AXE_VIOLATIONS, AXE_VIOLATIONS
        browser.close()
    print('PASS: actual built UI with synthetic APIs: Max gate, 20 scenarios, role scopes, frozen settings, policies, decisions, report, mobile.')
except Exception:
    try:
        page.screenshot(path=str(OUT/'failure.png'), full_page=True)
        (OUT/'failure.html').write_text(page.content(), encoding='utf-8')
    except Exception:
        pass
    raise
finally:server.shutdown()
