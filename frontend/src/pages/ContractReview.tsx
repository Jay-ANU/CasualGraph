import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { apiFetch, jsonRequest, readApiError, withAuth } from '../api/client';
import { apiBase } from '../api/config';
import { useAuth } from '../contexts/AuthContext';
import './ContractReview.css';

type Block = { id: string; text: string; page: number | null };
type Policy = { id: string; title: string; text: string; version: number; contract_type: string };
type Matter = { id: string; org_id: string; name: string; role?: string };
type ContractSummary = { id: string; name: string; status: string; revision: number };
type Contract = ContractSummary & { matter_id: string; org_id: string; format: string; blocks: Block[]; warnings: string[]; replacement_count: number; reviews: { id: string; status: string }[] };
type Source = { id: string; title: string; url: string; retrieved_at: string; text: string; version_status: string };
type Finding = { id: string; block_id: string | null; original_quote: string; title: string; kind: string; severity: string; impact: string; reason: string; suggested_text: string; evidence_status: string; missing_facts: string[]; citations: { source_id: string; supporting_quote: string }[]; policy_ids: string[] };
type Decision = { decision: string; text: string; version: number };
type Review = { id: string; status: string; stage: string; resumable: boolean; error?: string; findings: Finding[]; coverage: { rule_id: string; title: string; status: string; note: string }[]; sources: Source[]; decisions: Record<string, Decision>; policies: Policy[]; notice: string };
type Capabilities = { model_configured: boolean; encryption_configured: boolean; law_search: { provider: string; notice: string } };
const TYPES = ['采购合同', '服务合同', '保密协议', '其他商事合同'];
const ROLES = ['采购方', '供应方', '服务提供方', '服务接受方', '披露方', '接收方'];
const KIND: Record<string, string> = { legal: '法律问题', commercial: '商业利益', company_policy: '公司规范' };
const STATE: Record<string, string> = { queued: '等待审查', running: '审查中', completed: '待人工复核', partial: '部分完成', failed: '已中断', redaction_pending: '待确认脱敏', ready: '可审查' };
const COVERAGE: Record<string, string> = { reviewed: '已检查', not_applicable: '不适用', needs_information: '需补充信息', not_reviewed: '未完成' };
const errorText = (e: unknown) => e instanceof Error ? e.message : '操作未完成，请重试。';

