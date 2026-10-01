import React from 'react';
import { AlertCircle, FileText, Lock, X } from 'lucide-react';
import { apiFetch, jsonRequest, readApiError, withAuth } from '../api/client';
import { apiBase } from '../api/config';
import type { Answer, Api, Block, Capabilities, Catalog, Contract, ContractSummary, Decision, Finding, Matter, Policy, Review, ReviewTier, User, Workspace } from './types';
import './LegalDesk.css';
import '@fontsource-variable/inter/wght.css';
import { uploadIssue } from './deskLogic';
import { emptyTransactionInputs, transactionAmount } from './transactionInput';
import { changeScenario, currentScenario, scenarioRoleValid } from './scenarioInput';
import { fileTitle, tierLabel, tierOf } from './labels';
import { partyCandidates } from './text';
import { ReviewReport } from './report';
import type { DeskView, Stage, ToneFilter } from './workspace';
import { clauseOutline, deskStage, filterByTone, isActive, isDone, isRevised, nextUndecided, numberFindings, pagesOf, placeLabel,
  redactionTokens, stepLabels, stepOf } from './workspace';
import { currentLang, I18nContext, pick, tr } from '../i18n/core';
import { labelOf, plural, serverText, type Pair } from './i18n';
import { ConfirmDialog, Toast } from './ui';
import { ic } from './icon';
import { TopBar } from './TopBar';
import type { Step } from './TopBar';
import { Library } from './Library';
import { Outline } from './Outline';
import { Paper } from './Paper';
import { RedactionPanel } from './RedactionPanel';
import { SetupForm } from './SetupForm';
import type { SetupValues } from './SetupForm';
import { ReviewProgress } from './ReviewStatus';
import { ResultsPanel } from './ResultsPanel';
import type { RailTab } from './ResultsPanel';
import { ReleasePanel } from './ReleasePanel';
import { PolicyEditor } from './PolicyEditor';

type Props = { user: User | null; logout: () => void; request?: Api };
type State = {
  workspace: Workspace | null; matters: Matter[]; contracts: ContractSummary[]; contract: Contract | null;
  review: Review | null; policies: Policy[]; caps: Capabilities | null; catalog: Catalog | null;
  busy: boolean; loading: boolean; error: string; modelError: string; modelsLoading: boolean;
  tab: 'review' | 'policies'; view: DeskView; pane: 'rail' | 'paper'; railTab: RailTab; tone: ToneFilter;
  selected: string | null; located: { id: string; n: number } | null;
  ourRole: string; contractType: string; date: string; instructions: string; consent: boolean; modelId: string;
  terms: string; preview: Block[] | null; libraryQuery: string; question: string; answers: Answer[]; questionBusy: boolean; questionConsent: boolean;
  ourPartyBlock: string; ourPartyQuote: string; excludedTerms: string; originalBlocks: Block[] | null;
  notice: string; hint: string; denied: boolean; reviewTier: ReviewTier;
  performanceStage: string; attachmentsStatus: string; businessPriority: string; dealValue: string; currency: string;
  exportFormat: 'docx' | 'txt' | null; pendingFile: File | null; confirmingRedaction: boolean; archivePolicy: Policy | null;
};
/**
 * Errors and notices are kept as the Chinese the desk or the service wrote and translated
 * with tr() when shown, so a language switch also rewrites a message already on screen.
 */
const errorText = (e: unknown) => e instanceof Error ? e.message : '操作没有完成，请重试。';
const motion = (): ScrollBehavior => window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth';
const RAIL_LABEL: Record<Stage, Pair> = {
  redaction: ['脱敏核对', 'Redaction check'], setup: ['审查设置', 'Review settings'], running: ['审查进度', 'Review progress'], results: ['批注', 'Notes'], export: ['导出', 'Export'],
};
const deskTitle = () => pick('合同审查 · CausalGraph', 'Contract review · CausalGraph');
/** Everything that belongs to one open contract; reset whenever another one opens. */
const freshContract = () => ({
  exportFormat: null, pendingFile: null, confirmingRedaction: false, originalBlocks: null, ourPartyBlock: '', ourPartyQuote: '', excludedTerms: '',
  review: null, preview: null, terms: '', consent: false, answers: [], question: '', questionConsent: false,
  view: 'work' as DeskView, pane: 'rail' as const, railTab: 'notes' as RailTab, tone: 'all' as ToneFilter, selected: null, located: null,
});

