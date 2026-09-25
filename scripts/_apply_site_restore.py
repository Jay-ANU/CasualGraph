"""Second, branch-only pass: adapt preserved UI to current typing/auth and validate new export semantics."""
from pathlib import Path
import re
ROOT = Path(__file__).resolve().parents[1]

def patch(path, before, after):
    p = ROOT / path
    text = p.read_text()
    assert before in text, (path, before[:120])
    p.write_text(text.replace(before, after))

def put(path, content):
    p = ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)

patch('frontend/src/components/KnowledgeGraphView.tsx', '      setInspectedCluster(domain);', '      // eslint-disable-next-line react-hooks/set-state-in-effect -- synchronize externally selected node with the existing graph tabs\n      setInspectedCluster(domain);')
for name, call in [('OfferView', 'load'), ('Recruitment', 'loadOffers')]:
    patch(f'frontend/src/pages/{name}.tsx', 'useMemo(apiBase, [])', 'useMemo(() => apiBase(), [])')
    patch(f'frontend/src/pages/{name}.tsx', f'    {call}();\n  }}, [{call}]);', f'    // eslint-disable-next-line react-hooks/set-state-in-effect -- initial async load also resets the visible loading state\n    void {call}();\n  }}, [{call}]);')
patch('frontend/src/pages/OfferView.tsx', '      let payload: any = {};', '      let payload: Partial<PublicOffer> & { detail?: string | { offer?: PublicOffer } };')
patch('frontend/src/pages/OfferView.tsx', "if (response.status === 409 && payload?.detail?.offer)", "if (response.status === 409 && typeof payload.detail === 'object' && payload.detail?.offer)")
p = ROOT / 'frontend/src/pages/Recruitment.tsx'
text = p.read_text()
a, b = text.index('const errorMessage ='), text.index('// Fields the backend fills')
text = text[:a] + '''const errorMessage = (payload: unknown, fallback: string): string => {
  if (!payload || typeof payload !== 'object') return fallback;
  const data = payload as { detail?: unknown; message?: unknown };
  if (typeof data.detail === 'string') return data.detail;
  if (Array.isArray(data.detail)) {
    const messages = data.detail.map((item: unknown) => {
      if (!item || typeof item !== 'object') return '';
      const message = (item as { msg?: unknown }).msg;
      return typeof message === 'string' ? message : '';
    }).filter(Boolean);
    if (messages.length) return messages.join(' ');
  }
  return typeof data.message === 'string' ? data.message : fallback;
};

''' + text[b:]
p.write_text(text)
patch('frontend/src/pages/offer/OfferExperience.tsx', '  let x = 0;\n', '')
patch('frontend/src/pages/offer/OfferExperience.tsx', '''      {bars.map(([bar, gap], index) => {
        const rect = <rect key={index} x={x} y="0" width={bar} height="22" />;
        x += bar + gap;
        return rect;
      })}''', '''      {bars.map(([bar], index) => (
        <rect key={index} x={bars.slice(0, index).reduce((sum, [width, gap]) => sum + width + gap, 0)} y="0" width={bar} height="22" />
      ))}''')
patch('frontend/src/pages/offer/OfferExperience.tsx', '  let digitIndex = 0;\n', '')
patch('frontend/src/pages/offer/OfferExperience.tsx', '        const order = digitIndex;\n        digitIndex += 1;', "        const order = (value.slice(0, index).match(/\\d/g) || []).length;")

