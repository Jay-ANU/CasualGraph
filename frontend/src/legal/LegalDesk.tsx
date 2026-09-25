import React from 'react';
import { apiFetch, jsonRequest, readApiError, withAuth } from '../api/client';
import { apiBase } from '../api/config';
import type { Answer, Api, Block, Capabilities, Catalog, Contract, ContractSummary, Decision, Finding, Matter, Policy, Review, User, Workspace } from './types';
import { FindingCard, Icon, ModelSelect, PolicyEditor, ReviewReport } from './parts';
import './LegalDesk.css';
import { PartyBinding, DraftReleasePanel } from './AuditControls';
import { findingStatus } from './findingStatus';
import { ConfirmDialog, Welcome, WorkflowSteps, ReviewOverview } from './DeskExperience';
import { uploadIssue, visibleFindings } from './deskLogic';
import { emptyTransactionInputs, transactionAmount } from './transactionInput';
import { ReviewContext } from './ReviewContext';
import { ScenarioPicker } from './ScenarioPicker';
import { changeScenario, currentScenario, scenarioRoleValid } from './scenarioInput';

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
  exportFormat: 'docx' | 'txt' | null; pendingFile: File | null; confirmingRedaction: boolean; archivePolicy: Policy | null; resultQuery: string; documentQuery: string;
};
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
    performanceStage: '未知', attachmentsStatus: '未知', businessPriority: '综合审查', dealValue: '', currency: 'CNY',
    exportFormat: null, pendingFile: null, confirmingRedaction: false, archivePolicy: null, resultQuery: '', documentQuery: '' };
  private live = false;
  private generation = 0;
  private operation = false;
  private polling = false;
  private modelGeneration = 0;
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
    this.setState({ loading: true, error: '' });
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
    const seq = ++this.modelGeneration;
    if (this.live) this.setState({ modelsLoading: true, modelError: '' });
    try {
      const catalog = await this.api<Catalog>('/legal/models');
      if (!this.live || seq !== this.modelGeneration) return;
      const modelId = catalog.models.some(m => m.id === this.state.modelId) ? this.state.modelId : catalog.default_model;
      this.setState(state => ({ catalog, modelId, consent: modelId === state.modelId ? state.consent : false }));
    } catch (e) { if (this.live && seq === this.modelGeneration) this.setState({ catalog: null, modelError: errorText(e), modelId: '', consent: false }); }
    finally { if (this.live && seq === this.modelGeneration) this.setState({ modelsLoading: false }); }
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
    this.setState({ exportFormat: null, pendingFile: null, confirmingRedaction: false, resultQuery: '', documentQuery: '', filter: 'all', statusFilter: 'all', contractType: '采购合同', ourRole: '', originalBlocks: null, ourPartyBlock: '', ourPartyQuote: '', excludedTerms: '', contract: null, review: null, preview: null, terms: '', consent: false, selectedBlock: null,
      instructions: '', date: '', performanceStage: '未知', attachmentsStatus: '未知', businessPriority: '综合审查', dealValue: '', currency: 'CNY', question: '', answers: [], showDocument: false, setupOpen: true,
      tab: 'review', error: '', notice: '', mobileMenu: false, questionConsent: false }, () => {
      document.querySelector<HTMLButtonElement>('[aria-label="选择一份合同开始"]')?.focus();
    });
    history.replaceState(null, '', '/legal');
  };
  private openContract = async (id: string) => {
    const seq = ++this.generation;
    this.setState({ exportFormat: null, pendingFile: null, confirmingRedaction: false, resultQuery: '', documentQuery: '', filter: 'all', statusFilter: 'all', ...emptyTransactionInputs(), contractType: '采购合同', date: '', ourRole: '', instructions: '', originalBlocks: null, ourPartyBlock: '', ourPartyQuote: '', excludedTerms: '', review: null, preview: null, terms: '', consent: false, selectedBlock: null, answers: [], question: '', questionConsent: false });
    const contract = await this.api<Contract>(`/legal/contracts/${id}`);
    if (!this.live || seq !== this.generation) return;
    this.setState({ contract, tab: 'review', showDocument: window.matchMedia('(min-width: 1100px)').matches, mobileMenu: false });
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
  private queueUpload = (file?: File) => {
    if (!file || this.operation || this.state.loading) return;
    const problem = uploadIssue(file);
    if (problem) { this.setState({ error: problem }); return; }
    if (!this.state.workspace || !this.state.caps?.encryption_configured) {
      this.setState({ error: '安全存储尚未就绪，合同没有上传。请稍后重试。' }); return;
    }
    if (!this.state.caps.upload_disclosure) {
      this.setState({ error: '后端尚未支持原件上传说明，请先完成后端升级。' }); return;
    }
    this.setState({ pendingFile: file, error: '' });
  };
  private upload = async (file?: File) => {
    if (!file || !this.state.workspace) return;
    const problem = uploadIssue(file);
    if (problem) throw new Error(problem);
    if (!this.state.caps?.encryption_configured) throw new Error('安全存储尚未就绪，合同没有上传。');
    const disclosure = this.state.caps?.upload_disclosure;
    if (!disclosure) throw new Error('后端尚未支持原件上传说明，请先完成后端升级。');
    const workspace = this.state.workspace;
    const contractType = !this.state.contract && currentScenario(this.state.caps?.scenario_catalog, this.state.contractType) ? this.state.contractType : '采购合同';
    const form = new FormData(); form.set('matter_id', workspace.matter_id); form.set('file', file); form.set('original_upload_confirmed', 'true'); form.set('upload_notice_version', disclosure.version);
    const contract = await this.api<Contract>('/legal/contracts', { method: 'POST', body: form });
    if (!this.live) return;
    this.generation++;
    this.setState({ pendingFile: null, resultQuery: '', documentQuery: '', filter: 'all', statusFilter: 'all', ...emptyTransactionInputs(), date: '', ourRole: '', instructions: this.state.contract ? '' : this.state.instructions, contractType, originalBlocks: null, ourPartyBlock: '', ourPartyQuote: '', excludedTerms: '', contract, review: null, preview: null, terms: '', consent: false, selectedBlock: null,
      answers: [], question: '', showDocument: window.matchMedia('(min-width: 1100px)').matches, setupOpen: true, tab: 'review', questionConsent: false });
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
      if (this.live) this.setState({ contract, confirmingRedaction: false, originalBlocks: null, showDocument: window.matchMedia('(min-width: 1100px)').matches, notice: '脱敏已确认。下一步，确认合同类型和我方立场。' });
      if (this.state.workspace) await this.refreshList(this.state.workspace);
    }
  };
  private start = async () => {
    const s = this.state;
    if (!s.contract || !s.modelId || !s.consent || !s.ourRole || !s.ourPartyBlock || !s.ourPartyQuote) return;
    if (!scenarioRoleValid(s.caps?.scenario_catalog, s.contractType, s.ourRole)) throw new Error('请根据当前合同类型重新选择我方角色。');
    const amount = transactionAmount(s.dealValue);
    if (!amount.valid) throw new Error('交易金额须为不超过一万亿元、最多两位小数的非负数字。');
    const review = await this.api<Review>(`/legal/contracts/${s.contract.id}/reviews`, jsonRequest('POST', {
      model_id: s.modelId, external_processing_provider: 'ydata', external_processing_confirmed: true,
      scenario_revision: s.caps?.scenario_catalog?.revision,
      our_party: { block_id: s.ourPartyBlock, quote: s.ourPartyQuote }, our_role: s.ourRole, contract_type: s.contractType, jurisdiction: '中国大陆', transaction_date: s.date || null,
      transaction_context: { performance_stage: s.performanceStage, attachments_status: s.attachmentsStatus, business_priority: s.businessPriority,
        deal_value: amount.value, currency: s.currency },
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
  private download = async (format: 'docx' | 'txt' | 'md', confirmed = false) => {
    const r = this.state.review, c = this.state.contract; if (!r || !c) return;
    if (format !== 'md' && !confirmed) { this.setState({ exportFormat: format, error: '' }); return; }
    const response = await fetch(`${apiBase()}/legal/reviews/${r.id}/export?format=${format === 'md' ? 'json' : format}`, withAuth());
    if (!response.ok) throw await readApiError(response);
    let blob: Blob;
    if (format === 'md') {
      const data: Review = await response.json();
      if (data.id !== r.id) throw new Error('报告与本轮审查不一致，请刷新。');
      blob = new Blob([ReviewReport(data)], { type: 'text/markdown;charset=utf-8' });
    } else blob = await response.blob();
    const url = URL.createObjectURL(blob), a = document.createElement('a');
    a.href = url; a.download = `${format === 'md' ? '合同审查报告' : format === 'docx' ? '合同修订稿（含修订痕迹）' : '合同文字修改稿'}.${format}`;
    document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 2000);
    if (this.live) this.setState({ exportFormat: null, notice: format === 'md' ? '已导出可阅读的审查报告。' : format === 'docx' ? '修订稿已导出，请在 Word「审阅」中逐项确认。' : '文字修改稿已导出，请对照原合同复核，不包含 Word 修订标记。' });
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
      requestAnimationFrame(() => { if (!this.live) return; if (this.state.mobileMenu) document.getElementById('legal-close-menu')?.focus(); else this.focusBeforeMenu?.focus(); });
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
    const scenarioValid = scenarioRoleValid(s.caps?.scenario_catalog, s.contractType, s.ourRole);
    const partyValid = s.ourPartyQuote.trim().length >= 2 && !!c?.blocks.find(b => b.id === s.ourPartyBlock)?.text.includes(s.ourPartyQuote);
    const accepted = Object.values(r?.decisions || {}).filter(d => d.decision === 'accepted').length;
    const blocks = s.preview || c?.blocks || [];
    const filtered = r ? visibleFindings(r, s.filter, s.statusFilter, s.resultQuery) : [];
    const visibleBlocks = blocks.filter(block => block.text.toLocaleLowerCase().includes(s.documentQuery.trim().toLocaleLowerCase()));
    const startIssue = c?.redaction_version !== 2 ? '这份合同需要重新上传并确认新版脱敏。'
      : !scenarioRoleValid(s.caps?.scenario_catalog, s.contractType, s.ourRole) ? '请先选择合同类型和我方角色。'
      : !partyValid ? '请确认合同中对应我方的主体原文。'
      : !transactionAmount(s.dealValue).valid ? '请修正交易金额，或将金额留空。'
      : s.modelsLoading ? '正在读取可用模型。'
      : !s.modelId || s.caps?.model_configured === false ? '暂时没有可用的审查模型，请刷新模型列表。'
      : !s.consent ? '开始前，请确认下方的模型处理授权。' : '';
    const scrollTo = (id: string) => { document.getElementById(id)?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' }); };
    const overview = r && done ? <ReviewOverview review={r}
      onPending={() => this.setState({ statusFilter: 'pending', filter: 'all', resultQuery: '' }, () => scrollTo('legal-results'))}
      onUnconfirmed={() => this.setState({ statusFilter: 'unconfirmed', filter: 'all', resultQuery: '' }, () => scrollTo('legal-results'))}
      onExport={() => scrollTo('legal-release')} /> : null;
    const canUpload = Boolean(s.workspace && s.caps?.encryption_configured && !s.busy && !s.loading);
    const modelProps = { catalog: s.catalog, value: s.modelId, loading: s.modelsLoading, disabled: s.busy || active,
      onChange: (modelId: string) => this.setState({ modelId, consent: false }), onRefresh: () => void this.loadModels() };
    if (s.denied) return <div className="legal-v2"><main className="lv-denied"><h1>法务 Agent 仅限 Max 用户</h1><p>当前账户的授权已变化，合同内容已从此页面移除。</p><a href="/agent">返回研究 Agent</a></main></div>;
    return <div className={`legal-v2 ${s.mobileMenu ? 'lv-menu-open' : ''}`}>
      <a className="lv-skip" href="#legal-main">跳到工作区</a>
      {s.mobileMenu && <button className="lv-backdrop" aria-label="关闭侧栏" onClick={this.toggleMenu} />}
      <aside className="lv-sidebar" aria-label="法务导航" role={s.mobileMenu ? 'dialog' : undefined} aria-modal={s.mobileMenu || undefined} onKeyDown={this.menuKey} onTransitionEnd={event => {
        if (event.target === event.currentTarget && this.state.mobileMenu && !event.currentTarget.contains(document.activeElement)) document.getElementById('legal-close-menu')?.focus();
      }}>
        <div className="lv-brand-row"><a href="/" className="lv-brand"><span className="lv-brand-mark">C</span><span>CausalGraph <small>Legal</small></span></a><button id="legal-close-menu" className="lv-icon lv-mobile-only" onClick={this.toggleMenu} aria-label="关闭导航"><Icon name="close" /></button></div>
        <button className="lv-new" disabled={s.busy} onClick={this.clear}><Icon name="plus" />新建审查</button>
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
          {!s.loading && !s.contracts.length && <p>你的合同会保留在这里，随时继续上次审查。</p>}
          {s.contracts.length > 0 && !s.contracts.some(item => item.name.toLowerCase().includes(s.historyQuery.toLowerCase())) && <p role="status">没有找到这份合同。试试文件名中的其他字词。</p>}
        </div>
        <div className="lv-sidebar-bottom"><a href="/agent"><Icon name="arrow" />返回研究 Agent</a><div className="lv-account"><span className="lv-avatar">{(this.props.user?.username || 'U').slice(0, 1)}</span><span>{this.props.user?.username || '我的账户'}<small>Max 工作空间</small></span><button className="lv-icon" onClick={this.props.logout} aria-label="退出登录"><Icon name="exit" /></button></div></div>
      </aside>
      <div className="lv-main-shell" ref={el => { if (el) el.inert = s.mobileMenu; }}>
        <header className="lv-topbar"><button className="lv-icon lv-mobile-only" onClick={this.toggleMenu} aria-label="打开导航"><Icon name="menu" /></button><div className="lv-title">{s.tab === 'policies' ? '公司规范' : c?.name || '法务 Agent'}<span className="lv-max">MAX</span></div><div className="lv-top-actions">{c && s.tab === 'review' && <button className="lv-quiet" onClick={() => this.setState({ showDocument: !s.showDocument })}><Icon name="panel" />{s.showDocument ? '收起原文' : '查看原文'}</button>}<a href="/" className="lv-icon" aria-label="返回网站首页"><Icon name="home" /></a></div></header>
        {s.error && !s.pendingFile && !s.confirmingRedaction && !s.archivePolicy && !s.exportFormat && <div className="lv-banner lv-error" role="alert"><Icon name="alert" /><span>{s.error}</span><button className="lv-icon" aria-label="关闭错误" onClick={() => this.setState({ error: '' })}><Icon name="close" /></button></div>}
        {s.notice && <div className="lv-banner lv-notice" role="status"><Icon name="check" /><span>{s.notice}</span><button className="lv-icon" aria-label="关闭提示" onClick={() => this.setState({ notice: '' })}><Icon name="close" /></button></div>}
        {s.caps && !s.caps.encryption_configured && <div className="lv-banner lv-warning">安全存储未配置，暂不能上传合同。请联系管理员；不会绕过加密上传。</div>}
        {s.modelError && <div className="lv-banner lv-warning"><span>{s.modelError}</span><button onClick={() => void this.loadModels()}>重新读取模型</button></div>}
        <input ref={el => { this.uploadInput = el; }} type="file" accept=".docx,.pdf,.txt" hidden onChange={e => { const file = e.target.files?.[0]; e.target.value = ''; this.queueUpload(file); }} />
        {s.loading ? <main className="lv-loading" role="status"><span className="lv-spinner" />正在打开工作空间</main> : !s.workspace ? <main id="legal-main" className="lv-loading"><Icon name="alert" /><h1>暂时打不开工作空间</h1><p>合同没有上传。检查网络后重试，不需要重复选择文件。</p><button className="lv-primary" onClick={() => void this.initialize()}>重新打开工作空间</button></main> : s.tab === 'policies' ? <PolicyEditor catalog={s.caps?.scenario_catalog} policies={s.policies} busy={s.busy} onSave={(draft, existing) => void this.run(async () => {
          if (!s.workspace) return;
          await this.api(`/legal/policies${existing ? `/${existing.id}` : ''}?org_id=${encodeURIComponent(s.workspace.org_id)}`, jsonRequest(existing ? 'PUT' : 'POST', { ...draft, version: existing?.version }));
          await this.refreshList(s.workspace);
        })} onArchive={policy => this.setState({ archivePolicy: policy, error: '' })} /> : !c ?
          <Welcome caps={s.caps} catalog={s.catalog} modelId={s.modelId} modelLoading={s.modelsLoading}
            disabled={!canUpload} instructions={s.instructions} contractType={s.contractType}
            onUpload={() => this.uploadInput?.click()} onDrop={files => {
              if (files.length !== 1) { this.setState({ error: '请一次上传一份合同。' }); return; }
              this.queueUpload(files[0]);
            }} onInstructions={instructions => this.setState({ instructions, consent: false })}
            onScenario={type => this.setState(changeScenario(s.caps?.scenario_catalog, type))}
            onModel={modelProps.onChange} onRefresh={modelProps.onRefresh} /> : <><WorkflowSteps step={c.status === 'redaction_pending' ? 0 : !r ? 1 : r.draft_approval ? 3 : 2} />
          <div className="lv-mobile-view-switch" aria-label="工作区视图"><button aria-pressed={!s.showDocument} onClick={() => this.setState({ showDocument: false })}>审查工作区</button><button aria-pressed={s.showDocument} onClick={() => this.setState({ showDocument: true })}>合同正文</button></div>
          <div className={`lv-workbench ${s.showDocument ? 'with-document' : ''}`}>
            <main id="legal-main" tabIndex={-1} className="lv-conversation" aria-label="合同审查工作区"><div className="lv-conversation-inner">
              <div className="lv-upload-message"><Icon name="file" /><span><strong>{c.name}</strong><small>{c.format.toUpperCase()} · {blocks.length} 个段落</small></span><span className="lv-status">{LABEL[r?.status || c.status]}</span></div>
              {overview}
              {c.status === 'ready' && c.redaction_version !== 2 && <p className="lv-inline-warning">此合同使用旧版脱敏。历史报告仍可查看；请新建审查并重新上传以使用主体绑定和安全修订导出。</p>}
              {c.warnings.length > 0 && <details className="lv-details"><summary>文档解析范围 · {c.warnings.length} 项提示</summary>{c.warnings.map((w, i) => <p key={i}>{w}</p>)}</details>}
              {c.status === 'redaction_pending' ? <section className="lv-step-card"><div className="lv-step-heading"><span>01</span><h2>先确认哪些信息需要隐藏</h2></div><p>先打开合同正文，核对主体、联系人和账户是否隐藏。自动识别可能遗漏；交易金额与期限默认保留。</p><button className="lv-secondary" onClick={() => this.setState({ showDocument: true })}><Icon name="document" />查看脱敏正文</button><button className="lv-quiet" disabled={s.busy} onClick={() => void this.run(this.showOriginal)}><Icon name="panel" />{s.originalBlocks ? '关闭真实原文对照' : '对照真实原文（仅有编辑权限可见）'}</button><label>补充脱敏词<textarea aria-label="补充脱敏词" rows={2} value={s.terms} onChange={e => this.setState({ terms: e.target.value, preview: null })} placeholder="每行一项：公司名称、联系人、项目代号" /></label><label>撤销过度脱敏<textarea aria-label="撤销过度脱敏词" rows={2} value={s.excludedTerms} onChange={e => this.setState({ excludedTerms: e.target.value, preview: null })} placeholder="每行填写一项被错误遮蔽的原文字词；撤销后这些内容可能发送给模型，请核对。" /></label><div className="lv-actions"><button className="lv-secondary" disabled={s.busy} onClick={() => void this.run(() => this.redact(false))}>更新预览</button><button className="lv-primary" disabled={s.busy} onClick={() => this.setState({ confirmingRedaction: true, error: '' })}>已检查，确认脱敏<Icon name="arrow-right" /></button></div></section> : <section className="lv-settings">
                <button className="lv-settings-heading" aria-expanded={s.setupOpen} aria-controls="legal-setup-body" onClick={() => this.setState({ setupOpen: !s.setupOpen })}><span><Icon name="settings" />{r ? '本轮审查设置' : '确认审查立场'}</span><small>{s.ourRole || '尚未选择'}<Icon name="chevron" /></small></button>
                {s.setupOpen && <div className="lv-settings-body" id="legal-setup-body"><ScenarioPicker catalog={s.caps?.scenario_catalog} type={s.contractType} role={s.ourRole} disabled={s.busy || active}
                  onType={type => this.setState(changeScenario(s.caps?.scenario_catalog, type))}
                  onRole={ourRole => this.setState({ ourRole, consent: false })} /><div className="lv-form-section-title"><span>01</span><h3>确认合同中的我方主体</h3></div><PartyBinding blocks={c.blocks} blockId={s.ourPartyBlock} quote={s.ourPartyQuote} disabled={s.busy || active} onChange={(ourPartyBlock, ourPartyQuote) => this.setState({ ourPartyBlock, ourPartyQuote, consent: false })} /><div className="lv-form-section-title"><span>02</span><h3>告诉我们你的关注点</h3><small>可选</small></div><label>补充要求<textarea aria-label="补充审查要求" maxLength={1500} rows={2} value={s.instructions} disabled={s.busy || active} onChange={e => this.setState({ instructions: e.target.value, consent: false })} placeholder="描述你关注的条款或谈判目标，不要填写额外敏感信息。" /></label><details className="lv-advanced"><summary>交易背景与法律适用</summary><div className="lv-fields"><label>履行阶段<select aria-label="履行阶段" value={s.performanceStage} disabled={s.busy || active} onChange={e => this.setState({ performanceStage: e.target.value, consent: false })}><option>未知</option><option>拟签署</option><option>谈判中</option><option>已签署未履行</option><option>履行中</option><option>发生争议</option></select></label><label>关键附件<select aria-label="关键附件状态" value={s.attachmentsStatus} disabled={s.busy || active} onChange={e => this.setState({ attachmentsStatus: e.target.value, consent: false })}><option>未知</option><option>已提供全部关键附件</option><option>存在未提供附件</option><option>无附件</option></select></label></div><div className="lv-fields"><label>本轮业务优先级<select aria-label="业务优先级" value={s.businessPriority} disabled={s.busy || active} onChange={e => this.setState({ businessPriority: e.target.value, consent: false })}><option>综合审查</option><option>付款与回款</option><option>交付与验收</option><option>责任限制</option><option>退出与解除</option><option>知识产权</option><option>保密与数据</option></select></label><label>交易金额（可留空）<span className="lv-money"><input aria-label="交易金额" type="text" inputMode="decimal" maxLength={16} value={s.dealValue} disabled={s.busy || active} onChange={e => this.setState({ dealValue: e.target.value, consent: false })} /><select aria-label="交易币种" value={s.currency} disabled={s.busy || active} onChange={e => this.setState({ currency: e.target.value, consent: false })}><option>CNY</option><option>USD</option><option>EUR</option><option>HKD</option><option>OTHER</option></select></span></label></div><label>交易日期（未知可留空）<input type="date" value={s.date} disabled={s.busy || active} onChange={e => this.setState({ date: e.target.value, consent: false })} /></label>{!transactionAmount(s.dealValue).valid && <p className="lv-inline-warning" role="alert">交易金额必须是非负数字，最多两位小数，不使用单位或科学计数法。</p>}<p>这些是你填写、尚未独立核实的交易背景，不覆盖合同原文。附件未知或缺失时，依赖附件的判断必须保留缺口；法律来源的原文匹配也不等于版本和时间适用已核实。</p></details><div className="lv-form-section-title"><span>03</span><h3>选择模型并授权审查</h3></div><ModelSelect {...modelProps} /><label className="lv-review-mode">审查方式<select aria-label="审查方式" value={s.reviewMode} disabled={s.busy || active} onChange={e => this.setState({ reviewMode: e.target.value as 'standard' | 'multi_agent', consent: false })}><option value="multi_agent">多 Agent 协作审查</option><option value="standard">常规审查</option></select><small>协作模式分别检查法律、公司利益与内部规范，再交叉复核。各 Agent 使用同一所选模型，会增加调用量。</small></label><label className="lv-consent"><input type="checkbox" checked={s.consent} disabled={s.busy || active} onChange={e => this.setState({ consent: e.target.checked })} /><span>允许将脱敏正文、补充要求及适用公司规范经 YData 网关发送给所选模型。</span></label><p id="legal-start-help" className="lv-start-help">{active ? '本轮正在审查；完成后可调整设置并新建一轮。' : startIssue || '信息已准备好。开始后，本轮设置将保留在报告中。'}</p><button aria-describedby="legal-start-help" className="lv-primary lv-start" disabled={s.busy || active || s.modelsLoading || !s.consent || !s.modelId || !scenarioValid || !partyValid || !transactionAmount(s.dealValue).valid || c.redaction_version !== 2 || s.caps?.model_configured === false} onClick={() => void this.run(this.start)}>{s.busy ? <span className="lv-spinner" /> : <Icon name="arrow-right" />}{r ? '新建一轮审查' : '开始审查'}</button></div>}
              </section>}
              {r && <section className="lv-assistant-response">

                {r.intake?.facts && r.intake.facts.length > 0 && <details className="lv-facts"><summary>读到的合同要点 · {r.intake.facts.length}</summary><div>{r.intake.facts.map((f, i) => <button key={i} onClick={() => this.locate(f.block_id)}><small>{f.name}</small><span>{f.value}</span></button>)}</div></details>}
                {(r.findings.length > 0 || done) && <section className="lv-results" id="legal-results"><div className="lv-filters" role="group" aria-label="意见类别">{KINDS.map(([key, label]) => <button key={key} aria-pressed={s.filter === key} className={s.filter === key ? 'selected' : ''} onClick={() => this.setState({ filter: key })}>{label}</button>)}</div><div className="lv-result-tools"><label className="lv-result-search"><Icon name="search" /><input aria-label="查找审查意见" value={s.resultQuery} onChange={e => this.setState({ resultQuery: e.target.value })} placeholder="查找条款或意见" /></label><span>{filtered.length} 项</span><select aria-label="处理状态" value={s.statusFilter} onChange={e => this.setState({ statusFilter: e.target.value })}><option value="all">全部状态</option><option value="pending">待处理</option><option value="unconfirmed">待核实</option><option value="accepted">已纳入修订</option><option value="draft">人工草稿</option><option value="rejected">已保留原文</option></select></div>{filtered.map((f, i) => <FindingCard key={`${r.id}-${f.id}-${r.decisions[f.id]?.version || 0}`} finding={f} review={r} original={blocks.find(b => b.id === f.block_id)?.text || ''} busy={s.busy} initiallyOpen={i === 0} onLocate={this.locate} onDecision={(value, replacement, legalBasis, manual) => void this.run(() => this.decide(f, value, replacement, legalBasis, manual))} />)}{!filtered.length && <div className="lv-empty-result"><Icon name="search" /><h3>没有符合条件的意见</h3><p>试试其他字词或清除筛选。没有结果不代表没有风险。</p><button className="lv-secondary" onClick={() => this.setState({ resultQuery: '', filter: 'all', statusFilter: 'all' })}>清除筛选</button></div>}</section>}
                <div className="lv-assistant-label"><span className="lv-agent-mark">C</span>法务 Agent<small>{r.profile?.model?.id || s.modelId}</small></div><div className="lv-progress" role="status">{active && <span className="lv-spinner" />}<strong>{r.stage}</strong>{r.progress && r.progress.total > 0 && <small>{r.progress.completed} / {r.progress.total} 步</small>}</div>{r.collaboration && <details className="lv-team" aria-label="协作进度" open={active}><summary>协作审查 · 独立分析，统一复核</summary><div className="lv-team-grid">{r.collaboration.agents.map(agent => <div className={`lv-team-agent is-${agent.status}`} key={agent.id}><strong>{agent.title}</strong><span>{({ pending: '等待开始', running: '进行中', completed: '已完成', partial: '部分完成', paused: '已暂停', not_applicable: '本轮不适用' } as Record<string, string>)[agent.status] || '状态待确认'}{agent.total > 0 && ` · ${agent.completed}/${agent.total}`}</span>{agent.note && <small>{agent.note}</small>}</div>)}</div><p>各 Agent 只提出建议，不直接修改合同。分歧与修改冲突仍需人工处理。</p></details>}{active && <p className="lv-muted">正在读取全文与外部依据。你可以稍后从最近合同中继续查看；未完成步骤不代表无风险。</p>}{active && (s.caps?.review_engine_version || 0) >= 2 && <button className="lv-quiet" disabled={s.busy} onClick={() => void this.run(async () => { const review = await this.api<Review>(`/legal/reviews/${r.id}/cancel`, { method: 'POST' }); if (this.live) this.setState({ review }); })}><Icon name="stop" />停止后续步骤</button>}{r.error && <div className="lv-inline-warning">{r.error}</div>}{r.resumable && <button className="lv-secondary" disabled={s.busy} onClick={() => void this.run(async () => { const review = await this.api<Review>(`/legal/reviews/${r.id}/resume`, { method: 'POST' }); if (this.live) this.setState({ review }); })}><Icon name="refresh" />重试未完成步骤</button>}
                <details className="lv-review-details"><summary><Icon name="book" />查看交易背景、检索依据与检查过程</summary><ReviewContext review={r} onLocate={this.locate} /></details>
                <details className="lv-coverage"><summary><Icon name="list" />查看检查覆盖与未确认项<span>{r.coverage.length}</span></summary>{r.coverage.map(item => <div key={item.rule_id}><strong>{item.title}</strong><small>{({ reviewed: '已检查', not_applicable: '不适用', needs_information: '待确认', not_reviewed: '未完成' } as Record<string, string>)[item.status] || item.status}</small><p>{item.note}</p>{item.verification_note && <p className="lv-muted">{item.verification_note}</p>}</div>)}{Object.entries(r.batch_errors || {}).map(([key, value]) => <p key={key} className="lv-inline-warning">{value}</p>)}<p>{r.notice}</p></details>
              </section>}
              {done && s.caps?.followup_questions && <section className="lv-followup"><h2>继续问这份合同</h2><p className="lv-muted">使用本轮模型和已取得的依据解释，不会自动修改合同。</p>{s.answers.map(a => <div className="lv-turn" key={a.id}><div className="lv-user-message">{a.question}</div><div className="lv-answer">{a.answer || (a.status === 'failed' ? '这次提问未完成，请重新发送。' : '正在处理，请刷新后查看。')}{a.block_refs?.map((ref, i) => <button key={i} className="lv-reference" onClick={() => this.locate(ref.block_id)}>原文 {ref.block_id}</button>)}{a.citations?.map((ref, i) => { const source = r?.sources.find(x => x.id === ref.source_id); return source ? <a key={i} className="lv-reference" href={source.url} target="_blank" rel="noreferrer noopener">{source.title}</a> : null; })}{a.uncertain && <small>当前证据仍有不确定性，需要人工核实。</small>}</div></div>)}<div className="lv-question-chips">{['最需要优先谈的是哪几条？', '这份合同还缺少什么保障？'].map(q => <button key={q} onClick={() => this.setState({ question: q })}>{q}</button>)}</div><div className="lv-question-input"><textarea aria-label="追问本轮审查" maxLength={1500} value={s.question} disabled={s.questionBusy} onChange={e => this.setState({ question: e.target.value })} placeholder="问一条意见的原因，或请它解释原文…" /><button className="lv-send" aria-label="发送追问" disabled={s.questionBusy || !s.question.trim() || !s.questionConsent} onClick={() => void this.ask()}>{s.questionBusy ? <span className="lv-spinner" /> : <Icon name="arrow-up" />}</button></div><label className="lv-consent"><input type="checkbox" checked={s.questionConsent} onChange={e => this.setState({ questionConsent: e.target.checked })} />允许将本次提问及本轮脱敏材料发送给原审查模型。</label></section>}
              {done && <div id="legal-release" className="lv-release"><DraftReleasePanel key={`${r?.id}-${JSON.stringify(r?.decisions)}`} review={r!} busy={s.busy} onCheck={() => void this.run(async () => { const review = await this.api<Review>(`/legal/reviews/${r!.id}/draft-check`, jsonRequest('POST', { request_id: crypto.randomUUID(), external_processing_confirmed: true })); if (this.live && this.state.review?.id === review.id) this.setState({ review }); })} onApprove={fingerprint => void this.run(async () => { const review = await this.api<Review>(`/legal/reviews/${r!.id}/draft-approval`, jsonRequest('POST', { fingerprint, confirmed: true })); if (this.live && this.state.review?.id === review.id) this.setState({ review }); })} /></div>}
              {done && <footer className="lv-export"><div><strong>{accepted} 项修改已选入修订稿</strong><small>{c.format === 'docx' ? 'Word 中仍保留可接受、可拒绝的修订；请在分享前复核。' : '文字修改稿不是 Word 修订文件；请在分享前对照原合同复核。'}</small></div><div className="lv-actions"><button className="lv-secondary" disabled={s.busy} onClick={() => void this.run(() => this.download('md'))}><Icon name="download" />导出审查报告</button><button className="lv-primary" disabled={s.busy || !r?.draft_approval || !accepted} onClick={() => void this.run(() => this.download(c.format === 'docx' ? 'docx' : 'txt'))}>{c.format === 'docx' ? '导出 Word 修订稿' : '导出文字修改稿'}<Icon name="download" /></button></div></footer>}
              <p className="lv-conversation-note">AI 辅助审查，不替代法律意见。原文匹配不代表法条版本和适用性已核实。</p>
            </div></main>
            {s.showDocument && <section className="lv-document" aria-label="脱敏合同正文"><header><div><Icon name="document" /><strong>合同正文</strong><small>脱敏视图</small></div><button className="lv-icon" aria-label="关闭原文面板" onClick={() => this.setState({ showDocument: false }, () => document.getElementById('legal-main')?.focus())}><Icon name="close" /></button></header><label className="lv-document-search"><Icon name="search" /><input aria-label="查找合同正文" placeholder="查找正文内容" value={s.documentQuery} onChange={e => this.setState({ documentQuery: e.target.value })} /><span>{visibleBlocks.length} / {blocks.length} 段</span></label><div className="lv-document-scroll"><article className="lv-paper"><h2>{c.name.replace(/\.[^.]+$/, '')}</h2>{visibleBlocks.map(b => { const count = r?.findings.filter(f => f.block_id === b.id && findingStatus(f) !== 'rejected').length || 0; return <button id={`legal-block-${b.id}`} key={b.id} className={`lv-paragraph ${s.selectedBlock === b.id ? 'focused' : ''} ${count ? 'has-findings' : ''}`} onClick={() => { const finding = r?.findings.find(f => f.block_id === b.id && findingStatus(f) !== 'rejected'); this.setState(state => ({ selectedBlock: b.id, filter: finding ? 'all' : state.filter, statusFilter: finding ? 'all' : state.statusFilter, resultQuery: finding ? '' : state.resultQuery, showDocument: finding ? window.matchMedia('(min-width: 1100px)').matches : state.showDocument }), () => { if (finding) { const el = document.getElementById(`legal-finding-${finding.id}`); el?.scrollIntoView({ block: 'center', behavior: 'auto' }); el?.focus({ preventScroll: true }); } }); }}><small>{b.id}{b.page ? ` · 第 ${b.page} 页` : ''}{count > 0 && <b>{count} 项意见 · 查看</b>}</small><span>{b.text}</span>{s.originalBlocks && <span className="lv-original-comparison"><strong>上传原文（未外发）</strong>{s.originalBlocks.find(original => original.id === b.id)?.text || '未匹配原文'}</span>}</button>; })}{!visibleBlocks.length && <p className="lv-empty-result">正文中未找到匹配内容。</p>}</article></div><footer><Icon name="lock" />此处原件对照仅供人工检查，不进入审查模型请求。修订导出会恢复真实信息。</footer></section>}
          </div></>}
      </div>
      {s.pendingFile && <ConfirmDialog title="上传前，确认这份原件的处理方式" confirmLabel="确认授权并上传" busy={s.busy}
        onCancel={() => this.setState({ pendingFile: null, error: '' })} onConfirm={() => void this.run(() => this.upload(s.pendingFile || undefined))}>
        <div className="lv-upload-file"><Icon name="file" /><span>{s.pendingFile.name}<small>{(s.pendingFile.size / 1024).toFixed(1)} KB</small></span></div>
        <p>{s.caps?.upload_disclosure?.notice}</p><p>存储地域（运营方声明，未独立核验）：<strong>{s.caps?.upload_disclosure?.storage_region}</strong></p>
        <p className="lv-inline-warning">这是上传原件的授权，不是向模型发送合同的授权。审查前仍需检查脱敏并另行确认。</p>{s.error && <p role="alert" className="lv-inline-warning">{s.error}</p>}
      </ConfirmDialog>}
      {s.confirmingRedaction && <ConfirmDialog title="确认已检查脱敏内容？" confirmLabel="确认脱敏并继续" busy={s.busy}
        onCancel={() => this.setState({ confirmingRedaction: false, error: '' })} onConfirm={() => void this.run(() => this.redact(true))}>
        <p>请确认主体、联系人和账户等敏感内容已按需隐藏，交易金额与期限等审查信息仍然可读。</p><p className="lv-inline-warning">确认后，本版本的脱敏映射不能更改。模型外发需要在下一步另行授权。</p>{s.error && <p role="alert">{s.error}</p>}
      </ConfirmDialog>}
      {s.exportFormat && <ConfirmDialog title="导出前，检查文件中的敏感信息" confirmLabel="确认并导出修订稿" busy={s.busy}
        onCancel={() => this.setState({ exportFormat: null, error: '' })} onConfirm={() => { const format = s.exportFormat; if (format) void this.run(() => this.download(format, true)); }}>
        <p>这份修订稿包含真实信息和删除内容，不是脱敏副本。请确认接收人和分享范围，避免将原件中的隐私继续传播。</p>
        <p>导出不会自动签署合同，也不会覆盖你的原文件。</p>{s.error && <p role="alert">{s.error}</p>}
      </ConfirmDialog>}
      {s.archivePolicy && <ConfirmDialog title="归档这条公司规范？" confirmLabel="确认归档" busy={s.busy}
        onCancel={() => this.setState({ archivePolicy: null, error: '' })} onConfirm={() => void this.run(async () => {
          const policy = this.state.archivePolicy; const workspace = this.state.workspace; if (!policy || !workspace) return;
          await this.api(`/legal/policies/${policy.id}?org_id=${encodeURIComponent(workspace.org_id)}&version=${policy.version}`, { method: 'DELETE' });
          if (this.live) this.setState({ archivePolicy: null, notice: '规范已归档；既有报告仍保留当时的规范版本。' });
          await this.refreshList(workspace);
        })}>
        <p>“{s.archivePolicy.title}”将不再用于新审查。已有审查保留原版本，不会被改写。</p>{s.error && <p role="alert">{s.error}</p>}
      </ConfirmDialog>}
    </div>;
  }
}
