import type { Review, Source } from './types';

import { sourceKindLabel } from './sourceLabels';

export function SourceDetails({ source }: { source: Source }) {
  return <div className="lv-source-meta">
    <small>{sourceKindLabel(source)} · 页面类型由规则初筛，不是效力认证。{source.discovery === 'direct_official' && ' 此页由官方地址直接获取。'}</small>
    {source.effective_date_candidates?.map((item, i) => <p key={i}>页面记载的施行日期候选：{item.date}<q>{item.quote}</q></p>)}
    <small>检索于 {new Date(source.retrieved_at).toLocaleString('zh-CN')} · 版本及适用性待核验。</small>
  </div>;
}

export function ReviewContext({ review, onLocate }: { review: Review; onLocate: (id: string) => void }) {
  const brief = review.transaction_brief;
  const health = review.evidence_health;
  return <div className="lv-context-review">
    {review.profile?.scenario && <details className="lv-details" aria-label="本轮场景清单">
      <summary>本轮场景 · {review.profile.scenario.label} · {review.profile.our_role}</summary>
      <p>{review.profile.scenario.role_focus}</p>
      {review.profile.scenario.checks.map(check => <p key={check.id}>{check.title}</p>)}
      <p>建议核对材料：{review.profile.scenario.materials.join('；')}</p>
      <small>已冻结目录版本 {review.profile.scenario.catalog_version}。{review.profile.scenario.limits}</small>
    </details>}
    {brief && <details className="lv-details" open={brief.gaps.length > 0} aria-label="交易背景与资料缺口">
      <summary>交易背景与资料缺口 · {brief.gaps.length} 项待核对</summary>
      <p className="lv-muted">用户填写的背景，未经独立核实；与合同原文分开呈现。</p>
      <dl className="lv-brief-fields">
        <div><dt>履行阶段</dt><dd>{brief.context.performance_stage || '未知'}</dd></div>
        <div><dt>附件声明</dt><dd>{brief.context.attachments_status || '未知'}</dd></div>
        <div><dt>本轮重点</dt><dd>{brief.context.business_priority || '综合审查'}</dd></div>
        <div><dt>金额</dt><dd>{brief.context.deal_value == null ? '未提供' : `${brief.context.deal_value} ${brief.context.currency}`}</dd></div>
      </dl>
      {brief.gaps.map(gap => <p className="lv-inline-warning" key={gap.code}>{gap.message}</p>)}
      {brief.material_references.map(ref => <button className="lv-source-link" key={ref.block_id} onClick={() => onLocate(ref.block_id)}>查看材料引用 · {ref.block_id} · {ref.quote}</button>)}
      <small>{brief.notice}</small>
    </details>}
    {health && <details className="lv-details" open={health.status === 'gaps'} aria-label="法律检索状态">
      <summary>法律检索 · {health.topics_with_sources}/{health.queried_topics} 项取得来源</summary>
      {health.status === 'gaps' && <p className="lv-inline-warning">有 {health.failed_or_empty_topics} 项检索未取得来源，不能据此排除法律风险。</p>}
      <p>{health.source_count} 个来源，{health.version_pending} 个版本待核验。{health.notice}</p>
      {review.retrieval?.filter(item => item.status !== 'retrieved').map(item => <p key={item.rule_id}>{item.rule_id}：{item.warnings.join('；') || '尚未取得可核验来源。'}</p>)}
      {review.sources.map(source => <details className="lv-citation" key={source.id}>
        <summary>{source.title}</summary><SourceDetails source={source} />
        <a href={source.url} target="_blank" rel="noreferrer noopener">核对原网页 ↗</a>
      </details>)}
    </details>}
  </div>;
}