export default function ContractReview() {
  const { user, logout } = useAuth();
  const [workspace, setWorkspace] = useState<{ matter_id: string; org_id: string } | null>(null);
  const [matters, setMatters] = useState<Matter[]>([]);
  const [contracts, setContracts] = useState<ContractSummary[]>([]);
  const [contract, setContract] = useState<Contract | null>(null);
  const [review, setReview] = useState<Review | null>(null);
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [caps, setCaps] = useState<Capabilities | null>(null);
  const [tab, setTab] = useState<'review' | 'policies'>('review');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [ourRole, setOurRole] = useState('采购方');
  const [contractType, setContractType] = useState('采购合同');
  const [transactionDate, setTransactionDate] = useState('');
  const [consent, setConsent] = useState(false);
  const [terms, setTerms] = useState('');
  const [preview, setPreview] = useState<Block[] | null>(null);
  const [selectedBlock, setSelectedBlock] = useState<string | null>(null);
  const [filter, setFilter] = useState('all');
  const [newPolicy, setNewPolicy] = useState({ title: '', text: '', contract_type: '全部' });
  const [editingPolicy, setEditingPolicy] = useState<Policy | null>(null);
  const selection = useRef(0);
  const uploadInput = useRef<HTMLInputElement>(null);

  const run = async (fn: () => Promise<void>) => {
    setBusy(true); setError('');
    try { await fn(); } catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  };
  const refreshList = useCallback(async (w: { matter_id: string; org_id: string }) => {
    const [c, p] = await Promise.all([
      apiFetch<{ contracts: ContractSummary[] }>(`/legal/contracts?matter_id=${encodeURIComponent(w.matter_id)}`),
      apiFetch<{ policies: Policy[] }>(`/legal/policies?org_id=${encodeURIComponent(w.org_id)}`),
    ]);
    setContracts(c.contracts); setPolicies(p.policies);
  }, []);

  useEffect(() => {
    let cancelled = false;
    Promise.all([apiFetch<{ matter_id: string; org_id: string }>('/legal/workspace'),
      apiFetch<{ matters: Matter[] }>('/matters'), apiFetch<Capabilities>('/legal/capabilities')])
      .then(async ([w, ms, capabilities]) => {
        if (cancelled) return;
        setWorkspace(w); setMatters(ms.matters); setCaps(capabilities);
        await refreshList(w);
      }).catch(e => { if (!cancelled) setError(errorText(e)); });
    return () => { cancelled = true; };
  }, [refreshList]);

  const reviewId = review?.id;
  const reviewStatus = review?.status;
  useEffect(() => {
    if (!reviewId || !['queued', 'running'].includes(reviewStatus || '')) return;
    let cancelled = false;
    const timer = window.setInterval(() => {
      apiFetch<Review>(`/legal/reviews/${reviewId}`).then(r => { if (!cancelled) setReview(r); })
        .catch(e => { if (!cancelled) setError(errorText(e)); });
    }, 2500);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [reviewId, reviewStatus]);

  async function openContract(id: string) {
    const seq = ++selection.current;
    setReview(null); setPreview(null); setTerms(''); setConsent(false); setSelectedBlock(null);
    const c = await apiFetch<Contract>(`/legal/contracts/${id}`);
    if (seq !== selection.current) return;
    setContract(c);
    if (c.reviews.length) {
      const r = await apiFetch<Review>(`/legal/reviews/${c.reviews[0].id}`);
      if (seq === selection.current) setReview(r);
    }
  }
  async function upload(file?: File) {
    if (!file || !workspace) return;
    const form = new FormData(); form.set('matter_id', workspace.matter_id); form.set('file', file);
    const c = await apiFetch<Contract>('/legal/contracts', { method: 'POST', body: form });
    ++selection.current; setContract(c); setReview(null); setPreview(null); setTerms(''); setConsent(false);
    await refreshList(workspace);
  }
  async function redact(confirmed: boolean) {
    if (!contract) return;
    const r = await apiFetch<{ blocks: Block[]; confirmed: boolean }>(`/legal/contracts/${contract.id}/redaction`,
      jsonRequest('POST', { additional_terms: terms.split('\n').map(x => x.trim()).filter(Boolean), confirmed, revision: contract.revision }));
    setPreview(r.blocks);
    if (confirmed) {
      setContract(await apiFetch<Contract>(`/legal/contracts/${contract.id}`));
      if (workspace) await refreshList(workspace);
    }
  }
  async function start(fresh = false) {
    if (!contract) return;
    const r = await apiFetch<Review>(`/legal/contracts/${contract.id}/reviews`, jsonRequest('POST', {
      our_role: ourRole, contract_type: contractType, jurisdiction: '中国大陆', transaction_date: transactionDate || null,
      external_processing_confirmed: consent, fresh_review: fresh,
    }));
    setReview(r);
  }
  async function decide(f: Finding, value: string, text: string) {
    if (!review) return;
    const d = await apiFetch<Decision>(`/legal/reviews/${review.id}/findings/${f.id}`, jsonRequest('PATCH', {
      decision: value, text, expected_version: review.decisions[f.id]?.version || 0,
    }));
    setReview(r => r ? { ...r, decisions: { ...r.decisions, [f.id]: d } } : r);
  }
  async function download(format: string) {
    if (!review) return;
    const response = await fetch(`${apiBase()}/legal/reviews/${review.id}/export?format=${format}`, withAuth());
    if (!response.ok) throw await readApiError(response);
    const blob = await response.blob(); const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = `${format === 'json' ? '审查报告' : '合同修订稿'}.${format}`;
    document.body.appendChild(a); a.click(); a.remove(); window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  const displayedBlocks = preview || contract?.blocks || [];
  const findings = (review?.findings || []).filter(f => (filter === 'all' || f.kind === filter) && (!selectedBlock || f.block_id === selectedBlock));
  const done = review && ['completed', 'partial'].includes(review.status);
  const accepted = Object.values(review?.decisions || {}).filter(d => d.decision === 'accepted').length;

  return <div className="legal-app">
    <header className="legal-header">
      <Link to="/" className="legal-brand">CausalGraph <span>LEGAL</span></Link>
      <nav aria-label="法务工作台"><button className={tab === 'review' ? 'active' : ''} onClick={() => setTab('review')}>合同审查</button><button className={tab === 'policies' ? 'active' : ''} onClick={() => setTab('policies')}>公司规范 <small>{policies.length}</small></button></nav>
      <div className="legal-account"><Link to="/research">资料问答</Link><span>{user?.username || user?.email}</span><button onClick={logout}>退出</button></div>
    </header>
    {error && <div className="legal-error" role="alert">{error}<button onClick={() => setError('')} aria-label="关闭错误">×</button></div>}
    {caps && (!caps.encryption_configured || !caps.model_configured) && <div className="legal-warning">{!caps.encryption_configured ? '安全存储未配置，暂不能上传合同。' : '模型未配置，可以管理规范，但暂不能发起审查。'}</div>}
    <div className="legal-layout">
      <aside className="legal-sidebar">
        <label>事项工作区<select aria-label="事项工作区" value={workspace?.matter_id || ''} disabled={busy} onChange={e => { const m = matters.find(x => x.id === e.target.value); if (m) void run(async () => { ++selection.current; setWorkspace({ matter_id: m.id, org_id: m.org_id }); setContract(null); setReview(null); setPreview(null); await refreshList({ matter_id: m.id, org_id: m.org_id }); }); }}>
          {matters.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
        </select></label>
        <button className="legal-primary legal-upload" disabled={busy || !workspace || caps?.encryption_configured === false} onClick={() => uploadInput.current?.click()}>＋ 上传合同</button>
        <input ref={uploadInput} type="file" accept=".docx,.pdf,.txt" hidden onChange={e => { const f = e.target.files?.[0]; e.target.value = ''; void run(() => upload(f)); }} />
        <p className="legal-eyebrow">本事项合同 <span>{contracts.length}</span></p>
        <div className="legal-file-list">{contracts.map(c => <button key={c.id} className={contract?.id === c.id ? 'selected' : ''} disabled={busy} onClick={() => { setTab('review'); void run(() => openContract(c.id)); }}><span>{c.name}</span><small>{STATE[c.status] || c.status}</small></button>)}</div>
        <div className="legal-boundary"><strong>法规外部检索</strong><p>公司规范存入组织数据库；法律依据在审查时检索并保存本轮来源快照。</p><p>不依赖模型记忆生成法条。未查到不等于无风险。</p><small>检索方式：{caps?.law_search.provider || '正在检查'}</small></div>
      </aside>
      {tab === 'policies' ? <main className="legal-policies">
        <p className="legal-eyebrow">COMPANY PLAYBOOK</p><h1>把公司的底线写清楚。</h1><p className="legal-subtitle">这些规则用于判断公司利益，不会被当作法律。只有组织管理员可以修改；每轮审查固定使用当时版本。</p>
        <form className="legal-policy-form" onSubmit={e => { e.preventDefault(); void run(async () => {
          if (!workspace) return;
          await apiFetch(`/legal/policies${editingPolicy ? `/${editingPolicy.id}` : ''}?org_id=${encodeURIComponent(workspace.org_id)}`,
            jsonRequest(editingPolicy ? 'PUT' : 'POST', { ...newPolicy, version: editingPolicy?.version }));
          setNewPolicy({ title: '', text: '', contract_type: '全部' }); setEditingPolicy(null); await refreshList(workspace);
        }); }}>
          <h2>{editingPolicy ? '修改公司规范' : '新增公司规范'}</h2>
          <label>规范标题<input required maxLength={150} value={newPolicy.title} onChange={e => setNewPolicy({ ...newPolicy, title: e.target.value })} placeholder="例如：采购预付款要求" /></label>
          <label>适用合同<select value={newPolicy.contract_type} onChange={e => setNewPolicy({ ...newPolicy, contract_type: e.target.value })}>{['全部', ...TYPES].map(t => <option key={t}>{t}</option>)}</select></label>
          <label>审查要求<textarea required minLength={5} maxLength={2500} rows={4} value={newPolicy.text} onChange={e => setNewPolicy({ ...newPolicy, text: e.target.value })} placeholder="写清适用立场、必须满足的条件、允许的例外，以及什么情况需要升级审批。" /></label>
          <div className="legal-actions"><button className="legal-primary" disabled={busy || !workspace}>保存规范</button>{editingPolicy && <button type="button" onClick={() => { setEditingPolicy(null); setNewPolicy({ title: '', text: '', contract_type: '全部' }); }}>取消</button>}</div>
        </form>
        <div className="legal-policy-list">{policies.map(p => <article key={p.id}><div><h3>{p.title}</h3><small>{p.contract_type} · v{p.version}</small></div><p>{p.text}</p><div className="legal-actions"><button onClick={() => { setEditingPolicy(p); setNewPolicy({ title: p.title, text: p.text, contract_type: p.contract_type }); }}>编辑</button><button disabled={busy} onClick={() => { if (window.confirm('归档此规范？既有审查仍保留原版本。')) void run(async () => { if (!workspace) return; await apiFetch(`/legal/policies/${p.id}?org_id=${encodeURIComponent(workspace.org_id)}&version=${p.version}`, { method: 'DELETE' }); await refreshList(workspace); }); }}>归档</button></div></article>)}</div>
      </main> : !contract ? <main className="legal-empty">
        <p className="legal-eyebrow">CONTRACT REVIEW / 中国大陆商事合同</p><h1>看清风险，<br />再决定怎么签。</h1><p>从公司立场出发，检查法律问题、商业利益与内部规范。每条意见都回到原文和依据。</p>
        <button className="legal-dropzone" disabled={busy || !workspace || caps?.encryption_configured === false} onClick={() => uploadInput.current?.click()}><span>＋</span><strong>选择一份合同开始</strong><small>DOCX / 可复制文字的 PDF / TXT · 最大 10 MB、6 万字</small></button>
        <div className="legal-flow"><span>01 上传与脱敏</span><span>02 确认我方立场</span><span>03 逐条审查与修改</span></div>
        <p className="legal-caption">原件在后端加密保存。确认脱敏前，不向外部模型发送合同内容。</p>
      </main> : <main className="legal-desk">
        <div className="legal-contract-heading"><div><p className="legal-eyebrow">CONTRACT / {contract.format.toUpperCase()}</p><h1>{contract.name}</h1></div><span className="legal-status">{review ? STATE[review.status] : STATE[contract.status]}</span></div>
        {contract.warnings.length > 0 && <details className="legal-parse-note"><summary>本次解析范围 · {contract.warnings.length} 项需人工复核</summary>{contract.warnings.map(w => <p key={w}>{w}</p>)}</details>}
        {contract.status === 'redaction_pending' ? <section className="legal-setup">
          <div><h2>先检查脱敏预览</h2><p>自动识别不能保证无遗漏。请检查正文中的主体、地址、账户等信息；金额、日期与责任比例默认保留。</p></div>
          <label>补充需要遮蔽的内容，每行一个<textarea aria-label="补充脱敏词" rows={2} value={terms} onChange={e => { setTerms(e.target.value); setPreview(null); }} placeholder="公司名称、联系人、项目代号……" /></label>
          <div className="legal-actions"><button disabled={busy} onClick={() => void run(() => redact(false))}>更新预览</button><button className="legal-primary" disabled={busy} onClick={() => { if (window.confirm('已检查脱敏后的正文？确认后本版本不可再更改脱敏映射。')) void run(() => redact(true)); }}>已检查，确认脱敏</button></div>
        </section> : <section className="legal-setup legal-review-setup">
          <label>我方角色<select value={ourRole} onChange={e => setOurRole(e.target.value)}>{ROLES.map(r => <option key={r}>{r}</option>)}</select></label>
          <label>合同类型<select value={contractType} onChange={e => setContractType(e.target.value)}>{TYPES.map(t => <option key={t}>{t}</option>)}</select></label>
          <label>交易日期（未知可留空）<input type="date" value={transactionDate} onChange={e => setTransactionDate(e.target.value)} /></label>
          <label className="legal-consent"><input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} />允许将脱敏正文及适用公司规范发送给已配置的审查模型。</label>
          <button className="legal-primary" disabled={busy || !consent || caps?.model_configured === false || (review !== null && ['queued', 'running'].includes(review.status))} onClick={() => void run(() => start(Boolean(done)))}>{done ? '新建一轮审查' : '开始审查'}</button>
        </section>}
        {review && <div className="legal-progress" role="status"><span>{review.stage}</span><small>已记录 {review.coverage.length} 项检查 · {review.findings.length} 条意见 · 已接受 {accepted} 条</small>{review.resumable && <button disabled={busy} onClick={() => void run(async () => { setReview(await apiFetch<Review>(`/legal/reviews/${review.id}/resume`, { method: 'POST' })); })}>从检查点重试</button>}</div>}
        {review?.error && <p className="legal-warning">{review.error}</p>}
        <div className="legal-panes">
          <section className="legal-document" aria-label="脱敏合同正文"><div className="legal-pane-title"><h2>合同正文</h2><span>{displayedBlocks.length} 个段落 · 脱敏视图</span></div><div className="legal-paper">{displayedBlocks.map(b => { const count = review?.findings.filter(f => f.block_id === b.id).length || 0; return <button key={b.id} className={`legal-block ${selectedBlock === b.id ? 'selected' : ''} ${count ? 'has-findings' : ''}`} onClick={() => setSelectedBlock(selectedBlock === b.id ? null : b.id)}><span className="legal-block-id">{b.id}{b.page ? ` · 第 ${b.page} 页` : ''}{count > 0 && <b>{count} 条意见</b>}</span><span>{b.text}</span></button>; })}</div></section>
          <section className="legal-findings" aria-label="审查意见"><div className="legal-pane-title"><h2>审查意见</h2>{selectedBlock && <button onClick={() => setSelectedBlock(null)}>取消段落筛选</button>}</div>
            <div className="legal-filters">{[['all', '全部'], ...Object.entries(KIND)].map(([k, v]) => <button key={k} className={filter === k ? 'active' : ''} onClick={() => setFilter(k)}>{v}</button>)}</div>
            {!review ? <p className="legal-no-findings">{contract.status === 'redaction_pending' ? '确认脱敏与审查立场后，系统才会开始分析。' : '开始审查后，这里将显示逐条意见、外部来源和建议修改。'}</p> : findings.length === 0 ? <p className="legal-no-findings">当前没有可显示的意见。这不代表合同没有风险，请同时查看审查覆盖和检索状态。</p> : findings.map(f => <FindingCard key={`${review.id}-${f.id}`} finding={f} review={review} busy={busy} onDecision={(v, text) => void run(() => decide(f, v, text))} />)}
            {review && <details className="legal-coverage"><summary>检查覆盖与依据（{review.coverage.length}）</summary>{review.coverage.map(c => <p key={c.rule_id}><strong>{c.title} · {COVERAGE[c.status] || c.status}</strong><br />{c.note}</p>)}<p>{review.notice}</p></details>}
          </section>
        </div>
        {done && <footer className="legal-export"><div><strong>交付前再复核</strong><small>原件修改稿会恢复真实信息，且只应用你接受的修改；不是脱敏文件。Word 修订保留删除内容，勿作为脱敏副本分享。</small></div><button disabled={busy} onClick={() => void run(() => download('json'))}>导出审查报告</button><button disabled={busy} onClick={() => { if (window.confirm('导出包含真实主体信息的原件修改稿？仅应用已接受修改，请在分享前复核。')) void run(() => download(contract.format === 'docx' ? 'docx' : 'txt')); }}>导出{contract.format === 'docx' ? ' Word 修订稿' : '文字修改稿'}</button></footer>}
      </main>}
    </div>
  </div>;
}

function FindingCard({ finding: f, review, busy, onDecision }: { finding: Finding; review: Review; busy: boolean; onDecision: (value: string, text: string) => void }) {
  const decision = review.decisions[f.id];
  const [text, setText] = useState(decision?.text || f.suggested_text);
  const finished = ['completed', 'partial'].includes(review.status);
  return <article className={`legal-finding severity-${f.severity}`}>
    <div className="legal-finding-meta"><span>{KIND[f.kind]}</span><span>{({ high: '重点关注', medium: '需关注', low: '提示' } as Record<string, string>)[f.severity]}</span>{decision && <b>{({ accepted: '已接受', rejected: '已保留原文', pending: '待处理' } as Record<string, string>)[decision.decision]}</b>}</div>
    <h3>{f.title}</h3>{f.original_quote && <blockquote>{f.original_quote}</blockquote>}
    <h4>对公司的影响</h4><p>{f.impact}</p><h4>判断理由</h4><p>{f.reason}</p>
    {f.missing_facts.length > 0 && <p className="legal-warning">待确认：{f.missing_facts.join('；')}</p>}
    {f.citations.map(c => { const s = review.sources.find(x => x.id === c.source_id); return s ? <details className="legal-citation" key={c.source_id}><summary>{s.title}</summary><blockquote>{c.supporting_quote}</blockquote><a href={s.url} target="_blank" rel="noreferrer noopener">查看外部原文 ↗</a><small>检索于 {new Date(s.retrieved_at).toLocaleString('zh-CN')} · 原文已匹配，版本及适用性仍需法务核实</small></details> : null; })}
    {f.policy_ids.map(id => { const p = review.policies.find(x => x.id === id); return p ? <p className="legal-policy-reference" key={id}>公司依据：{p.title} · v{p.version}<br />{p.text}</p> : null; })}
    {f.kind === 'legal' && f.evidence_status !== 'source_matched' && <p className="legal-warning">缺少可核验的法律依据或复核未通过，不能直接接受回写。</p>}
    {f.suggested_text && <label className="legal-suggestion">建议替代本段全文<textarea value={text} onChange={e => setText(e.target.value)} rows={4} maxLength={12000} /></label>}
    <div className="legal-actions"><button className="legal-primary" disabled={busy || !finished || !f.block_id || !f.suggested_text || !text.trim() || (f.kind === 'legal' && f.evidence_status !== 'source_matched')} onClick={() => onDecision('accepted', text)}>接受修改</button><button disabled={busy || !finished} onClick={() => onDecision('rejected', '')}>保留原文</button>{decision && <button disabled={busy || !finished} onClick={() => onDecision('pending', '')}>撤销决定</button>}</div>
  </article>;
}
