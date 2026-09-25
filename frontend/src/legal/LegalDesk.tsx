import React from 'react';
import { apiFetch, jsonRequest, readApiError, withAuth } from '../api/client';
import { apiBase } from '../api/config';
import type { Answer, Api, Block, Capabilities, Catalog, Contract, ContractSummary, Decision, Finding, Matter, Policy, Review, User, Workspace } from './types';
import { FindingCard, Icon, ModelSelect, PolicyEditor, ReviewReport } from './parts';
import './LegalDesk.css';
import { PartyBinding, DraftReleasePanel } from './AuditControls';
import { findingCounts, findingStatus } from './findingStatus';

type Props = { user: User | null; logout: () => void; request?: Api };
type State = {
  workspace: Workspace | null; matters: Matter[]; contracts: ContractSummary[]; contract: Contract | null;
  review: Review | null; policies: Policy[]; caps: Capabilities | null; catalog: Catalog | null;
  busy: boolean; loading: boolean; error: string; modelError: string; modelsLoading: boolean;
  tab: 'review' | 'policies'; mobileMenu: boolean; showDocument: boolean; setupOpen: boolean;
  ourRole: string; contractType: string; date: string; instructions: string; consent: boolean; modelId: string;
  terms: string; preview: Block[] | null; selectedBlock: string | null; filter: string; statusFilter: string;
  historyQuery: string; question: string; answers: Answer[]; questionBusy: boolean; questionConsent: boolean;
  ourPartyBlock: string; ourPartyQuote: string; excludedTerms: string; originalBlocks: Block[] | null;
  notice: string; denied: boolean; reviewMode: 'standard' | 'multi_agent';
  performanceStage: string; attachmentsStatus: string; businessPriority: string; dealValue: string; currency: string;
};
const TYPES = ['采购合同', '服务合同', '保密协议', '其他商事合同'];
const ROLES = ['采购方', '供应方', '服务提供方', '服务接受方', '披露方', '接收方'];
const LABEL: Record<string, string> = { queued: '等待审查', running: '正在审查', completed: '待复核', partial: '部分完成', failed: '已暂停', cancelled: '已停止', ready: '可审查', redaction_pending: '待确认脱敏' };
const KINDS = [['all', '全部意见'], ['legal', '法律风险'], ['commercial', '商业利益'], ['company_policy', '公司规范']];
const errorText = (e: unknown) => e instanceof Error ? e.message : '操作未完成，请重试。';

/** Own the desk's request lifecycle; test previews may inject a synthetic API. */
export default class LegalDesk extends React.Component<Props, State> {
  state: State = { workspace: null, matters: [], contracts: [], contract: null, review: null, policies: [], caps: null, catalog: null,
    busy: false, loading: true, error: '', modelError: '', modelsLoading: false, tab: 'review', mobileMenu: false,
    showDocument: false, setupOpen: true, ourRole: '', contractType: '采购合同', date: '', instructions: '', consent: false, modelId: '',
    terms: '', preview: null, selectedBlock: null, filter: 'all', statusFilter: 'all', historyQuery: '', question: '', answers: [],
    ourPartyBlock: '', ourPartyQuote: '', excludedTerms: '', originalBlocks: null,
    questionBusy: false, questionConsent: false, notice: '', denied: false, reviewMode: 'multi_agent',
    performanceStage: '未知', attachmentsStatus: '未知', businessPriority: '综合审查', dealValue: '', currency: 'CNY' };
  private live = false;
  private generation = 0;
  private operation = false;
  private polling = false;
  private timer?: ReturnType<typeof setInterval>;
  private priorTitle = '';
  private uploadInput: HTMLInputElement | null = null;
  private focusBeforeMenu: HTMLElement | null = null;
  private api: Api = <T,>(path: string, init?: RequestInit) => (this.props.request || apiFetch)<T>(path, init);

