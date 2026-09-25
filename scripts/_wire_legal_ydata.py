"""One-time, branch-scoped wiring of the reviewed YData/Max change; removed before merge."""
from pathlib import Path
import re


def patch(path, old, new):
    p = Path(path)
    text = p.read_text()
    assert text.count(old) == 1, (path, old[:100], text.count(old))
    p.write_text(text.replace(old, new))

patch('services/db.py', '        await init_user_memory_db(db)',
      '        from services.max_membership import init_max_memberships\n        await init_max_memberships(db)\n        await init_user_memory_db(db)')
patch('services/rate_limit.py', '    if await _is_rag_pro_user(db, current_user):',
      '    from services.max_membership import has_max_membership\n    if await has_max_membership(db, str((current_user or {}).get("id") or "")):\n        return {"plan": "max", "plan_label": "Max", "points_limit": None, "unlimited": True}\n    if await _is_rag_pro_user(db, current_user):')
patch('app.py', 'from api.routers.contract_review import router as contract_review_router',
      'from api.routers.contract_review import public_router as contract_public_router\nfrom api.routers.max_memberships import router as max_memberships_router\nfrom api.routers.contract_review import router as contract_review_router')
patch('app.py', 'for router in (*ROUTERS, *_optional_routers()):',
      'for router in (*ROUTERS, contract_public_router, max_memberships_router, *_optional_routers()):')
p = 'api/routers/contract_review.py'
patch(p, 'from api.deps import get_current_user', 'from api.deps import get_current_user\nfrom services.db import get_db\nfrom legal.access import require_legal_max, access_status\nfrom legal import ydata')
patch(p, "router = APIRouter(prefix='/legal', tags=['contract-review'])",
      "router = APIRouter(prefix='/legal', tags=['contract-review'], dependencies=[Depends(require_legal_max)])\npublic_router = APIRouter(prefix='/legal', tags=['contract-review'])")
patch(p, "class ReviewRequest(BaseModel):", "class ReviewRequest(BaseModel):\n    model_id: str = Field(min_length=1, max_length=160, pattern=r'^[A-Za-z0-9][A-Za-z0-9._/-]*$')\n    external_processing_provider: Literal['ydata']")
patch(p, "@router.get('/version')", "@public_router.get('/version')")
patch(p, "return {'product': 'contract-review', 'version': '1.0.0', 'law_source': 'external', 'rules_source': 'database'}",
      "return {'product': 'contract-review', 'version': '1.0.0', 'law_source': 'external', 'rules_source': 'database',\n            'max_only': True, 'model_gateway': 'ydata', 'model_selection_version': 1}")
patch(p, "@router.get('/capabilities')", '''@public_router.get('/access')
async def legal_access(user: dict = Depends(get_current_user), db=Depends(get_db)):
    return await access_status(user, db)


def _gateway_failure(exc):
    return HTTPException(exc.status_code, {'error': exc.code, 'message': exc.message})


@router.get('/models')
def models():
    try:
        return ydata.model_catalog()
    except ydata.GatewayError as exc:
        raise _gateway_failure(exc) from None


@router.get('/capabilities')''')
patch(p, "def capabilities(user: dict = Depends(get_current_user)):\n    from configs.settings import openai_configured",
      "def capabilities(user: dict = Depends(get_current_user)):")
patch(p, "'model_configured': openai_configured()", "'model_configured': ydata.configured(), 'model_gateway': 'ydata'")
patch(p, "    from configs.settings import openai_configured\n    if not openai_configured():\n        raise HTTPException(503, '审查模型尚未配置，不会生成模拟审查结论。')",
      "    try:\n        selected = ydata.select_model(request.model_id)\n    except ydata.GatewayError as exc:\n        raise _gateway_failure(exc) from None")
patch(p, "exclude={'external_processing_confirmed', 'fresh_review'}",
      "exclude={'external_processing_confirmed', 'fresh_review', 'external_processing_provider', 'model_id'}")
patch(p, "    profile['review_date'] = date.today().isoformat()",
      "    profile['model'] = selected\n    profile['external_processing_provider'] = 'ydata'\n    profile['review_date'] = date.today().isoformat()")
