import { ExternalLink } from 'lucide-react';
import type { Block, Review, Source } from './types';
import { sourceKindLabel } from './sourceLabels';
import { COVERAGE_STATUS } from './labels';
import { clauseLabel } from './text';
import { Lanes } from './ReviewStatus';
import { RichText } from './ui';
import { ic } from './icon';

export function SourceDetails({ source }: { source: Source }) {
  return <div className="lv-source-meta">
    <small>{sourceKindLabel(source)}（页面类型由规则初步判断，不代表效力认证）{source.discovery === 'direct_official' && ' · 由官方网址直接获取'}</small>
    {source.effective_date_candidates?.map((item, i) => <p key={i}>页面记载的施行日期：{item.date}<q>{item.quote}</q></p>)}
    <small>检索于 {new Date(source.retrieved_at).toLocaleString('zh-CN')}，版本和适用范围请自行核实。</small>
  </div>;
}

/** Everything that explains how the result was reached, kept below the decisions. */
export function ReviewDetails({ review, blocks, active, onLocate }: {
  review: Review; blocks: Block[]; active: boolean; onLocate: (id: string) => void;
}) {
  const brief = review.transaction_brief;
  const health = review.evidence_health;
  const scenario = review.profile?.scenario;
  const checked = review.coverage.filter(c => ['reviewed', 'not_applicable'].includes(c.status)).length;
  return <section className="lv-appendix" aria-labelledby="legal-appendix-title">
    <div className="lv-section-head"><h2 id="legal-appendix-title">审查依据与过程</h2></div>
    {review.collaboration && !active && <details className="lv-disclosure" aria-label="协作进度">
      <summary>审查分工 · {review.collaboration.agents.length} 个维度独立检查，统一复核</summary>
      <div className="lv-disclosure-body"><Lanes collaboration={review.collaboration} /><p className="lv-hint">各维度只提出建议，不会直接修改合同；意见之间的分歧需要你来决定。</p></div>
    </details>}
    {scenario && <details className="lv-disclosure" aria-label="本轮场景清单">
      <summary>本轮场景 · {scenario.label} · 我方：{review.profile?.our_role}</summary>
      <div className="lv-disclosure-body">
        <p>{scenario.role_focus}</p>
        <ul className="lv-plain-list">{scenario.checks.map(check => <li key={check.id}>{check.title}</li>)}</ul>
        <p>建议核对材料：{scenario.materials.join('；')}</p>
        <p className="lv-hint">场景目录第 {scenario.catalog_version} 版，已随本轮审查保存。{scenario.limits}</p>
      </div>
    </details>}
    {brief && <details className="lv-disclosure" open={brief.gaps.length > 0 || undefined} aria-label="交易背景与资料缺口">
      <summary>交易背景与资料缺口{brief.gaps.length > 0 ? ` · ${brief.gaps.length} 项待核对` : ''}</summary>
      <div className="lv-disclosure-body">
        <dl className="lv-facts-grid">
          <div><dt>履行阶段</dt><dd>{brief.context.performance_stage || '未知'}</dd></div>
          <div><dt>附件情况</dt><dd>{brief.context.attachments_status || '未知'}</dd></div>
          <div><dt>本轮最关心</dt><dd>{brief.context.business_priority || '综合审查'}</dd></div>
          <div><dt>交易金额</dt><dd>{brief.context.deal_value == null ? '未提供' : `${brief.context.deal_value} ${brief.context.currency}`}</dd></div>
        </dl>
        {brief.gaps.map(gap => <p className="lv-note is-warn" key={gap.code}>{gap.message}</p>)}
        {brief.material_references.map(ref => <button className="lv-source-link" key={ref.block_id} onClick={() => onLocate(ref.block_id)}>查看合同中提到的材料：<RichText text={ref.quote} /></button>)}
        <p className="lv-hint">以上背景由你填写，未经独立核实，与合同原文分开使用。{brief.notice}</p>
      </div>
    </details>}
    {health && <details className="lv-disclosure" open={health.status === 'gaps' || undefined} aria-label="法律检索状态">
      <summary>法律检索 · {health.topics_with_sources}/{health.queried_topics} 项取得来源</summary>
      <div className="lv-disclosure-body">
        {health.status === 'gaps' && <p className="lv-note is-warn">有 {health.failed_or_empty_topics} 项检索未取得来源，不能据此排除法律风险。</p>}
        <p>共 {health.source_count} 个来源，其中 {health.version_pending} 个的版本有待核实。{health.notice}</p>
        {review.retrieval?.filter(item => item.status !== 'retrieved').map(item => <p key={item.rule_id} className="lv-hint">{review.coverage.find(c => c.rule_id === item.rule_id)?.title || '检索主题'}：{item.warnings.join('；') || '尚未取得可核验的来源。'}</p>)}
        {review.sources.map(source => <details className="lv-citation" key={source.id}>
          <summary>{source.title}</summary><SourceDetails source={source} />
          <a href={source.url} target="_blank" rel="noreferrer noopener">打开来源原文<ExternalLink {...ic} size={13} /></a>
        </details>)}
      </div>
    </details>}
    <details className="lv-disclosure">
      <summary>检查范围 · {checked}/{review.coverage.length} 已完成</summary>
      <div className="lv-disclosure-body">
        <ul className="lv-coverage">{review.coverage.map(item => <li key={item.rule_id}>
          <div><strong>{item.title}</strong><span className={`lv-chip ${item.status === 'reviewed' ? 'is-ok' : item.status === 'not_applicable' ? '' : 'is-mid'}`}>{COVERAGE_STATUS[item.status] || item.status}</span></div>
          <p>{item.note}</p>{item.verification_note && <p className="lv-hint">{item.verification_note}</p>}
        </li>)}</ul>
        {Object.entries(review.batch_errors || {}).map(([key, value]) => <p key={key} className="lv-note is-warn">{value}</p>)}
        {review.notice && <p className="lv-hint">{review.notice}</p>}
      </div>
    </details>
    {review.intake?.facts && review.intake.facts.length > 0 && <details className="lv-disclosure">
      <summary>读取到的合同要点 · {review.intake.facts.length}</summary>
      <div className="lv-disclosure-body lv-key-facts">{review.intake.facts.map((fact, i) => <button key={i} onClick={() => onLocate(fact.block_id)}>
        <small>{fact.name}</small><span><RichText text={fact.value} /></span><em>{clauseLabel(blocks.find(b => b.id === fact.block_id))}</em>
      </button>)}</div>
    </details>}
  </section>;
}