/** Own the desk's request lifecycle; test previews may inject a synthetic API. */
export default class LegalDesk extends React.Component<Props, State> {
  // Re-render on a language switch; copy is picked with pick()/tr() while rendering.
  static contextType = I18nContext;
  declare context: React.ContextType<typeof I18nContext>;
  state: State = { workspace: null, matters: [], contracts: [], contract: null, review: null, policies: [], caps: null, catalog: null,
    busy: false, loading: true, error: '', modelError: '', modelsLoading: false, tab: 'review', view: 'work', pane: 'rail', railTab: 'notes', tone: 'all',
    selected: null, located: null, ourRole: '', contractType: '采购合同', date: '', instructions: '', consent: false, modelId: '',
    terms: '', preview: null, libraryQuery: '', question: '', answers: [],
    ourPartyBlock: '', ourPartyQuote: '', excludedTerms: '', originalBlocks: null,
    questionBusy: false, questionConsent: false, notice: '', hint: '', denied: false, reviewTier: 'standard',
    performanceStage: '未知', attachmentsStatus: '未知', businessPriority: '综合审查', dealValue: '', currency: 'CNY',
    exportFormat: null, pendingFile: null, confirmingRedaction: false, archivePolicy: null };
  private live = false;
  private generation = 0;
  private operation = false;
  private polling = false;
  private modelGeneration = 0;
  private locateCount = 0;
  private timer?: ReturnType<typeof setInterval>;
  private priorTitle = '';
  private priorTheme = '';
  private uploadInput: HTMLInputElement | null = null;
  private api: Api = <T,>(path: string, init?: RequestInit) => (this.props.request || apiFetch)<T>(path, init);

