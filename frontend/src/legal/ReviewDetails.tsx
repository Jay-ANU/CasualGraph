import { ExternalLink } from 'lucide-react';
import type { Review, Source } from './types';
import { sourceKindLabel } from './sourceLabels';
import { COVERAGE_STATUS, failedSteps, noSearchReason, SEARCH_NAME, SEARCH_STATE } from './labels';
import { RichText } from './ui';
import { ic } from './icon';

export function SourceDetails({ source }: { source: Source }) {
  return <p className="lv-source-meta">
    {sourceKindLabel(source)} · 检索于 {new Date(source.retrieved_at).toLocaleDateString('zh-CN')}
    {source.effective_date_candidates?.[0] && ` · 施行日期 ${source.effective_date_candidates[0].date}`} · 版本及适用性待核实
  </p>;
}

const COVERAGE_TONE: Record<string, string> = { reviewed: 'is-ok', not_applicable: '', needs_information: 'is-mid', not_reviewed: 'is-high' };

/** How the result was reached: scope, legal research, the transaction as stated, scenario and skills. */
export function ReviewDetails({ review, searchProvider, onLocate }: {
  review: Review;
  /** The search service configured now, which may differ from the one this review used. */
  searchProvider?: string;
  onLocate: (id: string) => void;
}) {
  const brief = review.transaction_brief;
  const health = review.evidence_health;
  const scenario = review.profile?.scenario;
  const checked = review.coverage.filter(c => ['reviewed', 'not_applicable'].includes(c.status)).length;
  const skipped = review.research?.status === 'skipped' && review.research.reason === 'tier';
  const searches = review.retrieval || [];
  const used = searches.find(x => SEARCH_NAME[x.provider])?.provider;
  const provider = SEARCH_NAME[used || searchProvider || ''];
  const unsearched = noSearchReason(review);
  return <div className="lv-basis-panel">
    <section className="lv-basis-group" aria-label="审查范围">
      <div className="lv-rail-label"><span>审查范围</span><span className="lv-mono">{checked}/{review.coverage.length}</span></div>
      <ul className="lv-plain-rows">{review.coverage.map(item => <li key={item.rule_id}>
        <span className="lv-row-main">{item.title}</span>
        <span className={`lv-row-state ${COVERAGE_TONE[item.status] ?? 'is-mid'}`}>{COVERAGE_STATUS[item.status] || item.status}</span>
        {item.status !== 'reviewed' && item.note && <p className="lv-row-note">{item.note}</p>}
      </li>)}</ul>
      {failedSteps(review).map(step => <p key={step.id} className="lv-note is-warn"><strong>未完成 · {step.title}</strong>{step.message}</p>)}
    </section>
    {health && <section className="lv-basis-group" aria-label="法律检索状态">
      <div className="lv-rail-label"><span>法律检索</span>
        <span className="lv-mono">{skipped ? '本档位不检索' : [provider, `${health.topics_with_sources}/${health.queried_topics}`].filter(Boolean).join(' · ')}</span></div>
      {unsearched && <p className={unsearched.warn ? 'lv-note is-warn' : 'lv-hint'}>{unsearched.text}</p>}
      {used && searchProvider && used !== searchProvider && SEARCH_NAME[searchProvider] && <p className="lv-hint">
        本次检索使用 {SEARCH_NAME[used]}；当前已配置 {SEARCH_NAME[searchProvider]}，新建审查或重新检索时生效。</p>}
      {health.status === 'gaps' && <p className="lv-note is-warn">{health.failed_or_empty_topics} 项检索未获取到来源，相关风险无法排除。</p>}
      {(review.research?.issues?.length || 0) > 0 && <ul className="lv-plain-rows" aria-label="检索规划">{review.research!.issues.map(issue => {
        const found = searches.find(x => x.rule_id === issue.key);
        const state = found ? SEARCH_STATE[found.status] ?? { label: found.status, tone: 'is-mid' } : { label: '未检索', tone: '' };
        return <li key={issue.key}>
          <span className="lv-row-main">{issue.issue}{issue.laws.length > 0 && `（${issue.laws.map(law => law.name + (law.articles.length ? ' ' + law.articles.join('、') : '')).join('；')}）`}</span>
          <span className={`lv-row-state ${state.tone}`}>{state.label}</span>
          {found && found.status !== 'retrieved' && found.warnings[0] && <p className="lv-row-note">{found.warnings[0]}</p>}
        </li>;
      })}</ul>}
      {review.sources.map(source => <details className="lv-citation" key={source.id}>
        <summary>{source.title}</summary><SourceDetails source={source} />
        <a href={source.url} target="_blank" rel="noreferrer noopener">查看来源<ExternalLink {...ic} size={13} /></a>
      </details>)}
    </section>}
    {brief && <section className="lv-basis-group" aria-label="交易背景与资料缺口">
      <div className="lv-rail-label"><span>交易信息</span>{brief.gaps.length > 0 && <span className="lv-mono is-warn">{brief.gaps.length} 项缺口</span>}</div>
      <dl className="lv-facts">
        <div><dt>履行阶段</dt><dd>{brief.context.performance_stage || '未知'}</dd></div>
        <div><dt>附件情况</dt><dd>{brief.context.attachments_status || '未知'}</dd></div>
        <div><dt>审查侧重</dt><dd>{brief.context.business_priority || '综合审查'}</dd></div>
        <div><dt>交易金额</dt><dd>{brief.context.deal_value == null ? '—' : `${brief.context.deal_value} ${brief.context.currency}`}</dd></div>
      </dl>
      {brief.gaps.map(gap => <p className="lv-note is-warn" key={gap.code}>{gap.message}</p>)}
      {brief.material_references.map(ref => <button className="lv-clause-link" key={ref.block_id} onClick={() => onLocate(ref.block_id)}><RichText text={ref.quote} /></button>)}
    </section>}
    {scenario && <section className="lv-basis-group" aria-label="本轮场景清单">
      <div className="lv-rail-label"><span>审查场景</span><span>{scenario.label} · {review.profile?.our_role}</span></div>
      <ul className="lv-plain-rows">{scenario.checks.map(check => <li key={check.id}><span className="lv-row-main">{check.title}</span></li>)}</ul>
      <p className="lv-hint">建议核对：{scenario.materials.join('、')}</p>
    </section>}
    {(review.skills?.length || 0) > 0 && <section className="lv-basis-group" aria-label="审查技能">
      <div className="lv-rail-label"><span>审查技能</span><span className="lv-mono">{review.skills!.length}</span></div>
      <ul className="lv-plain-list">{review.skills!.map(skill => <li key={skill.id}>
        <strong>{skill.name}</strong>（v{skill.version}）：{skill.reason}
        {skill.source?.origin === 'adapted' && skill.source.repo && <span className="lv-hint">；改编自 {skill.source.repo.replace('https://github.com/', '')}（{skill.source.license}）</span>}
      </li>)}</ul>
      <p className="lv-hint">审查技能是审查方法与检查清单，不是法律依据。</p>
    </section>}
    {review.notice && <p className="lv-hint">{review.notice}</p>}
  </div>;
}