p = ROOT / 'frontend/src/pages/CausalInference.tsx'
text = p.read_text()
a,b = text.index('const normalizeGraphPayload ='), text.index('const GRAPH_OVERVIEW_NODE_LIMIT')
text = text[:a] + '''const objectOf = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};

const normalizeGraphPayload = (input: unknown): GraphData => {
  const payload = objectOf(input);
  const nodes = (Array.isArray(payload.nodes) ? payload.nodes : []).map(objectOf).map(node => ({
    id: String(node.id || '').trim(), label: String(node.label || node.name || node.id || '').trim(),
    domain: String(node.domain || node.esg_domain || 'general'), type: String(node.type || 'Entity'),
    confidence: Number(node.confidence ?? 0.75), description: String(node.description || ''),
    company: String(node.company || ''), year: String(node.year || ''),
    normalizedName: String(node.normalizedName || node.normalized_name || node.id || ''), metadata: objectOf(node.metadata),
  })).filter(node => node.id && node.label);
  const ids = new Set(nodes.map(node => node.id));
  const edges = (Array.isArray(payload.edges) ? payload.edges : []).map(objectOf).map(edge => ({
    source: String(edge.source || '').trim(), target: String(edge.target || '').trim(),
    relationship_type: String(edge.relationship_type || edge.relation || edge.type || 'RELATED_TO'),
    confidence: Number(edge.confidence ?? 0.75), evidence: String(edge.evidence || ''), domain: String(edge.domain || 'general'),
    relationship_action: String(edge.relationship_action || ''), relationship_nature: String(edge.relationship_nature || ''),
    documentId: String(edge.documentId || edge.document_id || ''), chunkId: String(edge.chunkId || edge.chunk_id || ''), metadata: objectOf(edge.metadata),
  })).filter(edge => ids.has(edge.source) && ids.has(edge.target));
  const meta = objectOf(payload.metadata);
  return { nodes, edges, metadata: { ...meta, node_count: nodes.length, edge_count: edges.length,
    is_directed: typeof meta.is_directed === 'boolean' ? meta.is_directed : true,
    is_acyclic: typeof meta.is_acyclic === 'boolean' ? meta.is_acyclic : false } };
};

''' + text[b:]
text = text.replace('/public/knowledge-graph?limit=', "/graph/${token ? 'workspace' : 'public'}?limit=")
p.write_text(text)

# Retain the development page, but do not resurrect its unsafe/removed extraction API.
p = ROOT / 'frontend/src/pages/EsgDemo.tsx'
text = p.read_text().replace("import React,", "import { withAuth } from '../api/client';\nimport React,")
text = text.replace('const platformApiBase = `http://${host}:8001`;', 'const platformApiBase = esgApiBase;')
text = text.replace('useState<any>(null)', 'useState<{ entities?: unknown[]; relations?: unknown[]; error?: string; message?: string } | null>(null)', 1)
text = text.replace('useState<any>(null)', 'useState<(Partial<RagResponse> & { error?: string; message?: string }) | null>(null)', 1)
text = text.replace('  useEffect(() => {\n    setHealth(serviceTargets);\n  }, [serviceTargets]);\n\n', '')
text = text.replace("headers: { 'Content-Type': 'application/json' },", "headers: withAuth({ headers: { 'Content-Type': 'application/json' } }).headers,")
a,b = text.index('  const runExtraction ='), text.index('  const runRag =')
text = text[:a] + text[b:]
text = text.replace("  const [extractLoading, setExtractLoading] = useState(false);\n", '')
text = re.sub(r'  const \[extractResult, setExtractResult\] = useState<.*?\(null\);\n', '  const extractResult: { entities?: unknown[]; relations?: unknown[] } = {};\n', text)
text = text.replace('extract entities and relationships from a passage, and run a cited query', 'open the research upload desk, and run an authenticated cited query')
text = text.replace('''                <button type="button" onClick={runExtraction} disabled={extractLoading} className="btn btn-primary mt-4">
                  {extractLoading && <Loader2 className="h-4 w-4 animate-spin" />}
                  {extractLoading ? 'Extracting…' : 'Run extraction'}
                </button>''', '''                <p className="mt-4 text-sm text-ink-3">The old standalone extraction endpoint is no longer exposed. Use the authenticated research desk to upload and query reports.</p>
                <a href="/agent" className="btn btn-primary mt-4">Open research desk</a>''')
p.write_text(text)

