import React from 'react';
import type { Catalog, Finding, Policy, Review } from './types';
import { diffText } from './diff';
import { findingStatus } from './findingStatus';
import { SourceDetails } from './ReviewContext';
import { sourceKindLabel } from './sourceLabels';

const PATHS: Record<string, string[]> = {
  plus: ['M10 4v12M4 10h12'], close: ['M5 5l10 10M15 5L5 15'], menu: ['M3 5h14M3 10h14M3 15h14'],
  chat: ['M4 3h12a2 2 0 012 2v8a2 2 0 01-2 2H8l-5 3V5a2 2 0 012-2'],
  file: ['M5 2h7l4 4v12H4V2h1', 'M12 2v5h4M7 11h6M7 14h4'],
  document: ['M5 2h7l4 4v12H4V2h1', 'M12 2v5h4M7 10h6M7 13h6M7 16h3'],
  book: ['M3 3h5a3 3 0 012 2 3 3 0 013-2h4v13h-4a3 3 0 00-3 2 3 3 0 00-3-2H3V3', 'M10 5v13'],
  search: ['M14 14l4 4', 'M15 9A6 6 0 113 9a6 6 0 0112 0'],
  arrow: ['M16 10H4M9 5l-5 5 5 5'], 'arrow-right': ['M4 10h12M11 5l5 5-5 5'], 'arrow-up': ['M10 16V4M5 9l5-5 5 5'],
  attach: ['M7 10l6-6a3 3 0 014 4l-8 8a5 5 0 01-7-7l8-8', 'M5 12l7-7'],
  lock: ['M5 9h10v8H5V9', 'M7 9V6a3 3 0 016 0v3M10 12v2'],
  home: ['M2 9l8-7 8 7M5 7v11h10V7M8 18v-6h4v6'],
  panel: ['M2 3h16v14H2V3M11 3v14'], exit: ['M8 3H3v14h5M8 10h9M13 6l4 4-4 4'],
  alert: ['M10 2l9 16H1L10 2', 'M10 7v5M10 15h.01'], check: ['M3 10l4 4L17 4'],
  settings: ['M3 5h14M3 10h14M3 15h14M7 3v4M13 8v4M8 13v4'],
  chevron: ['M5 8l5 5 5-5'], refresh: ['M16 6a7 7 0 10.5 7M16 2v5h-5'],
  stop: ['M5 5h10v10H5V5'], list: ['M7 5h10M7 10h10M7 15h10M3 5h.1M3 10h.1M3 15h.1'],
  download: ['M10 2v11M6 9l4 4 4-4M3 13v5h14v-5'],
};
export function Icon({ name }: { name: string }) { return <svg viewBox="0 0 20 20" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.45" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{(PATHS[name] || PATHS.file).map((d, i) => <path key={i} d={d} />)}</svg>; }

export function ModelSelect({ catalog, value, loading, disabled, onChange, onRefresh }: { catalog: Catalog | null; value: string; loading: boolean; disabled: boolean; onChange: (id: string) => void; onRefresh: () => void }) {
  return <div className="lv-model"><Icon name="settings" /><select aria-label="审查模型" value={value} disabled={disabled || loading || !catalog} onChange={e => onChange(e.target.value)}><option value="" disabled>{loading ? '读取模型…' : '选择审查模型'}</option>{catalog?.families.map(family => <optgroup key={family} label={family}>{catalog.models.filter(m => m.family === family).map(m => <option value={m.id} key={m.id}>{m.id}</option>)}</optgroup>)}</select><button type="button" className="lv-icon" disabled={disabled || loading} title="刷新网关型号" aria-label="刷新模型列表" onClick={onRefresh}><Icon name="refresh" /></button></div>;
}

type FindingProps = { finding: Finding; review: Review; original: string; busy: boolean; initiallyOpen: boolean;
  onLocate: (id: string) => void; onDecision: (value: string, text: string, legalBasis: boolean, manual: boolean) => void };
export class FindingCard extends React.Component<FindingProps, { open: boolean; text: string; editing: boolean; legalBasis: boolean; manual: boolean }> {
  constructor(props: FindingProps) { super(props); this.state = { open: props.initiallyOpen, text: props.review.decisions[props.finding.id]?.text || props.finding.suggested_text, editing: false, legalBasis: false, manual: false }; }
  render() {
    const { finding: f, review: r, busy, onLocate, onDecision, original } = this.props;
    const decision = r.decisions[f.id];
    const done = ['completed', 'partial'].includes(r.status);
    const changed = this.state.text !== f.suggested_text;
    const status = findingStatus(f);
    const needsLegal = f.requires_legal_confirmation === true || ((r.engine_version || 0) >= 2 && f.kind === 'legal');
    const canAccept = done && !busy && !!f.block_id && !!f.suggested_text && !!this.state.text.trim()
      && f.revision_allowed !== false && f.missing_facts.length === 0 && f.evidence_status !== 'unverified'
      && (!needsLegal || this.state.legalBasis) && (!changed || this.state.manual);
    return <article className={`lv-finding ${decision?.decision === 'accepted' ? 'accepted' : ''}`}>
      <div className="lv-finding-top"><span className={`lv-risk ${status === 'supported' ? f.severity : 'low'}`}>{status === 'rejected' ? '候选已否定' : status === 'unconfirmed' ? '待核实' : ({ high: '重点关注', medium: '需要关注', low: '提示' } as Record<string, string>)[f.severity] || '需关注'}</span><span className="lv-kind">{({ legal: '法律风险', commercial: '商业利益', company_policy: '公司规范' } as Record<string, string>)[f.kind]}</span>{decision?.decision === 'accepted' && <span className="lv-decision"><Icon name="check" />已纳入修订</span>}{decision?.decision === 'draft' && <span className="lv-decision">人工草稿待复核</span>}{decision?.decision === 'rejected' && <span className="lv-decision">已保留原文（不代表风险消失）</span>}</div>
      <h3><button aria-expanded={this.state.open} onClick={() => this.setState({ open: !this.state.open })}>{f.title}<Icon name="chevron" /></button></h3><p className="lv-impact">{f.impact}</p>
      {f.block_id && <button className="lv-source-link" onClick={() => onLocate(f.block_id!)}><Icon name="file" />定位原文 · {f.block_id}<Icon name="arrow-right" /></button>}
      {this.state.open && <div className="lv-finding-details">{f.agent_title && <p className="lv-muted">提出意见：{f.agent_title} · 复核状态以本条说明为准</p>}{f.original_quote && <blockquote>{f.original_quote}</blockquote>}<h4>为什么需要关注</h4><p>{f.reason}</p>
        {f.verification_note && <details className="lv-verification"><summary>查看复核说明</summary><p>{f.verification_note}</p></details>}
        {f.missing_facts.length > 0 && <div className="lv-inline-warning"><strong>还需要确认</strong>{f.missing_facts.map((item, i) => <p key={i}>{item}</p>)}</div>}
        {f.validation_warnings?.map((w, i) => <p key={i} className="lv-inline-warning">{w}</p>)}
        {f.conflict_group && <p className="lv-inline-warning">这一段还有其他修改方案。请选择或人工合并，不会把相互覆盖的建议同时写入。</p>}
        {f.citations.map((citation, i) => { const source = r.sources.find(x => x.id === citation.source_id); return source ? <details className="lv-citation" key={`${citation.source_id}-${i}`}><summary><Icon name="book" />{source.title}</summary><blockquote>{citation.supporting_quote}</blockquote><a href={source.url} target="_blank" rel="noreferrer noopener">核对外部原文 ↗</a><SourceDetails source={source} /></details> : null; })}
        {f.policy_ids.map(id => { const p = r.policies.find(x => x.id === id); return p ? <details className="lv-citation" key={id}><summary><Icon name="book" />公司规范：{p.title} · v{p.version}</summary><p>{p.text}</p><small>这是内部标准，不是法律规定。</small></details> : null; })}
        {f.evidence_status === 'unverified' && <p className="lv-inline-warning">依据不足或复核未支持，不能直接纳入修订。</p>}
        {f.suggested_text && <div className="lv-suggestion"><div><h4>建议这样改</h4><button className="lv-text-button" onClick={() => this.setState({ editing: !this.state.editing })}>{this.state.editing ? '查看修改对比' : '编辑建议'}</button></div>{this.state.editing ? <label className="lv-edit-label">本段完整替代文本<textarea aria-label="编辑本段建议" rows={5} value={this.state.text} maxLength={12000} onChange={e => this.setState({ text: e.target.value, manual: false, legalBasis: false })} /></label> : <div className="lv-diff" aria-label="原文与建议修改对比">{diffText(original || f.original_quote, this.state.text).map((part, i) => part.kind === 'del' ? <del key={i}>{part.text}</del> : part.kind === 'ins' ? <ins key={i}>{part.text}</ins> : <span key={i}>{part.text}</span>)}</div>}<small>仅展示文字差异。导出 DOCX 会保留 Word 原生修订。</small></div>}
        {needsLegal && f.revision_allowed !== false && f.suggested_text && <label className="lv-consent"><input type="checkbox" checked={this.state.legalBasis} onChange={e => this.setState({ legalBasis: e.target.checked })} />我已核对所引规定的版本和适用性。</label>}
        {changed && f.suggested_text && <label className="lv-consent"><input type="checkbox" checked={this.state.manual} onChange={e => this.setState({ manual: e.target.checked })} />我确认保存为待复核人工草稿；不沿用原建议的核验结果。</label>}
        <div className="lv-actions"><button className="lv-primary" disabled={!canAccept || decision?.decision === 'accepted'} onClick={() => onDecision(changed ? 'draft' : 'accepted', this.state.text, this.state.legalBasis, this.state.manual)}><Icon name="check" />{decision?.decision === 'accepted' ? '已纳入修订' : changed ? '保存人工草稿' : '接受修改'}</button><button className="lv-secondary" disabled={busy || !done || decision?.decision === 'rejected'} onClick={() => onDecision('rejected', '', false, false)}>保留原文</button>{decision && <button className="lv-text-button" disabled={busy || !done} onClick={() => onDecision('pending', '', false, false)}>撤销决定</button>}</div>
      </div>}
    </article>;
  }
}

type Draft = { title: string; text: string; contract_type: string };
type PolicyProps = { policies: Policy[]; busy: boolean; onSave: (draft: Draft, existing: Policy | null) => void; onArchive: (policy: Policy) => void };
export class PolicyEditor extends React.Component<PolicyProps, { draft: Draft; editing: Policy | null }> {
  state = { draft: { title: '', text: '', contract_type: '全部' }, editing: null as Policy | null };
  render() { const { policies, busy, onSave, onArchive } = this.props; const { draft, editing } = this.state;
    return <main className="lv-policy-page"><p className="lv-eyebrow">COMPANY PLAYBOOK</p><h1>让它知道公司的底线</h1><p className="lv-subtitle">写清必须满足的条件，以及允许的例外。每轮审查保留当时版本，内部规范不会被当作法律。</p><div className="lv-policy-layout"><section className="lv-policy-list"><h2>正在使用的规范 <span>{policies.length}</span></h2>{!policies.length && <div className="lv-policy-empty"><Icon name="book" /><p>还没有公司规范</p><small>可以先审查合同，再逐步补充付款、责任及审批要求。</small></div>}{policies.map(p => <article key={p.id}><div><h3>{p.title}</h3><small>v{p.version}</small></div><span className="lv-policy-type">{p.contract_type}</span><p>{p.text}</p><div className="lv-actions"><button className="lv-secondary" disabled={busy} onClick={() => this.setState({ editing: p, draft: { title: p.title, text: p.text, contract_type: p.contract_type } })}>编辑</button><button className="lv-text-button" disabled={busy} onClick={() => onArchive(p)}>归档</button></div></article>)}</section><form className="lv-policy-form" onSubmit={e => { e.preventDefault(); onSave(draft, editing); }}><h2>{editing ? '编辑规范' : '新增规范'}</h2><label>规范标题<input required maxLength={150} value={draft.title} onChange={e => this.setState({ draft: { ...draft, title: e.target.value } })} placeholder="例如：采购预付款要求" /></label><label>适用合同<select value={draft.contract_type} onChange={e => this.setState({ draft: { ...draft, contract_type: e.target.value } })}>{['全部', '采购合同', '服务合同', '保密协议', '其他商事合同'].map(t => <option key={t}>{t}</option>)}</select></label><label>审查要求<textarea required minLength={5} maxLength={2500} rows={6} value={draft.text} onChange={e => this.setState({ draft: { ...draft, text: e.target.value } })} placeholder="例如：我方作为采购方时，预付款超过合同价款的 30% 需业务负责人批准。这是公司要求，不是法定比例。" /></label><p className="lv-muted">仅组织管理员可更改规范。不要填写与审查无关的秘密。</p><div className="lv-actions"><button className="lv-primary" disabled={busy}>保存规范</button>{editing && <button type="button" className="lv-secondary" onClick={() => this.setState({ editing: null, draft: { title: '', text: '', contract_type: '全部' } })}>取消编辑</button>}</div></form></div></main>;
  }
}
const escaped = (value: string) => value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
export function ReviewReport(review: Review): string {
  const out = ['# 合同审查报告', '', `审查编号：${review.id}`, `审查状态：${review.status}`, `模型：${review.profile?.model?.id || '历史记录未提供'}`, `我方角色：${review.profile?.our_role || '未记录'}`, `审查方式：${review.profile?.review_mode === 'multi_agent' ? '多 Agent 协作' : '常规审查'}`, '', review.notice];
  if (review.transaction_brief) {
    const b = review.transaction_brief;
    out.push('', '## 交易背景（用户填写，尚未独立核实）', `履行阶段：${escaped(b.context.performance_stage || '未知')}`, `附件声明：${escaped(b.context.attachments_status || '未知')}`, `业务重点：${escaped(b.context.business_priority || '综合审查')}`, `金额：${escaped(b.context.deal_value == null ? '未提供' : `${b.context.deal_value} ${b.context.currency}`)}`);
    for (const gap of b.gaps) out.push('', `资料缺口：${escaped(gap.message)}`);
  }
  if (review.evidence_health) out.push('', '## 法律检索状态', `取得来源：${review.evidence_health.topics_with_sources}/${review.evidence_health.queried_topics} 项；版本待核验：${review.evidence_health.version_pending} 个来源。`, review.evidence_health.notice);
  out.push('', '## 逐条意见');
  for (const [index, f] of review.findings.entries()) {
    out.push('', `### ${index + 1}. ${escaped(f.title)}`, `类别：${f.kind}；证据/复核状态：${findingStatus(f)}；优先级：${findingStatus(f) === 'supported' ? f.severity : '不作为已成立风险计级'}；原文：${f.block_id || '待确定插入位置'}`, '', '原文：', escaped(f.original_quote), '', '对我方的影响：', escaped(f.impact), '', '判断理由：', escaped(f.reason));
    if (f.agent_title) out.push('', `提出意见：${escaped(f.agent_title)}`);
    if (f.missing_facts.length) out.push('', '待确认信息：', ...f.missing_facts.map(escaped));
    if (f.verification_note) out.push('', '模型复核说明（不等于法律认证）：', escaped(f.verification_note));
    for (const c of f.citations) { const s = review.sources.find(source => source.id === c.source_id); if (s) out.push('', `依据：${escaped(s.title)}`, escaped(c.supporting_quote), s.url, `来源类型（规则初筛）：${sourceKindLabel(s)}；检索时间：${s.retrieved_at}；版本和适用性待人工核验。`); }
    for (const id of f.policy_ids) { const p = review.policies.find(item => item.id === id); if (p) out.push('', `公司规范：${escaped(p.title)} v${p.version}`, escaped(p.text)); }
    const decision = review.decisions[f.id];
    out.push('', `处理决定：${decision?.decision || 'pending'}`);
    if (decision?.text || f.suggested_text) out.push('', '建议或已选择的完整替代段落：', escaped(decision?.text || f.suggested_text));
  }
  out.push('', `修订组合状态：${review.draft_approval ? '用户已确认精确修改组合（非签署或企业授权审批）' : '尚未最终确认'}`, '', '## 检查覆盖');
  for (const c of review.coverage) out.push('', `### ${escaped(c.title)} · ${c.status}`, escaped(c.note), escaped(c.verification_note || ''));
  for (const error of Object.values(review.batch_errors || {})) out.push('', `未完成：${escaped(error)}`);
  out.push('', '本报告不是脱敏质量、法律时效或整份合同安全的保证。导出的 Word 修订稿保留真实内容和删除内容，分享前应再次检查。', '');
  return out.join('\n');
}
