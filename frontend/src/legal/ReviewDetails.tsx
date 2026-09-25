import { ExternalLink } from 'lucide-react';
import type { Review, Source } from './types';
import { sourceKindLabel } from './sourceLabels';
import { COVERAGE_STATUS } from './labels';
import { RichText } from './ui';
import { ic } from './icon';

export function SourceDetails({ source }: { source: Source }) {
  return <p className="lv-source-meta">
    {sourceKindLabel(source)} · 检索于 {new Date(source.retrieved_at).toLocaleDateString('zh-CN')}
    {source.effective_date_candidates?.[0] && ` · 施行日期 ${source.effective_date_candidates[0].date}`} · 版本及适用性待核实
  </p>;
}

/** How the result was reached, kept below the decisions and closed by default. */
export function ReviewDetails({ review, onLocate }: { review: Review; onLocate: (id: string) => void }) {
  const brief = review.transaction_brief;
  const health = review.evidence_health;
  const scenario = review.profile?.scenario;
  const checked = review.coverage.filter(c => ['reviewed', 'not_applicable'].includes(c.status)).length;
  return <section className="lv-appendix" aria-labelledby="legal-appendix-title">
    <div className="lv-section-head"><h2 id="legal-appendix-title">审查依据</h2></div>
    <details className="lv-disclosure">
      <summary>审查范围<span className="lv-summary-count">{checked}/{review.coverage.length}</span></summary>
      <div className="lv-disclosure-body">
        <ul className="lv-coverage">{review.coverage.map(item => <li key={item.rule_id}>
          <strong>{item.title}</strong>
          <span className={`lv-chip ${item.status === 'reviewed' ? 'is-ok' : item.status === 'not_applicable' ? '' : 'is-mid'}`}>{COVERAGE_STATUS[item.status] || item.status}</span>
          {item.status !== 'reviewed' && item.note && <p>{item.note}</p>}
        </li>)}</ul>
        {Object.entries(review.batch_errors || {}).map(([key, value]) => <p key={key} className="lv-note is-warn">{value}</p>)}
        {review.notice && <p className="lv-hint">{review.notice}</p>}
      </div>
    </details>
    {health && <details className="lv-disclosure" open={health.status === 'gaps' || undefined} aria-label="法律检索状态">
      <summary>法律检索<span className="lv-summary-count">{health.topics_with_sources}/{health.queried_topics}</span></summary>
      <div className="lv-disclosure-body">
        {health.status === 'gaps' && <p className="lv-note is-warn">{health.failed_or_empty_topics} 项检索未获取到来源，相关风险无法排除。</p>}
        {review.sources.map(source => <details className="lv-citation" key={source.id}>
          <summary>{source.title}</summary><SourceDetails source={source} />
          <a href={source.url} target="_blank" rel="noreferrer noopener">查看来源<ExternalLink {...ic} size={13} /></a>
        </details>)}
      </div>
    </details>}
    {brief && <details className="lv-disclosure" open={brief.gaps.length > 0 || undefined} aria-label="交易背景与资料缺口">
      <summary>交易信息{brief.gaps.length > 0 && <span className="lv-summary-count is-warn">{brief.gaps.length} 项缺口</span>}</summary>
      <div className="lv-disclosure-body">
        <dl className="lv-facts-grid">
          <div><dt>履行阶段</dt><dd>{brief.context.performance_stage || '未知'}</dd></div>
          <div><dt>附件情况</dt><dd>{brief.context.attachments_status || '未知'}</dd></div>
          <div><dt>审查侧重</dt><dd>{brief.context.business_priority || '综合审查'}</dd></div>
          <div><dt>交易金额</dt><dd>{brief.context.deal_value == null ? '—' : `${brief.context.deal_value} ${brief.context.currency}`}</dd></div>
        </dl>
        {brief.gaps.map(gap => <p className="lv-note is-warn" key={gap.code}>{gap.message}</p>)}
        {brief.material_references.map(ref => <button className="lv-clause-link" key={ref.block_id} onClick={() => onLocate(ref.block_id)}><RichText text={ref.quote} /></button>)}
      </div>
    </details>}
    {scenario && <details className="lv-disclosure" aria-label="本轮场景清单">
      <summary>审查场景<span className="lv-summary-count">{scenario.label} · {review.profile?.our_role}</span></summary>
      <div className="lv-disclosure-body">
        <ul className="lv-plain-list">{scenario.checks.map(check => <li key={check.id}>{check.title}</li>)}</ul>
        <p className="lv-hint">建议核对：{scenario.materials.join('、')}</p>
      </div>
    </details>}
  </section>;
}
