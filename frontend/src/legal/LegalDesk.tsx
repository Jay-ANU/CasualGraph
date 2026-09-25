import React from 'react';
import { AlertCircle, ArrowRight, Check, ChevronDown, FileText, Home, Menu, PanelRight, SlidersHorizontal, X } from 'lucide-react';
import { apiFetch, jsonRequest, readApiError, withAuth } from '../api/client';
import { apiBase } from '../api/config';
import type { Answer, Api, Block, Capabilities, Catalog, Contract, ContractSummary, Decision, Finding, Matter, Policy, Review, User, Workspace } from './types';
import './LegalDesk.css';
import { findingCounts, findingStatus } from './findingStatus';
import { pendingDecisions, uploadIssue, visibleFindings } from './deskLogic';
import { emptyTransactionInputs, transactionAmount } from './transactionInput';
import { changeScenario, currentScenario, scenarioRoleValid } from './scenarioInput';
import { CONTRACT_STATUS, REVIEW_STATUS, STEPS, fileTitle } from './labels';
import { ReviewReport } from './report';
import { ConfirmDialog, Spinner } from './ui';
import { ic } from './icon';
import { Sidebar } from './Sidebar';
import { Welcome } from './Welcome';
import { RedactionStep } from './RedactionStep';
import { SetupForm } from './SetupForm';
import type { SetupValues } from './SetupForm';
import { ReviewIssue, ReviewProgress, ReviewSummary } from './ReviewStatus';
import { FindingList } from './FindingList';
import { ReviewDetails } from './ReviewDetails';
import { FollowUp } from './FollowUp';
import { ReleasePanel } from './ReleasePanel';
import { DocumentPane } from './DocumentPane';
import { PolicyEditor } from './PolicyEditor';

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
const errorText = (e: unknown) => e instanceof Error ? e.message : '操作没有完成，请重试。';
const wide = () => window.matchMedia('(min-width: 1100px)').matches;
const motion = (): ScrollBehavior => window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth';

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
      const deny = () => this.setState({ denied: true, contract: null, review: null, policies: [], contracts: [], answers: [], originalBlocks: null });
      void this.api<{ allowed: boolean }>('/legal/access').then(a => { if (this.live && !a.allowed) deny(); })
        .catch(() => { if (this.live) deny(); });
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
    this.setState({ exportFormat: null, pendingFile: null, confirmingRedaction: false, resultQuery: '', documentQuery: '', filter: 'all', statusFilter: 'all',
      contractType: '采购合同', ourRole: '', originalBlocks: null, ourPartyBlock: '', ourPartyQuote: '', excludedTerms: '', contract: null, review: null,
      preview: null, terms: '', consent: false, selectedBlock: null, instructions: '', date: '', performanceStage: '未知', attachmentsStatus: '未知',
      businessPriority: '综合审查', dealValue: '', currency: 'CNY', question: '', answers: [], showDocument: false, setupOpen: true,
      tab: 'review', error: '', notice: '', mobileMenu: false, questionConsent: false }, () => {
      document.querySelector<HTMLButtonElement>('[aria-label="选择一份合同开始"]')?.focus();
    });
    history.replaceState(null, '', '/legal');
  };
  private openContract = async (id: string) => {
    const seq = ++this.generation;
    this.setState({ exportFormat: null, pendingFile: null, confirmingRedaction: false, resultQuery: '', documentQuery: '', filter: 'all', statusFilter: 'all',
      ...emptyTransactionInputs(), contractType: '采购合同', date: '', ourRole: '', instructions: '', originalBlocks: null, ourPartyBlock: '', ourPartyQuote: '',
      excludedTerms: '', review: null, preview: null, terms: '', consent: false, selectedBlock: null, answers: [], question: '', questionConsent: false });
    const contract = await this.api<Contract>(`/legal/contracts/${id}`);
    if (!this.live || seq !== this.generation) return;
    this.setState({ contract, tab: 'review', showDocument: wide(), mobileMenu: false });
    history.replaceState(null, '', `/legal?contract=${encodeURIComponent(id)}`);
    if (contract.reviews.length) {
      const review = await this.api<Review>(`/legal/reviews/${contract.reviews[0].id}`);
      if (!this.live || seq !== this.generation) return;
      const context = review.profile?.transaction_context;
      this.setState({ review, setupOpen: false, ourRole: review.profile?.our_role || '',
        ourPartyBlock: review.profile?.our_party?.block_id || '', ourPartyQuote: review.profile?.our_party?.quote || '',
        contractType: review.profile?.contract_type || '采购合同', instructions: review.profile?.instructions || '',
        reviewMode: review.profile?.review_mode || 'standard', date: review.profile?.transaction_date || '',
        performanceStage: context?.performance_stage || '未知', attachmentsStatus: context?.attachments_status || '未知',
        businessPriority: context?.business_priority || '综合审查', dealValue: context?.deal_value == null ? '' : String(context.deal_value),
        currency: context?.currency || 'CNY' });
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
      this.setState({ error: '服务端暂不支持原件上传说明，请稍后再试。' }); return;
    }
    this.setState({ pendingFile: file, error: '' });
  };
  private upload = async (file?: File) => {
    if (!file || !this.state.workspace) return;
    const problem = uploadIssue(file);
    if (problem) throw new Error(problem);
    if (!this.state.caps?.encryption_configured) throw new Error('安全存储尚未就绪，合同没有上传。');
    const disclosure = this.state.caps?.upload_disclosure;
    if (!disclosure) throw new Error('服务端暂不支持原件上传说明，请稍后再试。');
    const workspace = this.state.workspace;
    const contractType = !this.state.contract && currentScenario(this.state.caps?.scenario_catalog, this.state.contractType) ? this.state.contractType : '采购合同';
    const form = new FormData(); form.set('matter_id', workspace.matter_id); form.set('file', file); form.set('original_upload_confirmed', 'true'); form.set('upload_notice_version', disclosure.version);
    const contract = await this.api<Contract>('/legal/contracts', { method: 'POST', body: form });
    if (!this.live) return;
    this.generation++;
    this.setState({ pendingFile: null, resultQuery: '', documentQuery: '', filter: 'all', statusFilter: 'all', ...emptyTransactionInputs(), date: '', ourRole: '',
      instructions: this.state.contract ? '' : this.state.instructions, contractType, originalBlocks: null, ourPartyBlock: '', ourPartyQuote: '', excludedTerms: '',
      contract, review: null, preview: null, terms: '', consent: false, selectedBlock: null,
      answers: [], question: '', showDocument: wide(), setupOpen: true, tab: 'review', questionConsent: false });
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
      if (this.live) this.setState({ contract, confirmingRedaction: false, originalBlocks: null, showDocument: wide(), notice: '脱敏已确认。下一步：说明你的立场。' });
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
    if (this.live) this.setState({ review, setupOpen: false, answers: [], question: '', questionConsent: false }, () => document.getElementById('legal-main')?.scrollTo({ top: 0, behavior: motion() }));
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
      document.getElementById(`legal-block-${id}`)?.scrollIntoView({ block: 'center', behavior: motion() });
    });
  };
  /** Clicking a paragraph with open findings jumps to the first one. */
  private selectParagraph = (block: Block) => {
    const finding = this.state.review?.findings.find(f => f.block_id === block.id && findingStatus(f) !== 'rejected');
    this.setState(state => ({ selectedBlock: block.id, filter: finding ? 'all' : state.filter, statusFilter: finding ? 'all' : state.statusFilter,
      resultQuery: finding ? '' : state.resultQuery, showDocument: finding ? wide() : state.showDocument }), () => {
      if (!finding) return;
      const el = document.getElementById(`legal-finding-${finding.id}`);
      el?.scrollIntoView({ block: 'center', behavior: 'auto' }); el?.focus({ preventScroll: true });
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
      if (data.id !== r.id) throw new Error('报告与本轮审查不一致，请刷新页面。');
      blob = new Blob([ReviewReport(data)], { type: 'text/markdown;charset=utf-8' });
    } else blob = await response.blob();
    const url = URL.createObjectURL(blob), a = document.createElement('a');
    a.href = url; a.download = `${format === 'md' ? '合同审查报告' : format === 'docx' ? '合同修订稿（含修订痕迹）' : '合同文字修改稿'}.${format}`;
    document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 2000);
    if (this.live) this.setState({ exportFormat: null, notice: format === 'md' ? '审查报告已导出。' : format === 'docx' ? '修订稿已导出。请在 Word 的“审阅”中逐项确认。' : '文字修改稿已导出。它不含 Word 修订标记，请对照原合同复核。' });
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
  /** Any change to what is sent withdraws the model-processing consent. */
  private changeSetup = (patch: Partial<SetupValues>) => this.setState({ ...patch, consent: false } as Pick<State, keyof SetupValues>);
  private changeType = (type: string) => {
    try { this.setState(changeScenario(this.state.caps?.scenario_catalog, type)); }
    catch (e) { this.setState({ error: errorText(e) }); }
  };
  private reviewAction = (path: 'cancel' | 'resume') => void this.run(async () => {
    const r = this.state.review; if (!r) return;
    const review = await this.api<Review>(`/legal/reviews/${r.id}/${path}`, { method: 'POST' });
    if (this.live) this.setState({ review });
  });

  private renderWorkspace(c: Contract) {
    const s = this.state, r = s.review;
    const active = Boolean(r && ['queued', 'running'].includes(r.status));
    const done = Boolean(r && ['completed', 'partial'].includes(r.status));
    const scenarioValid = scenarioRoleValid(s.caps?.scenario_catalog, s.contractType, s.ourRole);
    const partyValid = s.ourPartyQuote.trim().length >= 2 && !!c.blocks.find(b => b.id === s.ourPartyBlock)?.text.includes(s.ourPartyQuote);
    const amountValid = transactionAmount(s.dealValue).valid;
    const blocks = s.preview || c.blocks;
    const query = s.documentQuery.trim().toLocaleLowerCase();
    const visibleBlocks = blocks.filter(block => block.text.toLocaleLowerCase().includes(query));
    const startIssue = c.redaction_version !== 2 ? '这份合同需要重新上传，并确认新版脱敏。'
      : !scenarioValid ? '请先选择合同类型和你的角色。'
      : !partyValid ? '请确认合同中代表你的主体。'
      : !amountValid ? '请修正交易金额，或者留空。'
      : s.modelsLoading ? '正在读取可用模型…'
      : !s.modelId || s.caps?.model_configured === false ? '暂时没有可用的审查模型，请刷新模型列表。'
      : !s.consent ? '最后，请勾选同意发送给 AI 模型。' : '';
    const canStart = !(s.busy || active || s.modelsLoading || !s.consent || !s.modelId || !scenarioValid || !partyValid || !amountValid || c.redaction_version !== 2 || s.caps?.model_configured === false);
    const values: SetupValues = { contractType: s.contractType, ourRole: s.ourRole, ourPartyBlock: s.ourPartyBlock, ourPartyQuote: s.ourPartyQuote,
      instructions: s.instructions, performanceStage: s.performanceStage, attachmentsStatus: s.attachmentsStatus, businessPriority: s.businessPriority,
      dealValue: s.dealValue, currency: s.currency, date: s.date, reviewMode: s.reviewMode, modelId: s.modelId, consent: s.consent };
    const setup = <SetupForm contract={c} caps={s.caps} catalog={s.catalog} values={values} hasReview={Boolean(r)} busy={s.busy} locked={active}
      modelsLoading={s.modelsLoading} scenarioValid={scenarioValid} partyValid={partyValid} canStart={canStart} startIssue={startIssue}
      onType={this.changeType} onChange={this.changeSetup} onConsent={consent => this.setState({ consent })}
      onRefreshModels={() => void this.loadModels()} onStart={() => void this.run(this.start)} />;
    const scrollTo = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: motion(), block: 'start' });
    const focusStatus = (statusFilter: string) => this.setState({ statusFilter, filter: 'all', resultQuery: '' }, () => scrollTo('legal-results'));
    const counts = r ? findingCounts(r.findings) : null;
    const handled = r && counts ? counts.actionable - pendingDecisions(r) : 0;
    const step = c.status === 'redaction_pending' ? 0 : !r ? 1 : r.draft_approval ? 3 : 2;
    return <>
      <div className="lv-stepbar">
        <nav className="lv-steps" aria-label="合同审查步骤"><ol>{STEPS.map((label, index) =>
          <li key={label} className={index === step ? 'current' : index < step ? 'complete' : ''} aria-current={index === step ? 'step' : undefined}>
            <span className="lv-step-dot">{index < step ? <Check {...ic} size={12} strokeWidth={2.5} /> : index + 1}</span><span className="lv-step-label">{label}</span>
          </li>)}</ol></nav>
        <div className="lv-view-switch" role="group" aria-label="工作区视图">
          <button aria-pressed={!s.showDocument} onClick={() => this.setState({ showDocument: false })}>审查</button>
          <button aria-pressed={s.showDocument} onClick={() => this.setState({ showDocument: true })}>合同正文</button>
        </div>
      </div>
      <div className={`lv-workbench ${s.showDocument ? 'with-document' : ''}`}>
        <main id="legal-main" tabIndex={-1} className="lv-work" aria-label="合同审查工作区">
          <div className="lv-work-inner">
            {c.status === 'ready' && c.redaction_version !== 2 && <p className="lv-note is-warn">这份合同使用的是旧版脱敏。历史报告仍可查看；如需指定我方主体和导出修订稿，请新建审查并重新上传。</p>}
            {c.warnings.length > 0 && <details className="lv-disclosure lv-parse-note"><summary>文档解析提示 · {c.warnings.length} 项</summary>
              <div className="lv-disclosure-body">{c.warnings.map((w, i) => <p key={i}>{w}</p>)}</div></details>}
            {c.status === 'redaction_pending' ? <RedactionStep contract={c} busy={s.busy} comparing={Boolean(s.originalBlocks)} showingDocument={s.showDocument}
              terms={s.terms} excludedTerms={s.excludedTerms} onShowDocument={() => this.setState({ showDocument: true })}
              onCompare={() => void this.run(this.showOriginal)} onTerms={terms => this.setState({ terms, preview: null })}
              onExcluded={excludedTerms => this.setState({ excludedTerms, preview: null })} onPreview={() => void this.run(() => this.redact(false))}
              onConfirm={() => this.setState({ confirmingRedaction: true, error: '' })} />
            : !r ? <section className="lv-stage" aria-labelledby="legal-setup-title">
              <h2 id="legal-setup-title">说明你的立场</h2>
              <p className="lv-stage-lede">审查会站在你这一方，找出对你不利的条款，并给出修改建议。</p>
              {setup}
            </section>
            : <>
              {active && <ReviewProgress review={r} canCancel={(s.caps?.review_engine_version || 0) >= 2} busy={s.busy} onCancel={() => this.reviewAction('cancel')} />}
              {done && <ReviewSummary review={r} onPending={() => focusStatus('pending')} onUnconfirmed={() => focusStatus('unconfirmed')} onExport={() => scrollTo('legal-release')} />}
              {(r.error || r.resumable || ['failed', 'cancelled'].includes(r.status)) && <ReviewIssue review={r} busy={s.busy} onResume={() => this.reviewAction('resume')} />}
              <section className="lv-settings" aria-label="审查设置">
                <button className="lv-settings-toggle" aria-expanded={s.setupOpen} aria-controls="legal-setup-body" onClick={() => this.setState({ setupOpen: !s.setupOpen })}>
                  <SlidersHorizontal {...ic} /><span className="lv-settings-title">本轮审查设置</span>
                  <span className="lv-settings-summary">{[s.contractType, s.ourRole && `我方：${s.ourRole}`, s.reviewMode === 'multi_agent' ? '深度审查' : '标准审查', r.profile?.model?.id || s.modelId].filter(Boolean).join(' · ')}</span>
                  <ChevronDown {...ic} />
                </button>
                {s.setupOpen && <div className="lv-settings-body" id="legal-setup-body">{setup}</div>}
              </section>
              {(r.findings.length > 0 || done) && <FindingList review={r} findings={visibleFindings(r, s.filter, s.statusFilter, s.resultQuery)} blocks={blocks} busy={s.busy} active={active}
                kind={s.filter} status={s.statusFilter} query={s.resultQuery}
                onKind={filter => this.setState({ filter })} onStatus={statusFilter => this.setState({ statusFilter })} onQuery={resultQuery => this.setState({ resultQuery })}
                onClear={() => this.setState({ resultQuery: '', filter: 'all', statusFilter: 'all' })} onLocate={this.locate}
                onDecision={(f, value, text, legalBasis, manual) => void this.run(() => this.decide(f, value, text, legalBasis, manual))} />}
              <ReviewDetails review={r} blocks={blocks} active={active} onLocate={this.locate} />
              {done && s.caps?.followup_questions && <FollowUp review={r} blocks={blocks} answers={s.answers} question={s.question} busy={s.questionBusy}
                consent={s.questionConsent} onQuestion={question => this.setState({ question })} onConsent={questionConsent => this.setState({ questionConsent })}
                onAsk={() => void this.ask()} onLocate={this.locate} />}
              {done && <ReleasePanel review={r} contract={c} busy={s.busy}
                onCheck={() => void this.run(async () => {
                  const review = await this.api<Review>(`/legal/reviews/${r.id}/draft-check`, jsonRequest('POST', { request_id: crypto.randomUUID(), external_processing_confirmed: true }));
                  if (this.live && this.state.review?.id === review.id) this.setState({ review });
                })}
                onApprove={fingerprint => void this.run(async () => {
                  const review = await this.api<Review>(`/legal/reviews/${r.id}/draft-approval`, jsonRequest('POST', { fingerprint, confirmed: true }));
                  if (this.live && this.state.review?.id === review.id) this.setState({ review });
                })}
                onReport={() => void this.run(() => this.download('md'))}
                onDraft={() => void this.run(() => this.download(c.format === 'docx' ? 'docx' : 'txt'))} />}
            </>}
            <p className="lv-footnote">AI 辅助审查，不构成法律意见。引用的法条请核实版本和适用范围。</p>
          </div>
          {done && counts && counts.actionable > 0 && <div className="lv-dock" role="region" aria-label="处理进度">
            <span className="lv-dock-text"><strong>{handled}</strong> / {counts.actionable} 项已处理</span>
            <span className="lv-dock-bar" aria-hidden="true"><i style={{ width: `${Math.round((handled / counts.actionable) * 100)}%` }} /></span>
            <button className="lv-secondary lv-btn-sm" onClick={() => scrollTo('legal-release')}>去导出<ArrowRight {...ic} size={14} /></button>
          </div>}
        </main>
        {s.showDocument && <DocumentPane contract={c} review={r} blocks={blocks} visibleBlocks={visibleBlocks} query={s.documentQuery}
          selectedBlock={s.selectedBlock} originalBlocks={s.originalBlocks} onQuery={documentQuery => this.setState({ documentQuery })}
          onClose={() => this.setState({ showDocument: false }, () => document.getElementById('legal-main')?.focus())} onParagraph={this.selectParagraph} />}
      </div>
    </>;
  }

  render() {
    const s = this.state, c = s.contract, r = s.review;
    const canUpload = Boolean(s.workspace && s.caps?.encryption_configured && !s.busy && !s.loading);
    const dialogOpen = Boolean(s.pendingFile || s.confirmingRedaction || s.archivePolicy || s.exportFormat);
    const statusKey = r ? r.status : c?.status || '';
    const statusTone = ({ redaction_pending: 'is-mid', running: 'is-low', queued: 'is-low', completed: 'is-ink', partial: 'is-mid', failed: 'is-high', cancelled: 'is-high' } as Record<string, string>)[statusKey] || '';
    if (s.denied) return <div className="legal-v2"><main className="lv-denied">
      <img src="/brand/logo-mark.svg" alt="" width={32} height={32} />
      <h1>合同审查仅向 Max 会员开放</h1><p>当前账户的会员状态已变化，合同内容已从页面移除。</p>
      <a className="lv-primary" href="/agent">返回研究工作台</a>
    </main></div>;
    return <div className={`legal-v2 ${s.mobileMenu ? 'lv-menu-open' : ''}`}>
      <a className="lv-skip" href="#legal-main">跳到工作区</a>
      {s.mobileMenu && <button className="lv-backdrop" aria-label="关闭侧栏" onClick={this.toggleMenu} />}
      <Sidebar open={s.mobileMenu} busy={s.busy} loading={s.loading} tab={s.tab} user={this.props.user} matters={s.matters} workspace={s.workspace}
        contracts={s.contracts} currentId={c?.id} policyCount={s.policies.length} query={s.historyQuery} onQuery={historyQuery => this.setState({ historyQuery })}
        onNew={this.clear} onTab={tab => this.setState({ tab, mobileMenu: false })} onOpen={id => void this.run(() => this.openContract(id))}
        onMatter={id => {
          const m = s.matters.find(x => x.id === id); if (!m) return;
          void this.run(async () => { this.clear(); const workspace = { matter_id: m.id, org_id: m.org_id }; this.setState({ workspace }); await this.refreshList(workspace); });
        }}
        onClose={this.toggleMenu} onLogout={this.props.logout} onKeyDown={this.menuKey} />
      <div className="lv-main-shell" ref={el => { if (el) el.inert = s.mobileMenu; }}>
        <header className="lv-topbar">
          <button className="lv-icon lv-mobile-only" onClick={this.toggleMenu} aria-label="打开导航"><Menu {...ic} size={20} /></button>
          {c && s.tab === 'review' ? <div className="lv-title">
            <h1>{fileTitle(c.name)}</h1>
            <span className="lv-title-meta">{c.format.toUpperCase()} · {c.blocks.length} 段</span>
            <span className={`lv-chip ${statusTone}`}>{(r ? REVIEW_STATUS[r.status] : CONTRACT_STATUS[c.status]) || statusKey}</span>
          </div> : <div className="lv-title"><span className="lv-title-plain">{s.tab === 'policies' ? '公司规范' : '合同审查'}</span></div>}
          <div className="lv-top-actions">
            {c && s.tab === 'review' && <button className="lv-quiet lv-doc-toggle" aria-pressed={s.showDocument} onClick={() => this.setState({ showDocument: !s.showDocument })}><PanelRight {...ic} />{s.showDocument ? '收起正文' : '查看正文'}</button>}
            <a href="/" className="lv-icon" aria-label="返回网站首页"><Home {...ic} size={18} /></a>
          </div>
        </header>
        {s.error && !dialogOpen && <div className="lv-banner lv-error" role="alert"><AlertCircle {...ic} /><span>{s.error}</span><button className="lv-icon" aria-label="关闭错误" onClick={() => this.setState({ error: '' })}><X {...ic} /></button></div>}
        {s.notice && <div className="lv-banner lv-notice" role="status"><Check {...ic} /><span>{s.notice}</span><button className="lv-icon" aria-label="关闭提示" onClick={() => this.setState({ notice: '' })}><X {...ic} /></button></div>}
        {s.caps && !s.caps.encryption_configured && <div className="lv-banner lv-warning"><AlertCircle {...ic} /><span>安全存储尚未配置，暂时不能上传合同。请联系管理员；系统不会跳过加密上传。</span></div>}
        {s.modelError && <div className="lv-banner lv-warning"><AlertCircle {...ic} /><span>{s.modelError}</span><button className="lv-text-button" onClick={() => void this.loadModels()}>重新读取模型</button></div>}
        <input ref={el => { this.uploadInput = el; }} type="file" accept=".docx,.pdf,.txt" hidden onChange={e => { const file = e.target.files?.[0]; e.target.value = ''; this.queueUpload(file); }} />
        {s.loading ? <main className="lv-loading" role="status"><Spinner />正在打开工作空间…</main>
          : !s.workspace ? <main id="legal-main" className="lv-loading"><AlertCircle {...ic} size={22} /><h1>暂时打不开工作空间</h1>
            <p>合同没有上传。请检查网络后重试，不需要重新选择文件。</p><button className="lv-primary" onClick={() => void this.initialize()}>重新打开</button></main>
          : s.tab === 'policies' ? <PolicyEditor catalog={s.caps?.scenario_catalog} policies={s.policies} busy={s.busy}
            onSave={(draft, existing) => void this.run(async () => {
              if (!s.workspace) return;
              await this.api(`/legal/policies${existing ? `/${existing.id}` : ''}?org_id=${encodeURIComponent(s.workspace.org_id)}`, jsonRequest(existing ? 'PUT' : 'POST', { ...draft, version: existing?.version }));
              await this.refreshList(s.workspace);
            })} onArchive={policy => this.setState({ archivePolicy: policy, error: '' })} />
          : !c ? <Welcome caps={s.caps} disabled={!canUpload} instructions={s.instructions} contractType={s.contractType}
            onUpload={() => this.uploadInput?.click()} onDrop={files => {
              if (files.length !== 1) { this.setState({ error: '请一次上传一份合同。' }); return; }
              this.queueUpload(files[0]);
            }} onInstructions={instructions => this.setState({ instructions, consent: false })} onScenario={this.changeType} />
          : this.renderWorkspace(c)}
      </div>
      {s.pendingFile && <ConfirmDialog title="上传前，确认这份原件的处理方式" confirmLabel="确认授权并上传" busy={s.busy}
        onCancel={() => this.setState({ pendingFile: null, error: '' })} onConfirm={() => void this.run(() => this.upload(s.pendingFile || undefined))}>
        <div className="lv-upload-file"><FileText {...ic} size={18} /><span>{s.pendingFile.name}<small>{(s.pendingFile.size / 1024).toFixed(1)} KB</small></span></div>
        <ul className="lv-dialog-points">
          <li>原件会上传到服务器，解析后加密保存，并在服务器上完成脱敏。</li>
          <li>这一步不会把合同发送给 AI 模型。开始审查前，还需要你单独同意。</li>
          <li>存储地域：<strong>{s.caps?.upload_disclosure?.storage_region}</strong>（运营方声明，未经独立核验）</li>
        </ul>
        <div className="lv-disclosure-text"><strong>处理说明全文</strong><p>{s.caps?.upload_disclosure?.notice}</p></div>
        {s.error && <p role="alert" className="lv-note is-error">{s.error}</p>}
      </ConfirmDialog>}
      {s.confirmingRedaction && <ConfirmDialog title="确认已检查脱敏内容？" confirmLabel="确认脱敏并继续" busy={s.busy}
        onCancel={() => this.setState({ confirmingRedaction: false, error: '' })} onConfirm={() => void this.run(() => this.redact(true))}>
        <p>请确认公司名称、联系人和账户等敏感信息已按需隐藏，交易金额、期限等审查需要的信息仍然可读。</p>
        <p className="lv-note">确认后，这一版的脱敏结果不能再修改。发送给 AI 模型之前，下一步还会单独征求你的同意。</p>
        {s.error && <p role="alert" className="lv-note is-error">{s.error}</p>}
      </ConfirmDialog>}
      {s.exportFormat && <ConfirmDialog title="导出前，检查文件中的敏感信息" confirmLabel="确认并导出修订稿" busy={s.busy}
        onCancel={() => this.setState({ exportFormat: null, error: '' })} onConfirm={() => { const format = s.exportFormat; if (format) void this.run(() => this.download(format, true)); }}>
        <p>这份修订稿包含真实信息和被删除的内容，不是脱敏副本。请确认接收人和分享范围，避免原件中的隐私继续传播。</p>
        <p>导出不会签署合同，也不会覆盖你的原文件。</p>
        {s.error && <p role="alert" className="lv-note is-error">{s.error}</p>}
      </ConfirmDialog>}
      {s.archivePolicy && <ConfirmDialog title="归档这条公司规范？" confirmLabel="确认归档" busy={s.busy}
        onCancel={() => this.setState({ archivePolicy: null, error: '' })} onConfirm={() => void this.run(async () => {
          const policy = this.state.archivePolicy; const workspace = this.state.workspace; if (!policy || !workspace) return;
          await this.api(`/legal/policies/${policy.id}?org_id=${encodeURIComponent(workspace.org_id)}&version=${policy.version}`, { method: 'DELETE' });
          if (this.live) this.setState({ archivePolicy: null, notice: '规范已归档。已完成的审查仍保留当时的版本。' });
          await this.refreshList(workspace);
        })}>
        <p>“{s.archivePolicy.title}”将不再用于新的审查。已完成的审查保留当时的版本，不会被改写。</p>
        {s.error && <p role="alert" className="lv-note is-error">{s.error}</p>}
      </ConfirmDialog>}
    </div>;
  }
}