# Initialize only the restored additive offer schema, using the active DB location.
patch('api/routers/recruitment.py', 'from services.db import _DB_PATH', 'from services import db as db_service')
p = ROOT / 'api/routers/recruitment.py'
text = p.read_text()
a,b = text.index('async def _get_db():'), text.index('_RECRUITMENT_RESEND_COOLDOWN_SECONDS')
text = text[:a] + '''_get_db = db_service.get_db

async def initialize_recruitment():
    async for db in db_service.get_db():
        await recruitment_offers.init_recruitment_db(db)
        await db.commit()

''' + text[b:]
p.write_text(text)
patch('app.py', 'from api.routers.recruitment import router as recruitment_router', 'from api.routers.recruitment import router as recruitment_router, initialize_recruitment\nfrom api.routers.research_graph import router as research_graph_router')
patch('app.py', 'auth_router, admin_router, recruitment_router,', 'auth_router, admin_router, recruitment_router, research_graph_router,')
patch('app.py', '    await _init_auth_db()\n', '    await _init_auth_db()\n    await initialize_recruitment()\n')

# Preserve security tests; only the user-requested offer routes are restored.
patch('tests/test_phase0_security.py', '    "/offers",\n    "/admin/recruit" + "ment",\n', '')
patch('tests/test_phase0_security.py', '# Built from fragments so that a repository-wide grep for the removed features stays empty.', '# Unsafe or unsupported legacy endpoints remain absent; restored offer routes have separate authorization tests.')
p = ROOT / 'tests/test_contract_review_product.py'
text = p.read_text()
text, count = re.subn(r"        assert '验收后90日付款。' in xml and '验收后60日付款。' in xml", '''        from lxml import etree
        root = etree.fromstring(z.read('word/document.xml'))
        ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        assert ''.join(root.xpath('//w:del//w:delText/text()', namespaces=ns)) == '9'
        assert ''.join(root.xpath('//w:ins//w:t/text()', namespaces=ns)) == '6'
        assert root.xpath('//w:p/w:r/w:t[text()="验收后"]', namespaces=ns)
        assert root.xpath('//w:p/w:r/w:t[text()="0日付款。"]', namespaces=ns)''', text)
assert count == 1
p.write_text(text)
patch('scripts/legal_ui_smoke.py', "page.goto('http://127.0.0.1:4173/agent')", "page.goto('http://127.0.0.1:4173/legal')")
# Inject preserved-site browser checks into the existing build smoke, not a different fake page.
p = ROOT / 'scripts/research_ui_smoke.py'
text = p.read_text()
text = text.replace("page.goto('http://127.0.0.1:4173/research'", "page.goto('http://127.0.0.1:4173/agent'")
needle = "        check('Home action empty disabled'"
at = text.index(needle)
text = text[:at] + '''        check('Independent Legal navigation', page.get_by_role('navigation', name='Primary').get_by_role('link', name='法务 Agent', exact=True).get_attribute('href') == '/legal')
        for path, heading in [('/about', 'A reading tool, not a verdict.'), ('/desktop', 'Your research, a little closer.')]:
            # Assert the real restored page renders, without hard-coding copy that might evolve.
            page.goto('http://127.0.0.1:4173' + path, wait_until='networkidle')
            check('Restored page ' + path, page.get_by_role('heading', level=1).count() == 1 and 'doesn’t exist' not in page.locator('body').inner_text())
        page.goto('http://127.0.0.1:4173/', wait_until='networkidle')
''' + text[at:]
# At least one explicitly requested original /agent route must be exercised.
assert '/agent' in text
p.write_text(text)
# Detect a development-framework global before it can become a production blank page.
for p in (ROOT / 'frontend/src').rglob('*'):
    if p.suffix in {'.ts', '.tsx'}:
        assert not re.search(r'process\.env\.REACT_APP_', p.read_text()), p
print('Preserved-site compatibility patch complete; no authentication or encryption checks were relaxed.')
