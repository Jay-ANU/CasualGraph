"""Built-frontend regression with synthetic data, Max access and mocked providers."""
import functools
import http.server
import json
from pathlib import Path
import threading
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'ui-artifacts'
OUT.mkdir(exist_ok=True)


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if not (Path(self.directory) / self.path.lstrip('/').split('?')[0]).is_file():
            self.path = '/index.html'
        super().do_GET()

    def log_message(self, *args):
        pass


server = http.server.ThreadingHTTPServer(('127.0.0.1', 4173), functools.partial(Handler, directory=str(ROOT / 'frontend/dist')))
threading.Thread(target=server.serve_forever, daemon=True).start()
contract = {'id':'c1','name':'测试采购合同.txt','status':'redaction_pending','revision':1,'format':'txt',
    'matter_id':'m1','org_id':'o1','warnings':[], 'replacement_count':1,'reviews':[],
    'blocks':[{'id':'p1','text':'【脱敏1】应在签约后支付全部价款，交货时间另行通知。','page':None}]}
finding = {'id':'f1','rule_id':'performance','block_id':'p1','original_quote':contract['blocks'][0]['text'],
    'title':'付款与交货保障不匹配','kind':'commercial','severity':'high','impact':'我方预先承担全部资金风险。',
    'reason':'付款条件未与确定的交货期限挂钩。','suggested_text':'【脱敏1】在交货验收后支付价款。',
    'evidence_status':'not_applicable','missing_facts':[],'citations':[],'policy_ids':[]}
review = {'id':'r1','status':'completed','stage':'审查完成，等待人工逐条复核','resumable':False,'error':None,
    'findings':[finding],'coverage':[{'rule_id':'performance','title':'交付、验收与付款','status':'reviewed','note':'合成测试样例'}],
    'profile':{'model':{'id':'glm-5.2','provider':'ydata'}},
    'sources':[],'decisions':{},'policies':[],'notice':'测试数据，不是法律结论。'}
policies = []
calls = []
entitlement = {'allowed': True, 'plan': 'max', 'required_plan': 'max'}
access_error = False
model_ids = [('gpt-test','GPT'), ('claude-test','Claude'), ('deepseek-test','DeepSeek'), ('kimi-test','Kimi'), ('glm-5.2','GLM')]


def route_api(route):
    req = route.request
    path = urlparse(req.url).path
    method = req.method
    calls.append((method,path))
    headers = {'Access-Control-Allow-Origin':'*','Access-Control-Allow-Methods':'GET,POST,PUT,PATCH,DELETE,OPTIONS',
               'Access-Control-Allow-Headers':'authorization,content-type'}
    if method == 'OPTIONS':
        route.fulfill(status=204, headers=headers)
        return
    status, data = 200, {}
    if path == '/auth/me':
        # A stale or forged client-visible Max plan cannot override /legal/access.
        data={'user':{'id':'u1','username':'测试法务','email':'test@example.com','role':'user','plan':'max'}}
    elif path == '/legal/access':
        if access_error:
            status,data=503,{'detail':'Synthetic unavailable access service'}
        else:
            data=entitlement
    elif path == '/legal/models':
        data={'models':[{'id':mid,'family':family} for mid,family in model_ids],
              'families':['GPT','Claude','DeepSeek','Kimi','GLM'],'default_model':'glm-5.2','catalog_source':'gateway','notice':'mock'}
    elif path == '/legal/workspace': data={'matter_id':'m1','org_id':'o1'}
    elif path == '/matters': data={'matters':[{'id':'m1','org_id':'o1','name':'采购审查'}]}
    elif path == '/legal/capabilities': data={'product':'contract-review','model_configured':True,'encryption_configured':True,'law_search':{'provider':'test-only','notice':'mock'}}
    elif path == '/legal/contracts' and method == 'GET': data={'contracts':[contract] if any(m=='POST' and p==path for m,p in calls) else []}
    elif path == '/legal/contracts' and method == 'POST': data=contract
    elif path == '/legal/contracts/c1': data=contract
    elif path.endswith('/redaction'):
        request = req.post_data_json
        if request.get('confirmed'): contract['status']='ready'
        data={'blocks':contract['blocks'],'confirmed':request.get('confirmed'), 'replacement_count':1}
    elif path == '/legal/contracts/c1/reviews':
        assert req.post_data_json['model_id'] == 'glm-5.2'
        assert req.post_data_json['external_processing_provider'] == 'ydata'
        assert req.post_data_json['external_processing_confirmed'] is True
        assert contract['status']=='ready'
        data=review
    elif path == '/legal/reviews/r1': data=review
    elif path == '/legal/reviews/r1/findings/f1':
        d=req.post_data_json
        data={**d,'version':len(review['decisions'])+1}; review['decisions']['f1']=data
    elif path == '/legal/reviews/r1/export':
        route.fulfill(status=200, headers=headers, content_type='application/json', body=json.dumps(review,ensure_ascii=False))
        return
    elif path == '/legal/policies' and method == 'GET': data={'policies':policies}
    elif path == '/legal/policies' and method == 'POST':
        data={**req.post_data_json,'id':'policy1','version':1}; policies.append(data)
    else: status,data=404,{'detail':'Unhandled mock route: '+path}
    route.fulfill(status=status, headers=headers, content_type='application/json', body=json.dumps(data,ensure_ascii=False))