  componentDidMount() {
    this.live = true;
    this.priorTitle = document.title;
    document.title = '合同审查 · CausalGraph';
    void this.initialize();
    this.timer = setInterval(() => void this.poll(), 2500);
  }
  componentWillUnmount() { this.live = false; this.generation++; clearInterval(this.timer); document.title = this.priorTitle; }
  private async initialize() {
    try {
      const [workspace, data, caps] = await Promise.all([
        this.api<Workspace>('/legal/workspace'), this.api<{ matters: Matter[] }>('/matters'), this.api<Capabilities>('/legal/capabilities'),
      ]);
      if (!this.live) return;
      this.setState({ workspace, matters: data.matters, caps });
      const availableContracts = await this.refreshList(workspace);
      await this.loadModels();
      const cid = new URL(window.location.href).searchParams.get('contract');
      if (cid && this.live && availableContracts.some(c => c.id === cid)) await this.openContract(cid);
    } catch (e) { this.fail(e); }
    finally { if (this.live) this.setState({ loading: false }); }
  }
  private fail(e: unknown) {
    if (!this.live) return;
    this.setState({ error: errorText(e) });
    if (e && typeof e === 'object' && 'status' in e && e.status === 401) { this.props.logout(); return; }
    if (e && typeof e === 'object' && 'status' in e && e.status === 403) {
      void this.api<{ allowed: boolean }>('/legal/access').then(a => {
        if (this.live && !a.allowed) this.setState({ denied: true, contract: null, review: null, policies: [], contracts: [], answers: [], originalBlocks: null });
      }).catch(() => { if (this.live) this.setState({ denied: true, contract: null, review: null, policies: [], contracts: [], answers: [], originalBlocks: null }); });
    }
  }
  private run = async (operation: () => Promise<void>) => {
    if (this.operation) return;
    this.operation = true;
    this.setState({ busy: true, error: '', notice: '' });
    try { await operation(); } catch (e) { this.fail(e); }
    finally { this.operation = false; if (this.live) this.setState({ busy: false }); }
  };
  private async refreshList(w: Workspace) {
    const seq = this.generation;
    const [contracts, policies] = await Promise.all([
      this.api<{ contracts: ContractSummary[] }>(`/legal/contracts?matter_id=${encodeURIComponent(w.matter_id)}`),
      this.api<{ policies: Policy[] }>(`/legal/policies?org_id=${encodeURIComponent(w.org_id)}`),
    ]);
    if (this.live && seq === this.generation) this.setState({ contracts: contracts.contracts, policies: policies.policies });
    return contracts.contracts;
  }
  private loadModels = async () => {
    if (this.live) this.setState({ modelsLoading: true, modelError: '' });
    try {
      const catalog = await this.api<Catalog>('/legal/models');
      if (!this.live) return;
      const modelId = catalog.models.some(m => m.id === this.state.modelId) ? this.state.modelId : catalog.default_model;
      this.setState({ catalog, modelId, consent: false });
    } catch (e) { if (this.live) this.setState({ modelError: errorText(e), modelId: '' }); }
    finally { if (this.live) this.setState({ modelsLoading: false }); }
  };
  private async poll() {
    const r = this.state.review;
    if (!r || !['queued', 'running'].includes(r.status) || this.polling) return;
    this.polling = true;
    const seq = this.generation;
    try {
      const updated = await this.api<Review>(`/legal/reviews/${r.id}`);
      if (this.live && seq === this.generation && this.state.review?.id === r.id) this.setState({ review: updated });
    } catch (e) { this.fail(e); }
    finally { this.polling = false; }
  }
  private clear = () => {
    this.generation++;
    this.setState({ originalBlocks: null, ourPartyBlock: '', ourPartyQuote: '', excludedTerms: '', contract: null, review: null, preview: null, terms: '', consent: false, selectedBlock: null,
      instructions: '', ourRole: '', date: '', performanceStage: '未知', attachmentsStatus: '未知', businessPriority: '综合审查', dealValue: '', currency: 'CNY', question: '', answers: [], showDocument: false, setupOpen: true,
      tab: 'review', error: '', notice: '', mobileMenu: false, questionConsent: false }, () => {
      document.querySelector<HTMLTextAreaElement>('[aria-label="审查关注点"]')?.focus();
    });
    history.replaceState(null, '', '/legal');
  };
  private openContract = async (id: string) => {
    const seq = ++this.generation;
    this.setState({ originalBlocks: null, ourPartyBlock: '', ourPartyQuote: '', excludedTerms: '', review: null, preview: null, terms: '', consent: false, selectedBlock: null, answers: [], question: '', questionConsent: false });
    const contract = await this.api<Contract>(`/legal/contracts/${id}`);
    if (!this.live || seq !== this.generation) return;
    this.setState({ contract, tab: 'review', showDocument: true, mobileMenu: false });
    history.replaceState(null, '', `/legal?contract=${encodeURIComponent(id)}`);
    if (contract.reviews.length) {
      const review = await this.api<Review>(`/legal/reviews/${contract.reviews[0].id}`);
      if (!this.live || seq !== this.generation) return;
      this.setState({ review, setupOpen: false, ourRole: review.profile?.our_role || '',
        ourPartyBlock: review.profile?.our_party?.block_id || '', ourPartyQuote: review.profile?.our_party?.quote || '', contractType: review.profile?.contract_type || '采购合同', instructions: review.profile?.instructions || '',
        reviewMode: review.profile?.review_mode || 'standard', date: review.profile?.transaction_date || '',
        performanceStage: review.profile?.transaction_context?.performance_stage || '未知',
        attachmentsStatus: review.profile?.transaction_context?.attachments_status || '未知',
        businessPriority: review.profile?.transaction_context?.business_priority || '综合审查',
        dealValue: review.profile?.transaction_context?.deal_value == null ? '' : String(review.profile.transaction_context.deal_value),
        currency: review.profile?.transaction_context?.currency || 'CNY' });
      if (this.state.caps?.followup_questions) {
        const data = await this.api<{ messages: Answer[] }>(`/legal/reviews/${review.id}/questions`);
        if (this.live && seq === this.generation) this.setState({ answers: data.messages });
      }
    } else this.setState({ setupOpen: true, ourRole: '', instructions: '' });
  };
  private upload = async (file?: File) => {
    if (!file || !this.state.workspace) return;
    if (!/\.(docx|pdf|txt)$/i.test(file.name)) throw new Error('请选择 DOCX、文字型 PDF 或 TXT。旧版 .doc 请先另存为 .docx。');
    if (file.size > 10 * 1024 * 1024) throw new Error('文件超过 10 MB，请拆分附件后上传。');
    if (!this.state.caps?.encryption_configured) throw new Error('安全存储尚未就绪，合同没有上传。');
    const disclosure = this.state.caps?.upload_disclosure;
    if (!disclosure) throw new Error('后端尚未支持原件上传说明，请先完成后端升级。');
    if (!window.confirm(`${disclosure.notice}\n存储地域（运营方声明，未核验）：${disclosure.storage_region}\n确认授权上传这份原件？`)) return;
    const workspace = this.state.workspace;
    const form = new FormData(); form.set('matter_id', workspace.matter_id); form.set('file', file); form.set('original_upload_confirmed', 'true'); form.set('upload_notice_version', disclosure.version);
    const contract = await this.api<Contract>('/legal/contracts', { method: 'POST', body: form });
    if (!this.live) return;
    this.generation++;
    this.setState({ originalBlocks: null, ourPartyBlock: '', ourPartyQuote: '', excludedTerms: '', contract, review: null, preview: null, terms: '', consent: false, selectedBlock: null,
      answers: [], question: '', showDocument: true, setupOpen: true, tab: 'review', questionConsent: false });
    history.replaceState(null, '', `/legal?contract=${encodeURIComponent(contract.id)}`);
    await this.refreshList(workspace);
  };
  private redact = async (confirmed: boolean) => {
    const c = this.state.contract; if (!c) return;
    const preview = await this.api<{ blocks: Block[] }>(`/legal/contracts/${c.id}/redaction`, jsonRequest('POST', {
      additional_terms: this.state.terms.split('\n').map(s => s.trim()).filter(Boolean), excluded_terms: this.state.excludedTerms.split('\n').map(s => s.trim()).filter(Boolean), confirmed, revision: c.revision,
    }));
    if (!this.live) return;
    this.setState({ preview: preview.blocks });
    if (confirmed) {
      const contract = await this.api<Contract>(`/legal/contracts/${c.id}`);
      if (this.live) this.setState({ contract, notice: '脱敏已确认。请选择我方角色，再开始审查。' });
      if (this.state.workspace) await this.refreshList(this.state.workspace);
    }
  };
  private start = async () => {
    const s = this.state;
    if (!s.contract || !s.modelId || !s.consent || !s.ourRole || !s.ourPartyBlock || !s.ourPartyQuote) return;
    const review = await this.api<Review>(`/legal/contracts/${s.contract.id}/reviews`, jsonRequest('POST', {
      model_id: s.modelId, external_processing_provider: 'ydata', external_processing_confirmed: true,
      our_party: { block_id: s.ourPartyBlock, quote: s.ourPartyQuote }, our_role: s.ourRole, contract_type: s.contractType, jurisdiction: '中国大陆', transaction_date: s.date || null,
      transaction_context: { performance_stage: s.performanceStage, attachments_status: s.attachmentsStatus, business_priority: s.businessPriority,
        deal_value: s.dealValue.trim() ? Number(s.dealValue) : null, currency: s.currency },
      instructions: s.instructions, fresh_review: Boolean(s.review), review_mode: s.reviewMode,
    }));
    if (this.live) this.setState({ review, setupOpen: false, answers: [], question: '', questionConsent: false });
  };
  private decide = async (f: Finding, value: string, replacement: string, legalBasis: boolean, manual: boolean) => {
    const r = this.state.review; if (!r) return;
    const decision = await this.api<Decision>(`/legal/reviews/${r.id}/findings/${f.id}`, jsonRequest('PATCH', {
      decision: value, text: replacement, expected_version: r.decisions[f.id]?.version || 0,
      legal_basis_confirmed: legalBasis, manual_edit_confirmed: manual,
    }));
    if (this.live && this.state.review?.id === r.id) this.setState(s => ({ review: s.review ? { ...s.review, draft_check: undefined, draft_approval: undefined, decisions: { ...s.review.decisions, [f.id]: decision } } : null }));
  };
  private showOriginal = async () => {
    const c = this.state.contract; if (!c) return;
    if (this.state.originalBlocks) { this.setState({ originalBlocks: null }); return; }
    const seq = this.generation;
    const data = await this.api<{ blocks: Block[] }>(`/legal/contracts/${c.id}/original-text`);
    if (this.live && seq === this.generation && this.state.contract?.id === c.id) this.setState({ originalBlocks: data.blocks, showDocument: true });
  };
  private locate = (id: string) => {
    this.setState({ showDocument: true, selectedBlock: id }, () => {
      document.getElementById(`legal-block-${id}`)?.scrollIntoView({ block: 'center', behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
    });
  };
  private download = async (format: 'docx' | 'txt' | 'md') => {
    const r = this.state.review, c = this.state.contract; if (!r || !c) return;
    if (format !== 'md' && !window.confirm('修订稿包含真实信息以及删除内容，不是脱敏副本。确认导出？')) return;
    const response = await fetch(`${apiBase()}/legal/reviews/${r.id}/export?format=${format === 'md' ? 'json' : format}`, withAuth());
    if (!response.ok) throw await readApiError(response);
    let blob: Blob;
    if (format === 'md') {
      const data: Review = await response.json();
      if (data.id !== r.id) throw new Error('报告与本轮审查不一致，请刷新。');
      blob = new Blob([ReviewReport(data)], { type: 'text/markdown;charset=utf-8' });
    } else blob = await response.blob();
    const url = URL.createObjectURL(blob), a = document.createElement('a');
    a.href = url; a.download = `${format === 'md' ? '合同审查报告' : '合同修订稿（含修订痕迹）'}.${format}`;
    document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 2000);
    if (this.live) this.setState({ notice: format === 'md' ? '已导出可阅读的审查报告。' : '修订稿已导出，请在 Word「审阅」中逐项确认。' });
  };
  private ask = async () => {
    const r = this.state.review, question = this.state.question.trim();
    if (!r || !question || this.state.questionBusy || !this.state.questionConsent) return;
    const seq = this.generation;
    this.setState({ questionBusy: true, error: '' });
    try {
      const answer = await this.api<Answer>(`/legal/reviews/${r.id}/questions`, jsonRequest('POST', {
        question, request_id: crypto.randomUUID(), external_processing_confirmed: true,
      }));
      if (this.live && seq === this.generation && this.state.review?.id === r.id) this.setState(s => ({ answers: [...s.answers, answer], question: '' }));
    } catch (e) { this.fail(e); }
    finally { if (this.live) this.setState({ questionBusy: false }); }
  };
  private toggleMenu = () => {
    if (!this.state.mobileMenu) this.focusBeforeMenu = document.activeElement as HTMLElement;
    this.setState(s => ({ mobileMenu: !s.mobileMenu }), () => {
      if (this.state.mobileMenu) document.getElementById('legal-close-menu')?.focus(); else this.focusBeforeMenu?.focus();
    });
  };
  private menuKey = (event: React.KeyboardEvent<HTMLElement>) => {
    if (!this.state.mobileMenu) return;
    if (event.key === 'Escape') { this.toggleMenu(); return; }
    if (event.key !== 'Tab') return;
    const elements = Array.from(event.currentTarget.querySelectorAll<HTMLElement>('a[href], button:not([disabled]), input, select'));
    const first = elements[0], last = elements[elements.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
  };

  render() {
    const s = this.state, c = s.contract, r = s.review;
    const active = Boolean(r && ['queued', 'running'].includes(r.status));
    const done = Boolean(r && ['completed', 'partial'].includes(r.status));
    const counts = findingCounts(r?.findings || []);
    const partyValid = s.ourPartyQuote.trim().length >= 2 && !!c?.blocks.find(b => b.id === s.ourPartyBlock)?.text.includes(s.ourPartyQuote);
    const accepted = Object.values(r?.decisions || {}).filter(d => d.decision === 'accepted').length;
    const blocks = s.preview || c?.blocks || [];
    const filtered = (r?.findings || []).filter(f => (s.filter === 'all' || f.kind === s.filter)
      && (s.statusFilter === 'all' || (s.statusFilter === 'pending' ? !r?.decisions[f.id] || r.decisions[f.id].decision === 'pending' : r?.decisions[f.id]?.decision === 'accepted')));
    const canUpload = Boolean(s.workspace && s.caps?.encryption_configured && !s.busy && !s.loading);
    const modelProps = { catalog: s.catalog, value: s.modelId, loading: s.modelsLoading, disabled: s.busy || active,
      onChange: (modelId: string) => this.setState({ modelId, consent: false }), onRefresh: () => void this.loadModels() };
    if (s.denied) return <div className="legal-v2"><main className="lv-denied"><h1>法务 Agent 仅限 Max 用户</h1><p>当前账户的授权已变化，合同内容已从此页面移除。</p><a href="/agent">返回研究 Agent</a></main></div>;
    return <div className={`legal-v2 ${s.mobileMenu ? 'lv-menu-open' : ''}`}>
      {s.mobileMenu && <button className="lv-backdrop" aria-label="关闭侧栏" onClick={this.toggleMenu} />}
      <aside className="lv-sidebar" aria-label="法务导航" onKeyDown={this.menuKey}>
        <div className="lv-brand-row"><a href="/" className="lv-brand"><span className="lv-brand-mark">C</span><span>CausalGraph <small>Legal</small></span></a><button id="legal-close-menu" className="lv-icon lv-mobile-only" onClick={this.toggleMenu} aria-label="关闭导航"><Icon name="close" /></button></div>
        <button className="lv-new" disabled={s.busy} onClick={this.clear}><Icon name="plus" />新建审查<span>＋</span></button>
        <nav className="lv-navigation" aria-label="法务工作台">
          <button className={s.tab === 'review' ? 'selected' : ''} onClick={() => this.setState({ tab: 'review', mobileMenu: false })}><Icon name="chat" />合同审查</button>
          <button className={s.tab === 'policies' ? 'selected' : ''} onClick={() => this.setState({ tab: 'policies', mobileMenu: false })}><Icon name="book" />公司规范<span>{s.policies.length}</span></button>
        </nav>
        {s.matters.length > 1 && <label className="lv-workspace">工作空间<select aria-label="事项工作区" value={s.workspace?.matter_id || ''} disabled={s.busy} onChange={e => {
          const m = s.matters.find(x => x.id === e.target.value); if (!m) return;
          void this.run(async () => { this.clear(); const workspace = { matter_id: m.id, org_id: m.org_id }; this.setState({ workspace }); await this.refreshList(workspace); });
        }}>{s.matters.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}</select></label>}
        <label className="lv-search"><Icon name="search" /><input aria-label="查找历史合同" placeholder="查找合同" value={s.historyQuery} onChange={e => this.setState({ historyQuery: e.target.value })} /></label>
        <div className="lv-history-label">最近合同</div><div className="lv-history">
          {s.contracts.filter(item => item.name.toLowerCase().includes(s.historyQuery.toLowerCase())).map(item => <button key={item.id} disabled={s.busy} className={c?.id === item.id ? 'selected' : ''} onClick={() => void this.run(() => this.openContract(item.id))}><Icon name="file" /><span>{item.name}<small>{LABEL[item.status] || item.status}</small></span></button>)}
          {!s.loading && !s.contracts.length && <p>审查过的合同会保留在这里。</p>}
        </div>
        <div className="lv-sidebar-bottom"><a href="/agent"><Icon name="arrow" />返回研究 Agent</a><div className="lv-account"><span className="lv-avatar">{(this.props.user?.username || 'U').slice(0, 1)}</span><span>{this.props.user?.username || '我的账户'}<small>Max 工作空间</small></span><button className="lv-icon" onClick={this.props.logout} aria-label="退出登录"><Icon name="exit" /></button></div></div>
      </aside>
      <div className="lv-main-shell">
        <header className="lv-topbar"><button className="lv-icon lv-mobile-only" onClick={this.toggleMenu} aria-label="打开导航"><Icon name="menu" /></button><div className="lv-title">{s.tab === 'policies' ? '公司规范' : c?.name || '法务 Agent'}<span className="lv-max">MAX</span></div><div className="lv-top-actions">{c && s.tab === 'review' && <button className="lv-quiet" onClick={() => this.setState({ showDocument: !s.showDocument })}><Icon name="panel" />{s.showDocument ? '收起原文' : '查看原文'}</button>}<a href="/" className="lv-icon" aria-label="返回网站首页"><Icon name="home" /></a></div></header>
        {s.error && <div className="lv-banner lv-error" role="alert"><Icon name="alert" /><span>{s.error}</span><button className="lv-icon" aria-label="关闭错误" onClick={() => this.setState({ error: '' })}><Icon name="close" /></button></div>}
        {s.notice && <div className="lv-banner lv-notice" role="status"><Icon name="check" /><span>{s.notice}</span><button className="lv-icon" aria-label="关闭提示" onClick={() => this.setState({ notice: '' })}><Icon name="close" /></button></div>}
        {s.caps && !s.caps.encryption_configured && <div className="lv-banner lv-warning">安全存储未配置，暂不能上传合同。请联系管理员；不会绕过加密上传。</div>}
        {s.modelError && <div className="lv-banner lv-warning"><span>{s.modelError}</span><button onClick={() => void this.loadModels()}>重新读取模型</button></div>}
        <input ref={el => { this.uploadInput = el; }} type="file" accept=".docx,.pdf,.txt" hidden onChange={e => { const file = e.target.files?.[0]; e.target.value = ''; void this.run(() => this.upload(file)); }} />
        {s.loading ? <main className="lv-loading" role="status"><span className="lv-spinner" />正在打开工作空间</main> : s.tab === 'policies' ? <PolicyEditor policies={s.policies} busy={s.busy} onSave={(draft, existing) => void this.run(async () => {
          if (!s.workspace) return;
          await this.api(`/legal/policies${existing ? `/${existing.id}` : ''}?org_id=${encodeURIComponent(s.workspace.org_id)}`, jsonRequest(existing ? 'PUT' : 'POST', { ...draft, version: existing?.version }));
          await this.refreshList(s.workspace);
        })} onArchive={p => { if (window.confirm('归档这条规范？既有审查仍保留原版本。')) void this.run(async () => { if (!s.workspace) return; await this.api(`/legal/policies/${p.id}?org_id=${encodeURIComponent(s.workspace.org_id)}&version=${p.version}`, { method: 'DELETE' }); await this.refreshList(s.workspace); }); }} /> : !c ?
          <main className="lv-welcome" onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); if (e.dataTransfer.files.length !== 1) { this.setState({ error: '请一次上传一份合同。' }); return; } void this.run(() => this.upload(e.dataTransfer.files[0])); }}>
            <div className="lv-welcome-content"><div className="lv-intro-mark"><Icon name="document" /></div><p className="lv-eyebrow">YOUR CONTRACT, YOUR SIDE</p><h1>今天需要审查哪份合同？</h1><p className="lv-subtitle">从你的立场看条款，把风险、依据和修改放在一起。</p>
              <div className="lv-composer"><textarea aria-label="审查关注点" value={s.instructions} maxLength={1500} onChange={e => this.setState({ instructions: e.target.value, consent: false })} placeholder="有什么特别关注的？例如预付款保障、交付时间，或一条不确定的约定。" /><div className="lv-composer-footer"><button className="lv-attach" disabled={!canUpload} onClick={() => this.uploadInput?.click()} aria-label="选择一份合同开始"><Icon name="attach" />上传合同</button><ModelSelect {...modelProps} /></div></div>
              <div className="lv-starters">{TYPES.slice(0, 3).map(t => <button key={t} className={s.contractType === t ? 'selected' : ''} onClick={() => this.setState({ contractType: t })}><Icon name="file" />{t}</button>)}</div>
              <p className="lv-file-hint">拖入文件也可以 · DOCX、文字型 PDF、TXT · 最大 10 MB</p><div className="lv-trust"><Icon name="lock" /><span>原件先上传后端，再解析、加密保存并脱敏；不是浏览器本地脱敏。模型外发另行确认。</span></div>
            </div><p className="lv-bottom-note">法律依据来自外部检索，公司规范单独存储。AI 意见需人工核验。</p>
          </main> : <div className={`lv-workbench ${s.showDocument ? 'with-document' : ''}`}>
            <main className="lv-conversation" aria-label="合同审查对话"><div className="lv-conversation-inner">
              <div className="lv-upload-message"><Icon name="file" /><span><strong>{c.name}</strong><small>{c.format.toUpperCase()} · {blocks.length} 个段落</small></span><span className="lv-status">{LABEL[r?.status || c.status]}</span></div>
              {c.status === 'ready' && c.redaction_version !== 2 && <p className="lv-inline-warning">此合同使用旧版脱敏。历史报告仍可查看；请新建审查并重新上传以使用主体绑定和安全修订导出。</p>}
              {c.warnings.length > 0 && <details className="lv-details"><summary>文档解析范围 · {c.warnings.length} 项提示</summary>{c.warnings.map((w, i) => <p key={i}>{w}</p>)}</details>}
              {c.status === 'redaction_pending' ? <section className="lv-step-card"><div className="lv-step-heading"><span>01</span><h2>先确认哪些信息需要隐藏</h2></div><p>右侧显示脱敏预览。自动识别可能遗漏，请检查主体、联系人和账户；交易金额与期限默认保留。</p><button className="lv-quiet" disabled={s.busy} onClick={() => void this.run(this.showOriginal)}><Icon name="panel" />{s.originalBlocks ? '关闭真实原文对照' : '对照真实原文（仅有编辑权限可见）'}</button><label>补充脱敏词<textarea aria-label="补充脱敏词" rows={2} value={s.terms} onChange={e => this.setState({ terms: e.target.value, preview: null })} placeholder="每行一项：公司名称、联系人、项目代号" /></label><label>撤销过度脱敏<textarea aria-label="撤销过度脱敏词" rows={2} value={s.excludedTerms} onChange={e => this.setState({ excludedTerms: e.target.value, preview: null })} placeholder="每行填写一项被错误遮蔽的原文字词；撤销后这些内容可能发送给模型，请核对。" /></label><div className="lv-actions"><button className="lv-secondary" disabled={s.busy} onClick={() => void this.run(() => this.redact(false))}>更新预览</button><button className="lv-primary" disabled={s.busy} onClick={() => { if (window.confirm('确认已检查脱敏？本版本的脱敏映射确认后不可更改。')) void this.run(() => this.redact(true)); }}>已检查，确认脱敏<Icon name="arrow-right" /></button></div></section> : <section className="lv-settings">
                <button className="lv-settings-heading" onClick={() => this.setState({ setupOpen: !s.setupOpen })}><span><Icon name="settings" />{r ? '本轮审查设置' : '确认审查立场'}</span><small>{s.ourRole || '尚未选择'}<Icon name="chevron" /></small></button>
                {s.setupOpen && <div className="lv-settings-body"><PartyBinding blocks={c.blocks} blockId={s.ourPartyBlock} quote={s.ourPartyQuote} disabled={s.busy || active} onChange={(ourPartyBlock, ourPartyQuote) => this.setState({ ourPartyBlock, ourPartyQuote, consent: false })} /><div className="lv-fields"><label>我方角色<select aria-label="我方角色" value={s.ourRole} disabled={s.busy || active} onChange={e => this.setState({ ourRole: e.target.value, consent: false })}><option value="">选择我方在交易中的身份</option>{ROLES.map(role => <option key={role}>{role}</option>)}</select></label><label>合同类型<select value={s.contractType} disabled={s.busy || active} onChange={e => this.setState({ contractType: e.target.value, consent: false })}>{TYPES.map(t => <option key={t}>{t}</option>)}</select></label></div><label>补充要求<textarea aria-label="补充审查要求" maxLength={1500} rows={2} value={s.instructions} disabled={s.busy || active} onChange={e => this.setState({ instructions: e.target.value, consent: false })} placeholder="描述你关注的条款或谈判目标，不要填写额外敏感信息。" /></label><details className="lv-advanced"><summary>交易背景与法律适用</summary><div className="lv-fields"><label>履行阶段<select aria-label="履行阶段" value={s.performanceStage} disabled={s.busy || active} onChange={e => this.setState({ performanceStage: e.target.value, consent: false })}><option>未知</option><option>拟签署</option><option>谈判中</option><option>已签署未履行</option><option>履行中</option><option>发生争议</option></select></label><label>关键附件<select aria-label="关键附件状态" value={s.attachmentsStatus} disabled={s.busy || active} onChange={e => this.setState({ attachmentsStatus: e.target.value, consent: false })}><option>未知</option><option>已提供全部关键附件</option><option>存在未提供附件</option><option>无附件</option></select></label></div><div className="lv-fields"><label>本轮业务优先级<select aria-label="业务优先级" value={s.businessPriority} disabled={s.busy || active} onChange={e => this.setState({ businessPriority: e.target.value, consent: false })}><option>综合审查</option><option>付款与回款</option><option>交付与验收</option><option>责任限制</option><option>退出与解除</option><option>知识产权</option><option>保密与数据</option></select></label><label>交易金额（可留空）<span className="lv-money"><input aria-label="交易金额" type="number" min="0" step="0.01" value={s.dealValue} disabled={s.busy || active} onChange={e => this.setState({ dealValue: e.target.value, consent: false })} /><select aria-label="交易币种" value={s.currency} disabled={s.busy || active} onChange={e => this.setState({ currency: e.target.value, consent: false })}><option>CNY</option><option>USD</option><option>EUR</option><option>HKD</option><option>OTHER</option></select></span></label></div><label>交易日期（未知可留空）<input type="date" value={s.date} disabled={s.busy || active} onChange={e => this.setState({ date: e.target.value, consent: false })} /></label><p>这些是用户确认的交易背景，不覆盖合同原文。附件未知或缺失时，依赖附件的判断必须保留缺口；法律来源的原文匹配也不等于版本和时间适用已核实。</p></details><ModelSelect {...modelProps} /><label className="lv-review-mode">审查方式<select aria-label="审查方式" value={s.reviewMode} disabled={s.busy || active} onChange={e => this.setState({ reviewMode: e.target.value as 'standard' | 'multi_agent', consent: false })}><option value="multi_agent">多 Agent 协作审查</option><option value="standard">常规审查</option></select><small>协作模式分别检查法律、公司利益与内部规范，再交叉复核。各 Agent 使用同一所选模型，会增加调用量。</small></label><label className="lv-consent"><input type="checkbox" checked={s.consent} disabled={s.busy || active} onChange={e => this.setState({ consent: e.target.checked })} /><span>允许将脱敏正文、补充要求及适用公司规范经 YData 网关发送给所选模型。</span></label><button className="lv-primary lv-start" disabled={s.busy || active || !s.consent || !s.modelId || !s.ourRole || !partyValid || c.redaction_version !== 2 || s.caps?.model_configured === false} onClick={() => void this.run(this.start)}>{s.busy ? <span className="lv-spinner" /> : <Icon name="arrow-right" />}{r ? '新建一轮审查' : '开始审查'}</button></div>}
              </section>}
              {r && <section className="lv-assistant-response"><div className="lv-assistant-label"><span className="lv-agent-mark">C</span>法务 Agent<small>{r.profile?.model?.id || s.modelId}</small></div><div className="lv-progress" role="status">{active && <span className="lv-spinner" />}<strong>{r.stage}</strong>{r.progress && r.progress.total > 0 && <small>{r.progress.completed} / {r.progress.total} 步</small>}</div>{r.collaboration && <details className="lv-team" aria-label="协作进度" open={active}><summary>协作审查 · 独立分析，统一复核</summary><div className="lv-team-grid">{r.collaboration.agents.map(agent => <div className={`lv-team-agent is-${agent.status}`} key={agent.id}><strong>{agent.title}</strong><span>{({ pending: '等待开始', running: '进行中', completed: '已完成', partial: '部分完成', paused: '已暂停', not_applicable: '本轮不适用' } as Record<string, string>)[agent.status] || '状态待确认'}{agent.total > 0 && ` · ${agent.completed}/${agent.total}`}</span>{agent.note && <small>{agent.note}</small>}</div>)}</div><p>各 Agent 只提出建议，不直接修改合同。分歧与修改冲突仍需人工处理。</p></details>}{active && <p className="lv-muted">正在读取全文与外部依据。你可以稍后从最近合同中继续查看；未完成步骤不代表无风险。</p>}{active && (s.caps?.review_engine_version || 0) >= 2 && <button className="lv-quiet" disabled={s.busy} onClick={() => void this.run(async () => { const review = await this.api<Review>(`/legal/reviews/${r.id}/cancel`, { method: 'POST' }); if (this.live) this.setState({ review }); })}><Icon name="stop" />停止后续步骤</button>}{r.error && <div className="lv-inline-warning">{r.error}</div>}{r.resumable && <button className="lv-secondary" disabled={s.busy} onClick={() => void this.run(async () => { const review = await this.api<Review>(`/legal/reviews/${r.id}/resume`, { method: 'POST' }); if (this.live) this.setState({ review }); })}><Icon name="refresh" />重试未完成步骤</button>}
                {r.intake?.facts && r.intake.facts.length > 0 && <details className="lv-facts"><summary>读到的合同要点 · {r.intake.facts.length}</summary><div>{r.intake.facts.map((f, i) => <button key={i} onClick={() => this.locate(f.block_id)}><small>{f.name}</small><span>{f.value}</span></button>)}</div></details>}
                {done && <div className="lv-result-summary"><h2>{counts.actionable ? `有 ${counts.actionable} 项值得进一步处理` : '本轮没有形成可展示的审查意见'}</h2><p>{r.status === 'partial' ? '部分依据或检查尚未完成，请先查看覆盖缺口。' : '下面按优先级列出问题；每一项都由你决定如何处理。'}{!r.findings.length && '这不代表合同没有风险。'}</p><div className="lv-summary-chips"><span><i className="lv-dot high" />{counts.high} 项有依据的重点</span><span>{r.coverage.filter(x => ['reviewed', 'not_applicable'].includes(x.status)).length} / {r.coverage.length} 项检查</span><span>{counts.unconfirmed} 项待核实</span><span>{counts.rejected} 项候选已否定</span><span>{accepted} 项已纳入修订</span></div></div>}
                {(r.findings.length > 0 || done) && <section className="lv-results"><div className="lv-filters" role="tablist" aria-label="意见类别">{KINDS.map(([key, label]) => <button key={key} role="tab" aria-selected={s.filter === key} className={s.filter === key ? 'selected' : ''} onClick={() => this.setState({ filter: key })}>{label}</button>)}</div><div className="lv-result-tools"><span>{filtered.length} 项意见</span><select aria-label="处理状态" value={s.statusFilter} onChange={e => this.setState({ statusFilter: e.target.value })}><option value="all">全部状态</option><option value="pending">待处理</option><option value="accepted">已纳入修订</option></select></div>{filtered.map((f, i) => <FindingCard key={`${r.id}-${f.id}-${r.decisions[f.id]?.version || 0}`} finding={f} review={r} original={blocks.find(b => b.id === f.block_id)?.text || ''} busy={s.busy} initiallyOpen={i === 0} onLocate={this.locate} onDecision={(value, replacement, legalBasis, manual) => void this.run(() => this.decide(f, value, replacement, legalBasis, manual))} />)}{!filtered.length && <p className="lv-empty-result">当前筛选下没有意见，不等于没有风险。</p>}</section>}
                <details className="lv-coverage"><summary><Icon name="list" />查看检查覆盖与未确认项<span>{r.coverage.length}</span></summary>{r.coverage.map(item => <div key={item.rule_id}><strong>{item.title}</strong><small>{({ reviewed: '已检查', not_applicable: '不适用', needs_information: '待确认', not_reviewed: '未完成' } as Record<string, string>)[item.status] || item.status}</small><p>{item.note}</p>{item.verification_note && <p className="lv-muted">{item.verification_note}</p>}</div>)}{Object.entries(r.batch_errors || {}).map(([key, value]) => <p key={key} className="lv-inline-warning">{value}</p>)}<p>{r.notice}</p></details>
              </section>}
              {done && s.caps?.followup_questions && <section className="lv-followup"><h2>继续问这份合同</h2><p className="lv-muted">使用本轮模型和已取得的依据解释，不会自动修改合同。</p>{s.answers.map(a => <div className="lv-turn" key={a.id}><div className="lv-user-message">{a.question}</div><div className="lv-answer">{a.answer || (a.status === 'failed' ? '这次提问未完成，请重新发送。' : '正在处理，请刷新后查看。')}{a.block_refs?.map((ref, i) => <button key={i} className="lv-reference" onClick={() => this.locate(ref.block_id)}>原文 {ref.block_id}</button>)}{a.citations?.map((ref, i) => { const source = r?.sources.find(x => x.id === ref.source_id); return source ? <a key={i} className="lv-reference" href={source.url} target="_blank" rel="noreferrer noopener">{source.title}</a> : null; })}{a.uncertain && <small>当前证据仍有不确定性，需要人工核实。</small>}</div></div>)}<div className="lv-question-chips">{['最需要优先谈的是哪几条？', '这份合同还缺少什么保障？'].map(q => <button key={q} onClick={() => this.setState({ question: q })}>{q}</button>)}</div><div className="lv-question-input"><textarea aria-label="追问本轮审查" maxLength={1500} value={s.question} disabled={s.questionBusy} onChange={e => this.setState({ question: e.target.value })} placeholder="问一条意见的原因，或请它解释原文…" /><button className="lv-send" aria-label="发送追问" disabled={s.questionBusy || !s.question.trim() || !s.questionConsent} onClick={() => void this.ask()}>{s.questionBusy ? <span className="lv-spinner" /> : <Icon name="arrow-up" />}</button></div><label className="lv-consent"><input type="checkbox" checked={s.questionConsent} onChange={e => this.setState({ questionConsent: e.target.checked })} />允许将本次提问及本轮脱敏材料发送给原审查模型。</label></section>}
              {done && <DraftReleasePanel key={`${r?.id}-${JSON.stringify(r?.decisions)}`} review={r!} busy={s.busy} onCheck={() => void this.run(async () => { const review = await this.api<Review>(`/legal/reviews/${r!.id}/draft-check`, jsonRequest('POST', { request_id: crypto.randomUUID(), external_processing_confirmed: true })); if (this.live && this.state.review?.id === review.id) this.setState({ review }); })} onApprove={fingerprint => void this.run(async () => { const review = await this.api<Review>(`/legal/reviews/${r!.id}/draft-approval`, jsonRequest('POST', { fingerprint, confirmed: true })); if (this.live && this.state.review?.id === review.id) this.setState({ review }); })} />}
              {done && <footer className="lv-export"><div><strong>{accepted} 项修改已选入修订稿</strong><small>Word 中仍保留可接受、可拒绝的修订；请在分享前复核。</small></div><div className="lv-actions"><button className="lv-secondary" disabled={s.busy} onClick={() => void this.run(() => this.download('md'))}><Icon name="download" />导出审查报告</button><button className="lv-primary" disabled={s.busy || !r?.draft_approval || !accepted} onClick={() => void this.run(() => this.download(c.format === 'docx' ? 'docx' : 'txt'))}>{c.format === 'docx' ? '导出 Word 修订稿' : '导出文字修改稿'}<Icon name="download" /></button></div></footer>}
              <p className="lv-conversation-note">AI 辅助审查，不替代法律意见。原文匹配不代表法条版本和适用性已核实。</p>
            </div></main>
            {s.showDocument && <section className="lv-document" aria-label="脱敏合同正文"><header><div><Icon name="document" /><strong>合同原文</strong><small>脱敏视图</small></div><button className="lv-icon" aria-label="关闭原文面板" onClick={() => this.setState({ showDocument: false })}><Icon name="close" /></button></header><div className="lv-document-scroll"><article className="lv-paper"><h2>{c.name.replace(/\.[^.]+$/, '')}</h2>{blocks.map(b => { const count = r?.findings.filter(f => f.block_id === b.id && findingStatus(f) !== 'rejected').length || 0; return <button id={`legal-block-${b.id}`} key={b.id} className={`lv-paragraph ${s.selectedBlock === b.id ? 'focused' : ''} ${count ? 'has-findings' : ''}`} onClick={() => this.setState({ selectedBlock: b.id })}><small>{b.id}{b.page ? ` · 第 ${b.page} 页` : ''}{count > 0 && <b>{count} 项意见</b>}</small><span>{b.text}</span>{s.originalBlocks && <span className="lv-original-comparison"><strong>上传原文（未外发）</strong>{s.originalBlocks.find(original => original.id === b.id)?.text || '未匹配原文'}</span>}</button>; })}</article></div><footer><Icon name="lock" />此处原件对照仅供人工检查，不进入审查模型请求。修订导出会恢复真实信息。</footer></section>}
          </div>}
      </div>
    </div>;
  }
}