patch(p, "    # A failed external search is retried on resume; successful evidence remains timestamped.",
      "    if r['payload'].get('profile', {}).get('external_processing_provider') != 'ydata':\n        raise HTTPException(409, '旧任务未确认 YData 处理授权，请选择模型并新建审查。')\n    # A failed external search is retried on resume; successful evidence remains timestamped.")
p = Path('legal/review_engine.py')
t = p.read_text().replace('from legal import external_law, review_store as store', 'from legal import external_law, review_store as store, ydata, access')
t, n = re.subn(r'def model_json\(system: str, payload: dict\) -> dict:.*?(?=def _norm)',
               "def model_json(system: str, payload: dict) -> dict:\n    return ydata.chat_json(system, payload, payload.get('profile', {}).get('model'))\n\n\n", t, count=1, flags=re.S)
assert n == 1
p.write_text(t)
patch(str(p), 'def authorize_job(job: dict, contract: dict):', "def authorize_job(job: dict, contract: dict):\n    access.assert_worker_max(job['created_by'])")
patch(str(p), "        blocks = c['payload']['redacted_blocks']", "        if payload.get('profile', {}).get('external_processing_provider') != 'ydata':\n            raise ydata.GatewayError('legacy_review_restart_required', '旧任务未确认 YData 授权，请选择模型并新建审查。', 409)\n        blocks = c['payload']['redacted_blocks']")
patch(str(p), "            if checked['findings']:\n                audit_result", "            if checked['findings']:\n                authorize_job(job, c)\n                audit_result")
patch(str(p), "        payload['error'] = '模型或服务调用未完成（' + type(exc).__name__ + '）。未完成部分不代表无风险。'",
      "        payload['error'] = (exc.message if isinstance(exc, ydata.GatewayError) else\n                            'Max 权限或事项权限已变化，请联系管理员后重试。' if getattr(exc, 'status_code', None) == 403 else\n                            '模型或服务调用未完成（' + type(exc).__name__ + '）。未完成部分不代表无风险。')")