try:
    with sync_playwright() as p:
        browser=p.chromium.launch()
        errors=[]
        def new_page():
            page=browser.new_page(viewport={'width':1440,'height':1100})
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.on('dialog',lambda dialog:dialog.accept())
            page.route('http://127.0.0.1:8000/**',route_api)
            page.add_init_script("localStorage.setItem('token','synthetic-test-token');localStorage.setItem('user',JSON.stringify({id:'u1',username:'测试法务',role:'user',plan:'max'}));")
            return page

        for plan in ('free','pro'):
            entitlement.update(allowed=False,plan=plan)
            before=len(calls)
            page=new_page()
            page.goto('http://127.0.0.1:4173/legal')
            expect(page.get_by_role('heading',name='法务 Agent · Max 专属')).to_be_visible()
            expect(page.get_by_role('link',name='返回研究工作台')).to_have_attribute('href','/agent')
            expect(page.get_by_role('button',name='＋ 上传合同')).to_have_count(0)
            assert all(path == '/legal/access' for method,path in calls[before:] if path.startswith('/legal/'))
            page.screenshot(path=str(OUT/f'legal-{plan}-locked.png'),full_page=True)
            page.close()
        print('PASS: Free and Pro never mount the workbench or fetch private legal APIs despite a cached Max plan.')

        access_error=True
        page=new_page()
        page.goto('http://127.0.0.1:4173/legal')
        expect(page.get_by_role('heading',name='法务服务暂不可用')).to_be_visible()
        expect(page.get_by_role('button',name='＋ 上传合同')).to_have_count(0)
        page.close()
        access_error=False
        entitlement.update(allowed=True,plan='max')
        page=new_page()
        page.goto('http://127.0.0.1:4173/legal')
        page.get_by_role('button',name='选择一份合同开始').wait_for()
        expect(page.get_by_role('button',name='＋ 上传合同')).to_be_enabled()
        picker=page.get_by_label('审查模型',exact=True)
        expect(picker).to_have_value('glm-5.2')
        for mid,family in model_ids:
            expect(picker.locator(f'optgroup[label="{family}"] option')).to_have_attribute('value',mid)
            picker.select_option(mid)
        page.locator('input[type=file]').set_input_files({'name':'测试采购合同.txt','mimeType':'text/plain','buffer':'测试采购合同'.encode()})
        page.get_by_role('button',name='已检查，确认脱敏').click()
        page.get_by_label('我方角色').select_option('采购方')
        consent=page.get_by_label('允许将脱敏正文及适用公司规范经 YData 网关发送给所选模型。')
        consent.check()
        picker.select_option('claude-test')
        expect(consent).not_to_be_checked()
        expect(page.get_by_role('button',name='开始审查',exact=True)).to_be_disabled()
        picker.select_option('glm-5.2')
        consent.check()
        page.get_by_role('button',name='开始审查',exact=True).click()
        page.get_by_role('heading',name='付款与交货保障不匹配').wait_for()
        expect(page.get_by_role('status')).to_contain_text('glm-5.2')
        page.get_by_role('button',name='接受修改',exact=True).click()
        page.get_by_text('已接受',exact=True).wait_for()
        with page.expect_download() as pending:
            page.get_by_role('button',name='导出审查报告',exact=True).click()
        pending.value.save_as(OUT/'synthetic-review.json')
        page.screenshot(path=str(OUT/'legal-review-desktop.png'),full_page=True)
        page.get_by_role('navigation',name='法务工作台').get_by_role('button',name='公司规范',exact=False).click()
        page.get_by_label('规范标题').fill('采购付款要求')
        page.get_by_label('审查要求').fill('我方采购时，付款应与交付和验收安排挂钩。')
        page.get_by_role('button',name='保存规范').click()
        page.get_by_role('heading',name='采购付款要求',exact=True).wait_for()
        page.get_by_role('button',name='合同审查',exact=True).click()
        page.set_viewport_size({'width':390,'height':844})
        page.screenshot(path=str(OUT/'legal-review-mobile.png'),full_page=True)
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 2'), 'mobile horizontal overflow'
        assert not errors, errors
        browser.close()
    print('PASS: all five model families, provider consent reset, selected model request/display, upload, review, decisions, report export, policies and mobile (mock APIs).')
finally:
    server.shutdown()
