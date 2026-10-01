import { ExternalLink } from 'lucide-react';
import type { Review, Source } from './types';
import { sourceKindLabel } from './sourceLabels';
import { coverageStatusLabel, failedSteps } from './labels';
import { RichText } from './ui';
import { ic } from './icon';
import { useI18n } from '../i18n/core';
import { plural, serverText } from './i18n';

export function SourceDetails({ source }: { source: Source }) {
  const { lang, tx } = useI18n();
  const retrieved = lang === 'en' ? new Date(source.retrieved_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
    : new Date(source.retrieved_at).toLocaleDateString('zh-CN');
  const effective = source.effective_date_candidates?.[0];
  return <p className="lv-source-meta">
    {sourceKindLabel(source)}{tx(` · 检索于 ${retrieved}`, ` · retrieved ${retrieved}`)}
    {effective && tx(` · 施行日期 ${effective.date}`, ` · in force from ${effective.date}`)}{tx(' · 版本及适用性待核实', ' · version and applicability to verify')}
  </p>;
}

const COVERAGE_TONE: Record<string, string> = { reviewed: 'is-ok', not_applicable: '', needs_information: 'is-mid', not_reviewed: 'is-high' };

/** How the result was reached: scope, legal research, the transaction as stated, scenario and skills. */
export function ReviewDetails({ review, onLocate }: { review: Review; onLocate: (id: string) => void }) {
  const { tx, t } = useI18n();
  const brief = review.transaction_brief;
  const health = review.evidence_health;
  const scenario = review.profile?.scenario;
  const checked = review.coverage.filter(c => ['reviewed', 'not_applicable'].includes(c.status)).length;
  const skipped = review.research?.status === 'skipped';
  return <div className="lv-basis-panel">
    <section className="lv-basis-group" aria-label={tx('审查范围', 'Review scope')}>
      <div className="lv-rail-label"><span>{tx('审查范围', 'Review scope')}</span><span className="lv-mono">{checked}/{review.coverage.length}</span></div>
      <ul className="lv-plain-rows">{review.coverage.map(item => <li key={item.rule_id}>
        <span className="lv-row-main">{serverText(item.title)}</span>
        <span className={`lv-row-state ${COVERAGE_TONE[item.status] ?? 'is-mid'}`}>{coverageStatusLabel(item.status)}</span>
        {item.status !== 'reviewed' && item.note && <p className="lv-row-note">{serverText(item.note)}</p>}
      </li>)}</ul>
      {failedSteps(review).map(step => <p key={step.id} className="lv-note is-warn"><strong>{tx(`未完成 · ${step.title}`, `Not finished · ${step.title}`)}</strong>{step.message}</p>)}
    </section>
    {health && <section className="lv-basis-group" aria-label={tx('法律检索状态', 'Legal research status')}>
      <div className="lv-rail-label"><span>{tx('法律检索', 'Legal research')}</span>
        <span className="lv-mono">{skipped ? tx('本档位不检索', 'Not searched at this depth') : `${health.topics_with_sources}/${health.queried_topics}`}</span></div>
      {skipped && <p className="lv-hint">{tx('本档位不检索法规；意见引用的法条标注为“模型引用，待核对”。', 'This depth does not research the law; laws cited in findings are marked “model-cited, to verify”.')}</p>}
      {health.status === 'gaps' && <p className="lv-note is-warn">{tx(`${health.failed_or_empty_topics} 项检索未获取到来源，相关风险无法排除。`,
        `${plural(health.failed_or_empty_topics, 'search', 'searches')} found no source, so the related risks cannot be ruled out.`)}</p>}
      {(review.research?.issues?.length || 0) > 0 && <ul className="lv-plain-list" aria-label={tx('检索规划', 'Research plan')}>{review.research!.issues.map(issue => <li key={issue.key}>
        {issue.issue}{issue.laws.length > 0 && `（${issue.laws.map(law => law.name + (law.articles.length ? ' ' + law.articles.join('、') : '')).join('；')}）`}
      </li>)}</ul>}
      {review.sources.map(source => <details className="lv-citation" key={source.id}>
        <summary>{source.title}</summary><SourceDetails source={source} />
        <a href={source.url} target="_blank" rel="noreferrer noopener">{tx('查看来源', 'View source')}<ExternalLink {...ic} size={13} /></a>
      </details>)}
    </section>}
    {brief && <section className="lv-basis-group" aria-label={tx('交易背景与资料缺口', 'Transaction context and gaps')}>
      <div className="lv-rail-label"><span>{tx('交易信息', 'Transaction details')}</span>
        {brief.gaps.length > 0 && <span className="lv-mono is-warn">{tx(`${brief.gaps.length} 项缺口`, plural(brief.gaps.length, 'gap'))}</span>}</div>
      <dl className="lv-facts">
        <div><dt>{tx('履行阶段', 'Performance stage')}</dt><dd>{t(brief.context.performance_stage || '未知')}</dd></div>
        <div><dt>{tx('附件情况', 'Attachments')}</dt><dd>{t(brief.context.attachments_status || '未知')}</dd></div>
        <div><dt>{tx('审查侧重', 'Business priority')}</dt><dd>{t(brief.context.business_priority || '综合审查')}</dd></div>
        <div><dt>{tx('交易金额', 'Amount')}</dt><dd>{brief.context.deal_value == null ? '—' : `${brief.context.deal_value} ${brief.context.currency}`}</dd></div>
      </dl>
      {brief.gaps.map(gap => <p className="lv-note is-warn" key={gap.code}>{serverText(gap.message)}</p>)}
      {brief.material_references.map(ref => <button className="lv-clause-link" key={ref.block_id} onClick={() => onLocate(ref.block_id)}><RichText text={ref.quote} /></button>)}
    </section>}
    {scenario && <section className="lv-basis-group" aria-label={tx('本轮场景清单', 'Scenario checklist')}>
      <div className="lv-rail-label"><span>{tx('审查场景', 'Scenario')}</span><span>{t(scenario.label)} · {review.profile?.our_role && t(review.profile.our_role)}</span></div>
      <ul className="lv-plain-rows">{scenario.checks.map(check => <li key={check.id}><span className="lv-row-main">{serverText(check.title)}</span></li>)}</ul>
      <p className="lv-hint">{tx(`建议核对：${scenario.materials.join('、')}`, `Check against: ${scenario.materials.map(m => serverText(m)).join('; ')}`)}</p>
    </section>}
    {(review.skills?.length || 0) > 0 && <section className="lv-basis-group" aria-label={tx('审查技能', 'Review skills')}>
      <div className="lv-rail-label"><span>{tx('审查技能', 'Review skills')}</span><span className="lv-mono">{review.skills!.length}</span></div>
      <ul className="lv-plain-list">{review.skills!.map(skill => <li key={skill.id}>
        <strong>{serverText(skill.name)}</strong>{tx(`（v${skill.version}）：`, ` (v${skill.version}): `)}{serverText(skill.reason)}
        {skill.source?.origin === 'adapted' && skill.source.repo && <span className="lv-hint">{tx(`；改编自 ${skill.source.repo.replace('https://github.com/', '')}（${skill.source.license}）`,
          `; adapted from ${skill.source.repo.replace('https://github.com/', '')} (${skill.source.license})`)}</span>}
      </li>)}</ul>
      <p className="lv-hint">{tx('审查技能是审查方法与检查清单，不是法律依据。', 'Review skills are methods and checklists, not legal authority.')}</p>
    </section>}
    {review.notice && <p className="lv-hint">{serverText(review.notice)}</p>}
  </div>;
}