p = 'frontend/src/pages/ContractReview.tsx'
patch(p, "import './ContractReview.css';", "import './ContractReview.css';\nimport LegalAccessGate from '../components/LegalAccessGate';\nimport LegalModelPicker from '../components/LegalModelPicker';")
patch(p, 'export default function ContractReview() {', 'export default function ContractReview() {\n  return <LegalAccessGate><ContractWorkbench /></LegalAccessGate>;\n}\n\nfunction ContractWorkbench() {')
patch(p, 'type Review = { id:', 'type Review = { profile?: { model?: { id: string; provider: string } }; id:')
patch(p, "  const [consent, setConsent] = useState(false);", "  const [consent, setConsent] = useState(false);\n  const [modelId, setModelId] = useState('');\n  const selectModel = useCallback((id: string) => { setModelId(id); setConsent(false); }, []);")
patch(p, "external_processing_confirmed: consent, fresh_review: fresh,", "external_processing_confirmed: consent, fresh_review: fresh, model_id: modelId, external_processing_provider: 'ydata',")
patch(p, "        <p className=\"legal-eyebrow\">本事项合同", "        <LegalModelPicker value={modelId} onChange={selectModel} disabled={busy || ['queued', 'running'].includes(review?.status || '')} />\n        <p className=\"legal-eyebrow\">本事项合同")
patch(p, '允许将脱敏正文及适用公司规范发送给已配置的审查模型。', '允许将脱敏正文及适用公司规范经 YData 网关发送给所选模型。')
patch(p, 'disabled={busy || !consent || caps?.model_configured === false', 'disabled={busy || !consent || !modelId || caps?.model_configured !== true')
patch(p, '<small>已记录 {review.coverage.length}', '<small>模型：{review.profile?.model?.id || \'旧版未记录\'} · 已记录 {review.coverage.length}')
patch(p, "    if (!contract) return;\n    const r = await apiFetch<Review>", "    if (!contract || !modelId || !consent) return;\n    const r = await apiFetch<Review>")
p = 'frontend/src/App.tsx'
patch(p, "const ContractReview = lazy", "const MaxMemberships = lazy(() => import('./pages/MaxMemberships'));\nconst ContractReview = lazy")
patch(p, '            <Route path="/admin/recruitment"', '            <Route path="/admin/memberships" element={<AdminRoute><MaxMemberships /></AdminRoute>} />\n            <Route path="/admin/recruitment"')
p = Path('frontend/src/components/Navbar.tsx')
t = p.read_text()
t = t.replace('                          Admin console', '                          Admin console')
# Preserve all existing navigation. Insert one admin-only item before recruitment.
needle = '                        <Link to="/admin/recruitment"'
assert needle in t
t = t.replace(needle, '                        <Link to="/admin/memberships" className="menu-item" role="menuitem">Max 会员</Link>\n' + needle, 1)
p.write_text(t)
# Keep old unit suites focused on their existing tenancy/Word contracts; dedicated
# tests exercise the real Max dependency, not an application-wide test override.
p = 'tests/test_contract_review_product.py'
patch(p, "'profile': {'our_role': '采购方'}", "'profile': {'our_role': '采购方', 'external_processing_provider': 'ydata', 'model': {'id': 'glm-5.2', 'provider': 'ydata'}}")
patch(p, "    application.dependency_overrides[router_module.get_current_user] = lambda: actor", "    application.dependency_overrides[router_module.get_current_user] = lambda: actor\n    application.dependency_overrides[router_module.require_legal_max] = router_module.get_current_user\n    monkeypatch.setattr(router_module.ydata, 'select_model', lambda mid: {'provider':'ydata','id':mid,'family':'GLM'})")
patch(p, "profile = {'our_role':'采购方','contract_type':'采购合同','external_processing_confirmed':True}", "profile = {'our_role':'采购方','contract_type':'采购合同','external_processing_confirmed':True,'external_processing_provider':'ydata','model_id':'glm-5.2'}")
p = 'scripts/legal_ui_smoke.py'
patch(p, "    elif path == '/legal/workspace':", "    elif path == '/legal/access': data={'allowed':True,'plan':'max','required_plan':'max'}\n    elif path == '/legal/models': data={'models':[{'id':'glm-5.2','family':'GLM'},{'id':'claude-test','family':'Claude'}],'families':['GPT','Claude','DeepSeek','Kimi','GLM'],'default_model':'glm-5.2','catalog_source':'gateway','notice':'mock'}\n    elif path == '/legal/workspace':")
patch(p, "        assert req.post_data_json['external_processing_confirmed'] is True", "        assert req.post_data_json['model_id'] == 'glm-5.2'\n        assert req.post_data_json['external_processing_provider'] == 'ydata'\n        assert req.post_data_json['external_processing_confirmed'] is True")
patch(p, '允许将脱敏正文及适用公司规范发送给已配置的审查模型。', '允许将脱敏正文及适用公司规范经 YData 网关发送给所选模型。')
# Frontend may ship only after the backend implements the server-side paywall.
p = 'scripts/verify_legal_release.mjs'
patch(p, "version.version !== '1.0.0'", "version.version !== '1.0.0' || version.max_only !== true || version.model_gateway !== 'ydata' || version.model_selection_version !== 1")
p = 'scripts/verify_legal_release.test.mjs'
patch(p, "Response.json({ product: 'contract-review', version: '1.0.0' })", "Response.json({ product: 'contract-review', version: '1.0.0', max_only: true, model_gateway: 'ydata', model_selection_version: 1 })")
with Path(p).open('a') as f:
    f.write("\ntest('production blocks an old backend without Max enforcement', async () => {\n  await assert.rejects(verifyLegalRelease('production', async () => Response.json({product:'contract-review',version:'1.0.0'})), /incompatible/);\n});\n")
print('Applied scoped model, Max access and UI wiring; original pages and Word exporter unchanged.')
print('Existing legal API test modules:', [str(p) for p in Path('tests').glob('*.py') if '/legal/' in p.read_text()])
