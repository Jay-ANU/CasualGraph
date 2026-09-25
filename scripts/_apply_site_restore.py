"""One-off restoration builder; reads the immutable pre-legal UI, never resets main."""
from __future__ import annotations
import ast
import os
import re
import subprocess
from pathlib import Path

BASE = 'd3ea3fb953b618ade9483f84f82b37a21b2c0d8d'
ROOT = Path(__file__).resolve().parents[1]

def old(path):
    return subprocess.check_output(['git', 'show', f'{BASE}:{path}'], cwd=ROOT)

def put(path, text):
    p = ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(text if isinstance(text, bytes) else text.encode())

def patch(path, before, after):
    p = ROOT / path
    text = p.read_text()
    assert before in text, (path, before[:90])
    p.write_text(text.replace(before, after))

old_files = set(subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', BASE], cwd=ROOT).decode().splitlines())
restored = set()

def restore(path):
    put(path, old(path))
    restored.add(path)

for name in ('Home', 'About', 'CausalInference', 'DesktopDownload', 'EsgDemo', 'Recruitment', 'OfferView'):
    restore(f'frontend/src/pages/{name}.tsx')
# Only restore MISSING relative imports. Keep the new authentication and API client.
while True:
    missing = set()
    for name in list(restored):
        if not name.endswith(('.ts', '.tsx', '.css')):
            continue
        for rel in re.findall(r'''(?:from\s*|import\s*)['"](\.[^'"]+)['"]''', (ROOT / name).read_text()):
            base = (ROOT / name).parent / rel
            candidates = [base, *(Path(str(base) + x) for x in ('.ts', '.tsx', '.css')), base / 'index.ts', base / 'index.tsx']
            if any(p.is_file() for p in candidates):
                continue
            for p in candidates:
                relative = str(p.resolve().relative_to(ROOT))
                if relative in old_files:
                    missing.add(relative)
                    break
    if not missing:
        break
    for name in missing:
        restore(name)
for name in sorted(restored):
    p = ROOT / name
    if p.suffix not in ('.ts', '.tsx'):
        continue
    text = p.read_text()
    if 'process.env.REACT_APP_ESG_API_BASE' in text:
        relative = os.path.relpath(ROOT / 'frontend/src/api/config', p.parent)
        if not relative.startswith('.'):
            relative = './' + relative
        text = f"import {{ apiBase as restoredApiBase }} from '{relative}';\n" + text.replace('process.env.REACT_APP_ESG_API_BASE', 'restoredApiBase()')
    text = text.replace('process.env.REACT_APP_DESKTOP_DOWNLOAD_URL', 'import.meta.env.VITE_DESKTOP_DOWNLOAD_URL')
    text = text.replace('process.env.REACT_APP_GITHUB_REPOSITORY_URL', 'import.meta.env.VITE_GITHUB_REPOSITORY_URL')
    text = text.replace('process.env.PUBLIC_URL', "''")
    p.write_text(text)
for path in old_files:
    if (path.startswith('frontend/public/') and path != 'frontend/public/index.html') or path.startswith('assets/recruitment/'):
        if not (ROOT / path).exists():
            restore(path)

app = old('frontend/src/App.tsx').decode()
app = app.replace('const Recruitment = lazy', "const ContractReview = lazy(() => import('./pages/ContractReview'));\nconst Recruitment = lazy")
app = app.replace("const isWorkspace = location.pathname === '/agent';", "const isWorkspace = ['/agent', '/research', '/legal'].includes(location.pathname);")
app = app.replace('            <Route path="/admin"', '            <Route path="/research" element={<ProtectedRoute><Agent /></ProtectedRoute>} />\n            <Route path="/legal" element={<ProtectedRoute><ContractReview /></ProtectedRoute>} />\n            <Route path="/admin"')
app = app.replace("background: '#04050a'", "background: '#FBFAF8'")
put('frontend/src/App.tsx', app)
patch('frontend/src/components/Navbar.tsx', "  { name: 'Research', href: '/agent' },", "  { name: 'Research', href: '/agent' },\n  { name: 'Graph', href: '/causal-inference' },\n  { name: 'Desktop', href: '/desktop' },\n  { name: 'Company', href: '/about' },\n  { name: '法务 Agent', href: '/legal' },")
patch('frontend/src/components/Navbar.tsx', '                      </Link>\n                    )}', '                      </Link>\n                    )}\n                    {isAdmin && <Link to="/admin/recruitment" className="menu-item" role="menuitem">Recruitment</Link>}')
patch('frontend/src/components/Navbar.tsx', '                  {isAdmin && <Link to="/admin" className="btn btn-secondary">Admin console</Link>}', '                  {isAdmin && <Link to="/admin" className="btn btn-secondary">Admin console</Link>}\n                  {isAdmin && <Link to="/admin/recruitment" className="btn btn-secondary">Recruitment</Link>}')
p = ROOT / 'frontend/src/components/Navbar.tsx'
p.write_text(p.read_text().replace('md:flex', 'lg:flex').replace('md:hidden', 'lg:hidden'))
patch('frontend/src/pages/Home.tsx', '            <Link to="/desktop" className="hover:text-ink">Desktop</Link>', '            <Link to="/desktop" className="hover:text-ink">Desktop</Link>\n            <Link to="/legal" className="hover:text-ink">法务 Agent</Link>')
patch('frontend/index.html', 'CausalGraph 合同逐条审阅 agent：上传合同，逐条查看关键条款与风险，每个回答都附原文出处。', 'CausalGraph answers questions about sustainability reports with source citations. Contract review is available in the separate Legal workspace.')

# One canonical DOCX parser and exporter, without changing intake/ACL contracts.
p = ROOT / 'legal/contract_documents.py'
text = p.read_text()
lines = text.splitlines(keepends=True)
for node in sorted([n for n in ast.parse(text).body if isinstance(n, ast.FunctionDef) and n.name in {'_docx_parts', 'redline_docx'}], key=lambda n: n.lineno, reverse=True):
    del lines[node.lineno - 1:node.end_lineno]
text = ''.join(lines).replace('from lxml import etree', 'from legal.docx_redlines import open_package as _docx_parts, paragraph_text, redline_docx')
text = text.replace('import zipfile\n', '').replace('from datetime import datetime, timezone\n', '')
text = text.replace("''.join(p.xpath('.//w:t[not(ancestor::w:txbxContent)]/text()', namespaces=NS)).strip()", 'paragraph_text(p).strip()')
p.write_text(text)
patch('api/routers/contract_review.py', "format: Literal['json', 'docx', 'txt'] = 'json'", "format: Literal['json', 'docx', 'txt'] | None = None")
patch('api/routers/contract_review.py', "    p, cp = r['payload'], c['payload']\n    if format == 'json':", "    p, cp = r['payload'], c['payload']\n    format = format or ('docx' if cp['format'] == 'docx' else 'json')\n    if cp['format'] == 'docx' and format == 'txt':\n        raise HTTPException(422, 'Word 合同请导出带修订痕迹的 DOCX；审查报告可单独导出。')\n    if format == 'json':")
patch('api/routers/contract_review.py', "            try:\n                content = documents.redline_docx", "            if not changes:\n                raise HTTPException(409, '尚未选择需要纳入修订稿的修改，请先接受至少一项建议。')\n            try:\n                content = documents.redline_docx")
patch('frontend/src/pages/ContractReview.tsx', "'合同修订稿'", "'合同修订稿（含修订痕迹）'")
patch('frontend/src/pages/ContractReview.tsx', "<button disabled={busy} onClick={() => { if (window.confirm('导出包含真实主体信息的原件修改稿？仅应用已接受修改，请在分享前复核。'))", "<button disabled={busy || (contract.format === 'docx' && accepted === 0)} onClick={() => { if (window.confirm('导出包含真实主体信息的修订稿？所选建议在 Word 中仍是待接受或拒绝的修订。请在分享前复核。'))")
patch('frontend/src/pages/ContractReview.tsx', "' Word 修订稿'", "' Word（含修订痕迹）'")
patch('frontend/src/pages/ContractReview.tsx', '原件修改稿会恢复真实信息，且只应用你接受的修改；不是脱敏文件。Word 修订保留删除内容，勿作为脱敏副本分享。', '先接受需要纳入修订稿的建议。导出的 Word 保留新增、删除痕迹，可在 Word「审阅」中逐项接受或拒绝；原格式尽量保留。文件恢复真实信息并保留删除内容，不是脱敏副本。')

# Keep existing offer routes instead of leaving restored offer pages with dead APIs.
# Extract their dependency closure, but always use the current auth/DB dependencies.
restore('recruitment_offers.py')
oldapp = ast.parse(old('app.py').decode())
def names(node):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return [node.name]
    if isinstance(node, ast.Assign):
        return [t.id for t in node.targets if isinstance(t, ast.Name)]
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return [node.target.id]
    return []
defs = {name: n for n in oldapp.body for name in names(n)}
imports = {a.asname or a.name.split('.')[0]: n for n in oldapp.body if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
reuse = {}
for module in ['services.auth', 'services.db', 'services.rate_limit', 'api.deps']:
    for node in ast.parse((ROOT / (module.replace('.', '/') + '.py')).read_text()).body:
        for name in names(node):
            reuse[name] = module
reuse.update(get_db='api.deps', get_current_user='api.deps', require_admin='api.deps')
selected = set()
for n in oldapp.body:
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
        routes = [d.args[0].value for d in n.decorator_list if isinstance(d, ast.Call) and d.args and isinstance(d.args[0], ast.Constant) and isinstance(d.args[0].value, str)]
        if any('recruitment' in route or route.startswith('/offers/') for route in routes):
            selected.add(n.name)
used_imports, reused, pending = set(), set(), list(selected)
while pending:
    node = defs[pending.pop()]
    for child in ast.walk(node):
        if not isinstance(child, ast.Name) or not isinstance(child.ctx, ast.Load):
            continue
        dep = child.id
        if dep in {'app', 'router'} or dep in selected:
            continue
        if dep in reuse:
            reused.add(dep)
        elif dep in imports:
            used_imports.add(dep)
        elif dep in defs:
            selected.add(dep)
            pending.append(dep)
body = []
for n in oldapp.body:
    if set(names(n)) & selected:
        for d in getattr(n, 'decorator_list', []):
            if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and isinstance(d.func.value, ast.Name) and d.func.value.id == 'app':
                d.func.value.id = 'router'
        body.append(ast.unparse(n))
import_nodes = list({id(imports[name]): imports[name] for name in used_imports}.values())
text = '\"\"\"Existing recruitment and candidate routes, restored without changing auth.\"\"\"\nfrom __future__ import annotations\nfrom fastapi import APIRouter\n'
text += '\n'.join(ast.unparse(n) for n in import_nodes) + '\n'
text += '\n'.join(f'from {reuse[name]} import {name}' for name in sorted(reused)) + '\n\nrouter = APIRouter()\n\n'
text += '\n\n'.join(body) + '\n'
put('api/routers/recruitment.py', text)
print('RESTORED_OFFER_SYMBOLS', sorted(selected))
print('RESTORED_OFFER_IMPORTS', '\n'.join(ast.unparse(n) for n in import_nodes))
queue, seen = ['api/routers/recruitment.py', 'recruitment_offers.py'], set()
while queue:
    name = queue.pop()
    if name in seen:
        continue
    seen.add(name)
    for n in ast.walk(ast.parse((ROOT / name).read_text())):
        modules = [n.module] if isinstance(n, ast.ImportFrom) and n.module and not n.level else [a.name for a in n.names] if isinstance(n, ast.Import) else []
        for mod in modules:
            path = mod.replace('.', '/') + '.py'
            if path in old_files and not (ROOT / path).exists():
                restore(path)
                queue.append(path)
schema_names = [n.name for n in ast.parse((ROOT / 'recruitment_offers.py').read_text()).body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and ('init' in n.name or 'schema' in n.name)]
print('OFFER_SCHEMA_HELPERS', schema_names)
patch('app.py', 'from api.routers.admin import router as admin_router', 'from api.routers.recruitment import router as recruitment_router\nfrom api.routers.admin import router as admin_router')
patch('app.py', 'auth_router, admin_router,', 'auth_router, admin_router, recruitment_router,')

# Keep the existing browser checks; change only product-label expectations.
patch('scripts/research_ui_smoke.py', "name='合同逐条审阅 agent'", "name='Answers from sustainability reports, with the page they came from.'")
p = ROOT / 'scripts/legal_ui_smoke.py'
p.write_text(p.read_text().replace('导出 Word 修订稿', '导出 Word（含修订痕迹）'))
print('RESTORED_FILES', sorted(restored))
print('RESTORE_COMPLETE')