  componentDidMount() {
    this.live = true;
    this.priorTitle = document.title;
    document.title = deskTitle();
    // White browser chrome on phones while the desk is open.
    const theme = document.querySelector('meta[name="theme-color"]');
    this.priorTheme = theme?.getAttribute('content') ?? '';
    theme?.setAttribute('content', '#ffffff');
    void this.initialize();
    this.timer = setInterval(() => void this.poll(), 2500);
    document.addEventListener('visibilitychange', this.refreshOnReturn);
  }
  componentDidUpdate() {
    const title = deskTitle();
    if (document.title !== title) document.title = title;
  }
  componentWillUnmount() {
    this.live = false; this.generation++; clearInterval(this.timer); document.title = this.priorTitle;
    if (this.priorTheme) document.querySelector('meta[name="theme-color"]')?.setAttribute('content', this.priorTheme);
    document.removeEventListener('visibilitychange', this.refreshOnReturn);
  }
  /** Background tabs throttle timers; catch up as soon as the page is visible again. */
  private refreshOnReturn = () => { if (document.visibilityState === 'visible') void this.poll(); };
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
    if (!r || !isActive(r) || this.polling) return;
    this.polling = true;
    const seq = this.generation;
    try {
      const updated = await this.api<Review>(`/legal/reviews/${r.id}`);
      if (this.live && seq === this.generation && this.state.review?.id === r.id) this.setState({ review: updated });
    } catch (e) { this.fail(e); }
    finally { this.polling = false; }
  }
  /** Back to the library: nothing of the previous contract stays in memory. */
  private clear = () => {
    this.generation++;
    this.setState({ ...freshContract(), ...emptyTransactionInputs(), contract: null, contractType: '采购合同', ourRole: '', instructions: '', date: '',
      tab: 'review', error: '', notice: '', hint: '', libraryQuery: '' }, () => {
      document.getElementById('legal-upload-button')?.focus();
    });
    history.replaceState(null, '', '/legal');
  };
  private openContract = async (id: string) => {
    const seq = ++this.generation;
    this.setState({ ...freshContract(), ...emptyTransactionInputs(), contractType: '采购合同', date: '', ourRole: '', instructions: '' });
    const contract = await this.api<Contract>(`/legal/contracts/${id}`);
    if (!this.live || seq !== this.generation) return;
    this.setState({ contract, tab: 'review' });
    history.replaceState(null, '', `/legal?contract=${encodeURIComponent(id)}`);
    if (contract.reviews.length) {
      const review = await this.api<Review>(`/legal/reviews/${contract.reviews[0].id}`);
      if (!this.live || seq !== this.generation) return;
      const context = review.profile?.transaction_context;
      this.setState({ review, ourRole: review.profile?.our_role || '',
        ourPartyBlock: review.profile?.our_party?.block_id || '', ourPartyQuote: review.profile?.our_party?.quote || '',
        contractType: review.profile?.contract_type || '采购合同', instructions: review.profile?.instructions || '',
        reviewTier: tierOf(review), date: review.profile?.transaction_date || '',
        performanceStage: context?.performance_stage || '未知', attachmentsStatus: context?.attachments_status || '未知',
        businessPriority: context?.business_priority || '综合审查', dealValue: context?.deal_value == null ? '' : String(context.deal_value),
        currency: context?.currency || 'CNY' });
      if (this.state.caps?.followup_questions) {
        const data = await this.api<{ messages: Answer[] }>(`/legal/reviews/${review.id}/questions`);
        if (this.live && seq === this.generation) this.setState({ answers: data.messages });
      }
    }
  };
  private queueUpload = (file?: File) => {
    if (!file || this.operation || this.state.loading) return;
    const problem = uploadIssue(file, 'zh');
    if (problem) { this.setState({ error: problem }); return; }
    if (!this.state.workspace || !this.state.caps?.encryption_configured) {
      this.setState({ error: '安全存储未就绪，请稍后重试。' }); return;
    }
    if (!this.state.caps.upload_disclosure) {
      this.setState({ error: '服务暂不可用，请稍后重试。' }); return;
    }
    this.setState({ pendingFile: file, error: '' });
  };
  private upload = async (file?: File) => {
    if (!file || !this.state.workspace) return;
    const problem = uploadIssue(file, 'zh');
    if (problem) throw new Error(problem);
    if (!this.state.caps?.encryption_configured) throw new Error('安全存储未就绪，请稍后重试。');
    const disclosure = this.state.caps?.upload_disclosure;
    if (!disclosure) throw new Error('服务暂不可用，请稍后重试。');
    const workspace = this.state.workspace;
    const contractType = !this.state.contract && currentScenario(this.state.caps?.scenario_catalog, this.state.contractType) ? this.state.contractType : '采购合同';
    const form = new FormData(); form.set('matter_id', workspace.matter_id); form.set('file', file); form.set('original_upload_confirmed', 'true'); form.set('upload_notice_version', disclosure.version);
    const contract = await this.api<Contract>('/legal/contracts', { method: 'POST', body: form });
    if (!this.live) return;
    this.generation++;
    this.setState({ ...freshContract(), ...emptyTransactionInputs(), date: '', ourRole: '', instructions: this.state.contract ? '' : this.state.instructions,
      contractType, contract, tab: 'review' });
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
      if (this.live) this.setState({ contract, confirmingRedaction: false, originalBlocks: null, preview: null, pane: 'rail', notice: '脱敏已确认' });
      if (this.state.workspace) await this.refreshList(this.state.workspace);
    }
  };
  private start = async () => {
    const s = this.state;
    if (!s.contract || !s.modelId || !s.consent || !s.ourRole || !s.ourPartyBlock || !s.ourPartyQuote) return;
    if (!scenarioRoleValid(s.caps?.scenario_catalog, s.contractType, s.ourRole)) throw new Error('请重新选择我方身份。');
    const amount = transactionAmount(s.dealValue);
    if (!amount.valid) throw new Error('交易金额格式有误。');
    const review = await this.api<Review>(`/legal/contracts/${s.contract.id}/reviews`, jsonRequest('POST', {
      model_id: s.modelId, external_processing_provider: 'ydata', external_processing_confirmed: true,
      scenario_revision: s.caps?.scenario_catalog?.revision,
      our_party: { block_id: s.ourPartyBlock, quote: s.ourPartyQuote }, our_role: s.ourRole, contract_type: s.contractType, jurisdiction: '中国大陆', transaction_date: s.date || null,
      transaction_context: { performance_stage: s.performanceStage, attachments_status: s.attachmentsStatus, business_priority: s.businessPriority,
        deal_value: amount.value, currency: s.currency },
      instructions: s.instructions, fresh_review: Boolean(s.review), review_tier: s.reviewTier, review_mode: s.reviewTier === 'deep' ? 'multi_agent' : 'standard',
    }));
    if (this.live) this.setState({ review, view: 'work', pane: 'rail', railTab: 'notes', tone: 'all', selected: null, located: null, answers: [], question: '', questionConsent: false });
  };
  /** Numbered findings of the open review, in reading order. */
  private numbered() {
    const c = this.state.contract, r = this.state.review;
    return c && r ? numberFindings(r.findings, c.blocks) : { open: [], excluded: [] };
  }
  private decide = async (f: Finding, value: string, replacement: string, legalBasis: boolean, manual: boolean) => {
    const r = this.state.review; if (!r) return;
    const decision = await this.api<Decision>(`/legal/reviews/${r.id}/findings/${f.id}`, jsonRequest('PATCH', {
      decision: value, text: replacement, expected_version: r.decisions[f.id]?.version || 0,
      legal_basis_confirmed: legalBasis, manual_edit_confirmed: manual,
    }));
    const current = this.state.review;
    if (!this.live || !current || current.id !== r.id) return;
    const decisions = { ...current.decisions, [f.id]: decision };
    this.setState(s => ({ review: s.review ? { ...s.review, draft_check: undefined, draft_approval: undefined, decisions } : null }), () => {
      // A decision moves on to the next finding still waiting, so the list can be worked top to bottom.
      if (value === 'pending') return;
      const ids = filterByTone(this.numbered().open, this.state.tone).map(x => x.finding.id);
      const next = nextUndecided(ids, decisions, f.id);
      if (next !== f.id) this.select(next);
    });
  };
  private showOriginal = async () => {
    const c = this.state.contract; if (!c) return;
    if (this.state.originalBlocks) { this.setState({ originalBlocks: null }); return; }
    const seq = this.generation;
    const data = await this.api<{ blocks: Block[] }>(`/legal/contracts/${c.id}/original-text`);
    if (this.live && seq === this.generation && this.state.contract?.id === c.id) this.setState({ originalBlocks: data.blocks, pane: 'paper' });
  };
  /** Scroll the paper to a paragraph and the rail to a finding, without moving the page itself. */
  private reveal(blockId: string | null | undefined, findingId?: string | null) {
    requestAnimationFrame(() => {
      const scroll = (box: Element | null, el: HTMLElement | null, pad: number) => {
        if (!box || !el || !box.contains(el)) return;
        box.scrollTo({ top: box.scrollTop + el.getBoundingClientRect().top - box.getBoundingClientRect().top - pad, behavior: motion() });
      };
      if (blockId) scroll(document.querySelector('.lv-paper-desk'), document.getElementById(`legal-block-${blockId}`), 96);
      if (findingId) scroll(document.getElementById('legal-notes'), document.getElementById(`legal-finding-${findingId}`), 8);
    });
  }
  private select = (id: string) => {
    const item = this.numbered().open.find(x => x.finding.id === id);
    if (!item) return;
    const hidden = !filterByTone(this.numbered().open, this.state.tone).some(x => x.finding.id === id);
    const block = item.finding.block_id;
    this.setState(s => ({ selected: id, railTab: 'notes', tone: hidden ? 'all' : s.tone, located: block ? { id: block, n: ++this.locateCount } : s.located }),
      () => this.reveal(block, id));
  };
  private locate = (blockId: string) => {
    this.setState({ located: { id: blockId, n: ++this.locateCount }, pane: 'paper' }, () => this.reveal(blockId));
  };
  private download = async (format: 'docx' | 'txt' | 'md', confirmed = false) => {
    const r = this.state.review, c = this.state.contract; if (!r || !c) return;
    if (format !== 'md' && !confirmed) { this.setState({ exportFormat: format, error: '' }); return; }
    const response = await fetch(`${apiBase()}/legal/reviews/${r.id}/export?format=${format === 'md' ? 'json' : format}`, withAuth());
    if (!response.ok) throw await readApiError(response);
    let blob: Blob;
    if (format === 'md') {
      const data: Review = await response.json();
      if (data.id !== r.id) throw new Error('报告与当前审查不一致，请刷新页面。');
      blob = new Blob([ReviewReport(data)], { type: 'text/markdown;charset=utf-8' });
    } else blob = await response.blob();
    const url = URL.createObjectURL(blob), a = document.createElement('a');
    a.href = url; a.download = `${format === 'md' ? pick('合同审查报告', 'Contract review report') : format === 'docx' ? pick('合同修订版', 'Contract redline') : pick('合同修订文本', 'Revised contract text')}.${format}`;
    document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 2000);
    if (this.live) this.setState({ exportFormat: null, notice: format === 'md' ? '审查报告已导出' : format === 'docx' ? 'Word 修订版已导出' : '修订文本已导出' });
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

  private steps(c: Contract, stage: Stage): Step[] {
    const r = this.state.review, index = stepOf(stage);
    const settled = Boolean(r && !isActive(r));
    const go = (view: DeskView) => () => this.setState({ view, pane: 'rail' });
    return stepLabels().map((label, i) => ({
      label, state: i < index ? 'done' : i === index ? 'current' : 'todo',
      onClick: i === 1 && settled && stage !== 'setup' && c.redaction_version === 2 ? go('setup')
        : i === 3 && settled && stage !== 'results' ? go('work')
        : i === 4 && isDone(r) && stage !== 'export' ? go('export') : undefined,
    }));
  }

  private renderWorkspace(c: Contract, stage: Stage) {
    const s = this.state, r = s.review;
    const blocks = s.preview || c.blocks;
    const outline = clauseOutline(blocks);
    const { open, excluded } = this.numbered();
    const items = stage === 'running' || stage === 'results' ? open : stage === 'export' ? open.filter(x => isRevised(r?.decisions[x.finding.id])) : [];
    const selected = stage === 'results' ? (open.some(x => x.finding.id === s.selected) ? s.selected : open[0]?.finding.id ?? null) : null;
    const selectedBlock = open.find(x => x.finding.id === selected)?.finding.block_id ?? null;
    const scenarioValid = scenarioRoleValid(s.caps?.scenario_catalog, s.contractType, s.ourRole);
    const partyValid = s.ourPartyQuote.trim().length >= 2 && !!c.blocks.find(b => b.id === s.ourPartyBlock)?.text.includes(s.ourPartyQuote);
    const amountValid = transactionAmount(s.dealValue).valid;
    const startIssue = c.redaction_version !== 2 ? pick('当前合同需重新上传并完成脱敏确认。', 'Upload this contract again and confirm its redaction.')
      : !s.ourRole || !scenarioValid ? pick('请选择我方身份', 'Choose our role')
      : !partyValid ? pick('请选择我方主体', 'Choose our party')
      : !amountValid ? pick('交易金额格式有误', 'Enter a valid amount')
      : s.modelsLoading ? pick('正在加载模型…', 'Loading models…')
      : !s.modelId || s.caps?.model_configured === false ? pick('暂无可用模型，请刷新后重试', 'No model is available; refresh and try again')
      : !s.consent ? pick('请勾选模型分析授权', 'Tick the consent box for model analysis') : '';
    const canStart = !startIssue && !s.busy;
    const values: SetupValues = { contractType: s.contractType, ourRole: s.ourRole, ourPartyBlock: s.ourPartyBlock, ourPartyQuote: s.ourPartyQuote,
      instructions: s.instructions, performanceStage: s.performanceStage, attachmentsStatus: s.attachmentsStatus, businessPriority: s.businessPriority,
      dealValue: s.dealValue, currency: s.currency, date: s.date, reviewTier: s.reviewTier, modelId: s.modelId, consent: s.consent };
    const checked = r ? r.coverage.filter(x => ['reviewed', 'not_applicable'].includes(x.status)).length : 0;
    const format = (c.format || '').toUpperCase();
    const file = { k: pick('文件', 'File'), v: pick(`${format} · ${c.blocks.length} 段`, `${format} · ${plural(c.blocks.length, 'paragraph')}`) };
    const role = r?.profile?.our_role;
    const meta = stage === 'redaction' ? [file, { k: pick('脱敏', 'Redactions'), v: pick(`${c.replacement_count} 处`, `${c.replacement_count}`) }]
      : stage === 'setup' ? [file, { k: pick('脱敏', 'Redactions'), v: pick(`已确认 ${c.replacement_count} 处`, `${c.replacement_count} confirmed`) }]
      : r ? [{ k: pick('类型', 'Type'), v: tr(r.profile?.contract_type || s.contractType) }, { k: pick('我方', 'Our role'), v: role ? tr(role) : '—' },
        { k: pick('档位', 'Depth'), v: tierLabel(tierOf(r)) }, { k: pick('模型', 'Model'), v: r.profile?.model?.id || s.modelId || '—' },
        { k: pick('范围', 'Scope'), v: isActive(r) ? pick('审查中', 'In review') : pick(`${checked}/${r.coverage.length} 已审查`, `${checked}/${r.coverage.length} reviewed`) }] : [];
    const legacy = c.status === 'ready' && c.redaction_version !== 2;
    let rail: React.ReactNode = null;
    if (stage === 'redaction') rail = <RedactionPanel tokens={redactionTokens(blocks, s.originalBlocks)} comparing={Boolean(s.originalBlocks)}
      whereOf={id => placeLabel(outline, id)} busy={s.busy} terms={s.terms} excludedTerms={s.excludedTerms}
      onTerms={terms => this.setState({ terms, preview: null })} onExcluded={excludedTerms => this.setState({ excludedTerms, preview: null })}
      onPreview={() => void this.run(() => this.redact(false))} onConfirm={() => this.setState({ confirmingRedaction: true, error: '' })} />;
    else if (stage === 'setup') rail = <SetupForm contract={c} caps={s.caps} catalog={s.catalog} values={values} hasReview={Boolean(r)} busy={s.busy}
      modelsLoading={s.modelsLoading} canStart={canStart} startIssue={startIssue}
      onType={this.changeType} onChange={this.changeSetup} onConsent={consent => this.setState({ consent })}
      onRefreshModels={() => void this.loadModels()} onStart={() => void this.run(this.start)}
      onBack={r && !isActive(r) ? () => this.setState({ view: 'work' }) : undefined} />;
    else if (stage === 'running' && r) rail = <ReviewProgress review={r} canCancel={(s.caps?.review_engine_version || 0) >= 2} busy={s.busy} onCancel={() => this.reviewAction('cancel')} />;
    else if (stage === 'results' && r) rail = <ResultsPanel review={r} blocks={c.blocks} open={open} excluded={excluded} clauseOf={id => placeLabel(outline, id)}
      selected={selected} tone={s.tone} tab={s.railTab} busy={s.busy} followup={Boolean(s.caps?.followup_questions)}
      answers={s.answers} question={s.question} questionBusy={s.questionBusy} questionConsent={s.questionConsent}
      onTab={railTab => this.setState({ railTab })} onTone={tone => this.setState({ tone })} onSelect={this.select} onLocate={this.locate}
      onDecision={(f, value, text, legalBasis, manual) => void this.run(() => this.decide(f, value, text, legalBasis, manual))}
      onExport={() => this.setState({ view: 'export' })} onResume={() => this.reviewAction('resume')} onHint={hint => this.setState({ hint })}
      onQuestion={question => this.setState({ question })} onQuestionConsent={questionConsent => this.setState({ questionConsent })} onAsk={() => void this.ask()} />;
    else if (stage === 'export' && r) rail = <ReleasePanel review={r} contract={c} open={open} busy={s.busy}
      onCheck={() => void this.run(async () => {
        const review = await this.api<Review>(`/legal/reviews/${r.id}/draft-check`, jsonRequest('POST', { request_id: crypto.randomUUID(), external_processing_confirmed: true }));
        if (this.live && this.state.review?.id === review.id) this.setState({ review });
      })}
      onApprove={fingerprint => void this.run(async () => {
        const review = await this.api<Review>(`/legal/reviews/${r.id}/draft-approval`, jsonRequest('POST', { fingerprint, confirmed: true }));
        if (this.live && this.state.review?.id === review.id) this.setState({ review });
      })}
      onReport={() => void this.run(() => this.download('md'))}
      onDraft={() => void this.run(() => this.download(c.format === 'docx' ? 'docx' : 'txt'))}
      onBack={() => this.setState({ view: 'work' })} />;
    return <main id="legal-main" tabIndex={-1} className={`lv-workspace pane-${s.pane}`} aria-label={pick('合同审查工作区', 'Contract review workspace')}>
      <div className="lv-pane-switch" role="group" aria-label={pick('工作区视图', 'Workspace view')}>
        <button aria-pressed={s.pane === 'rail'} onClick={() => this.setState({ pane: 'rail' })}>{labelOf(RAIL_LABEL, stage)}</button>
        <button aria-pressed={s.pane === 'paper'} onClick={() => this.setState({ pane: 'paper' }, () => this.reveal(selectedBlock))}>{pick('合同正文', 'Contract text')}</button>
      </div>
      <Outline entries={outline} items={items} decisions={r?.decisions || {}} running={stage === 'running'} activeBlock={selectedBlock}
        blockCount={blocks.length} pageCount={pagesOf(blocks).length} meta={meta}
        onEntry={(entry, first) => { if (stage === 'results' && first) this.select(first); else this.locate(entry.id); }} />
      <Paper contract={c} blocks={blocks} stage={stage} decisions={r?.decisions || {}} items={items} selected={selected} located={s.located}
        originals={s.originalBlocks} busy={s.busy} candidates={stage === 'setup' ? partyCandidates(c.blocks) : []}
        party={{ blockId: s.ourPartyBlock, quote: s.ourPartyQuote }} detail={stage === 'running' && r ? r.stage : undefined}
        onSelect={id => { this.select(id); this.setState({ pane: 'rail' }); }} onCompare={() => void this.run(this.showOriginal)}
        onParty={(ourPartyBlock, ourPartyQuote) => this.changeSetup({ ourPartyBlock, ourPartyQuote })} />
      <aside className="lv-rail" aria-label={pick('审查操作', 'Review actions')}>
        {(legacy || c.warnings.length > 0) && <div className="lv-rail-notes">
          {legacy && <p className="lv-note is-warn">{pick('该合同使用旧版脱敏，仅可查看历史报告；重新审查请重新上传。', 'This contract uses the old redaction; only past reports can be viewed. Upload it again to review it again.')}</p>}
          {c.warnings.length > 0 && <details className="lv-disclosure"><summary>{pick(`解析提示（${c.warnings.length}）`, `Parsing notes (${c.warnings.length})`)}</summary>
            <div className="lv-disclosure-body">{c.warnings.map((w, i) => <p key={i}>{serverText(w)}</p>)}</div></details>}
        </div>}
        {rail}
      </aside>
    </main>;
  }

  render() {
    const s = this.state, c = s.contract, r = s.review;
    const lang = this.context?.lang ?? currentLang();
    const root = lang === 'en' ? 'legal-v2 lv-en' : 'legal-v2';
    const canUpload = Boolean(s.workspace && s.caps?.encryption_configured && !s.busy && !s.loading);
    const dialogOpen = Boolean(s.pendingFile || s.confirmingRedaction || s.archivePolicy || s.exportFormat);
    const stage = c ? deskStage(c, r, s.view) : null;
    if (s.denied) return <div className={`${root} lv-gate`}><main className="lv-gate-card">
      <span className="lv-tile lv-tile-lg is-gray" aria-hidden="true"><Lock size={32} strokeWidth={1.5} /></span>
      <h1>{pick('会员权限已变更', 'Your membership has changed')}</h1><p>{pick('合同审查为 Max 会员专享，合同内容已从页面移除。', 'Contract review is part of the Max plan. The contract has been removed from this page.')}</p>
      <div className="lv-gate-actions"><a className="lv-primary" href="/agent">{pick('返回研究工作台', 'Back to research desk')}</a></div>
    </main></div>;
    const matterName = s.matters.find(m => m.id === s.workspace?.matter_id)?.name;
    return <div className={root}>
      <a className="lv-skip" href="#legal-main">{pick('跳到工作区', 'Skip to workspace')}</a>
      <TopBar section={s.tab === 'policies' ? pick('公司规范', 'Company policies') : c ? fileTitle(c.name) : undefined}
        steps={c && stage && s.tab === 'review' ? this.steps(c, stage) : undefined} policyCount={s.policies.length} policiesOpen={s.tab === 'policies'}
        onHome={this.clear} onPolicies={() => this.setState(state => ({ tab: state.tab === 'policies' ? 'review' : 'policies' }))}
        user={this.props.user} matters={s.matters} workspace={s.workspace} busy={s.busy} onLogout={this.props.logout}
        onMatter={id => {
          const m = s.matters.find(x => x.id === id); if (!m) return;
          void this.run(async () => { this.clear(); const workspace = { matter_id: m.id, org_id: m.org_id }; this.setState({ workspace }); await this.refreshList(workspace); });
        }} />
      {s.error && !dialogOpen && <div className="lv-banner lv-error" role="alert"><AlertCircle {...ic} /><span>{serverText(s.error)}</span>
        <button className="lv-icon" aria-label={pick('关闭错误', 'Dismiss error')} onClick={() => this.setState({ error: '' })}><X {...ic} /></button></div>}
      {s.caps && !s.caps.encryption_configured && <div className="lv-banner lv-warning"><AlertCircle {...ic} />
        <span>{pick('安全存储未配置，暂不可上传，请联系管理员。', 'Secure storage is not configured, so uploads are off. Contact your administrator.')}</span></div>}
      {s.modelError && <div className="lv-banner lv-warning"><AlertCircle {...ic} /><span>{serverText(s.modelError)}</span>
        <button className="lv-text-button" onClick={() => void this.loadModels()}>{pick('重新加载', 'Reload')}</button></div>}
      <input ref={el => { this.uploadInput = el; }} type="file" accept=".docx,.pdf,.txt" hidden onChange={e => { const file = e.target.files?.[0]; e.target.value = ''; this.queueUpload(file); }} />
      {s.loading ? <main className="lv-skeleton" role="status"><span className="lv-sr">{pick('加载中…', 'Loading…')}</span>
          <span className="lv-sk lv-sk-title" /><span className="lv-sk lv-sk-line" /><span className="lv-sk lv-sk-card" /><span className="lv-sk lv-sk-row" /><span className="lv-sk lv-sk-row" /></main>
        : !s.workspace ? <main id="legal-main" className="lv-loading"><AlertCircle {...ic} size={22} /><h1>{pick('工作空间加载失败', 'The workspace did not load')}</h1>
          <p>{pick('请检查网络后重试。', 'Check your connection and try again.')}</p><button className="lv-primary" onClick={() => void this.initialize()}>{pick('重试', 'Retry')}</button></main>
        : s.tab === 'policies' ? <PolicyEditor catalog={s.caps?.scenario_catalog} policies={s.policies} busy={s.busy}
          onSave={(draft, existing) => void this.run(async () => {
            if (!s.workspace) return;
            await this.api(`/legal/policies${existing ? `/${existing.id}` : ''}?org_id=${encodeURIComponent(s.workspace.org_id)}`, jsonRequest(existing ? 'PUT' : 'POST', { ...draft, version: existing?.version }));
            await this.refreshList(s.workspace);
            if (this.live) this.setState({ notice: '规范已保存' });
          })} onArchive={policy => this.setState({ archivePolicy: policy, error: '' })} />
        : !c || !stage ? <Library contracts={s.contracts} matterName={matterName} loading={s.loading} disabled={!canUpload} busy={s.busy}
          query={s.libraryQuery} onQuery={libraryQuery => this.setState({ libraryQuery })}
          onUpload={() => this.uploadInput?.click()} onOpen={id => void this.run(() => this.openContract(id))}
          onDrop={files => {
            if (files.length !== 1) { this.setState({ error: '每次仅支持上传一份合同。' }); return; }
            this.queueUpload(files[0]);
          }} />
        : this.renderWorkspace(c, stage)}
      {s.pendingFile && <ConfirmDialog title={pick('上传确认', 'Confirm upload')} confirmLabel={pick('同意并上传', 'Agree and upload')} busyLabel={pick('正在上传并脱敏…', 'Uploading and redacting…')} busy={s.busy}
        onCancel={() => this.setState({ pendingFile: null, error: '' })} onConfirm={() => void this.run(() => this.upload(s.pendingFile || undefined))}>
        <div className="lv-upload-file"><FileText {...ic} size={18} /><span>{s.pendingFile.name}<small>{(s.pendingFile.size / 1024).toFixed(1)} KB</small></span></div>
        <ol className="lv-dialog-points">
          <li>{pick('原件将在服务器端解析、脱敏并加密存储', 'The original is parsed, redacted and stored encrypted on the server')}</li>
          <li>{pick('上传不会调用模型，审查前需另行授权', 'Uploading does not call a model; a review needs your separate consent')}</li>
          <li>{pick(`存储地域：${s.caps?.upload_disclosure?.storage_region ?? ''}（运营方声明）`, `Storage region: ${tr(s.caps?.upload_disclosure?.storage_region ?? '')} (as stated by the operator)`)}</li>
        </ol>
        <details className="lv-disclosure-text"><summary>{pick('《原件处理说明》', 'How the original is handled')}</summary><p>{serverText(s.caps?.upload_disclosure?.notice)}</p></details>
        {s.error && <p role="alert" className="lv-note is-error">{serverText(s.error)}</p>}
      </ConfirmDialog>}
      {s.confirmingRedaction && <ConfirmDialog title={pick('确认脱敏结果', 'Confirm redaction')} confirmLabel={pick('确认并继续', 'Confirm and continue')} busyLabel={pick('正在锁定脱敏结果…', 'Locking the redaction…')} busy={s.busy}
        onCancel={() => this.setState({ confirmingRedaction: false, error: '' })} onConfirm={() => void this.run(() => this.redact(true))}>
        <p>{pick('确认后脱敏结果将锁定，模型分析需在下一步单独授权。', 'Once confirmed, the redaction is locked. Model analysis needs your separate consent in the next step.')}</p>
        {s.error && <p role="alert" className="lv-note is-error">{serverText(s.error)}</p>}
      </ConfirmDialog>}
      {s.exportFormat && <ConfirmDialog title={pick('导出确认', 'Confirm export')} confirmLabel={pick('确认导出', 'Export')} busyLabel={pick('正在生成文件…', 'Generating the file…')} busy={s.busy}
        onCancel={() => this.setState({ exportFormat: null, error: '' })} onConfirm={() => { const format = s.exportFormat; if (format) void this.run(() => this.download(format, true)); }}>
        <p>{pick('修订版包含未脱敏的真实信息及删除内容，请确认接收范围。导出不会签署合同或覆盖原文件。',
          'The revised file contains real, unredacted information and deleted text, so check who will receive it. Exporting does not sign the contract or overwrite the original.')}</p>
        {s.error && <p role="alert" className="lv-note is-error">{serverText(s.error)}</p>}
      </ConfirmDialog>}
      {s.archivePolicy && <ConfirmDialog title={pick('归档规范', 'Archive policy')} confirmLabel={pick('确认归档', 'Archive')} busyLabel={pick('正在归档…', 'Archiving…')} busy={s.busy}
        onCancel={() => this.setState({ archivePolicy: null, error: '' })} onConfirm={() => void this.run(async () => {
          const policy = this.state.archivePolicy; const workspace = this.state.workspace; if (!policy || !workspace) return;
          await this.api(`/legal/policies/${policy.id}?org_id=${encodeURIComponent(workspace.org_id)}&version=${policy.version}`, { method: 'DELETE' });
          if (this.live) this.setState({ archivePolicy: null, notice: '规范已归档' });
          await this.refreshList(workspace);
        })}>
        <p>{pick(`“${s.archivePolicy.title}”归档后不再用于新审查，历史报告不受影响。`, `“${s.archivePolicy.title}” will no longer apply to new reviews. Past reports are not affected.`)}</p>
        {s.error && <p role="alert" className="lv-note is-error">{serverText(s.error)}</p>}
      </ConfirmDialog>}
      {s.notice && <Toast key={`n-${s.notice}`} text={tr(s.notice)} done onDone={() => this.setState({ notice: '' })} />}
      {!s.notice && s.hint && <Toast key={`h-${s.hint}`} text={tr(s.hint)} onDone={() => this.setState({ hint: '' })} />}
    </div>;
  }
}

