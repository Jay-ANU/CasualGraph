import { ExternalLink } from 'lucide-react';
import type { Review, Source } from './types';
import { sourceKindLabel } from './sourceLabels';
import { coverageStatusLabel, failedSteps } from './labels';
import { RichText } from './ui';
import { ic } from './icon';
import { useI18n } from '../i18n/core';
import { plural, serverText } from './i18n';
import { ToolList } from './ToolList';
import { legalLookups, toolGroups } from './toolCalls';

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
  const unconfigured = skipped && review.research?.reason === 'not_configured';
  // The model looked up the law itself, with tools, as it reviewed.
  const looked = review.research?.status === 'tools';
  const lookups = legalLookups(review);
  const groups = toolGroups(review);
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
        <span className="lv-mono">{unconfigured ? tx('未配置检索', 'No search service') : skipped ? tx('本档位不检索', 'Not searched at this depth')
          : looked ? tx(`${lookups} 次查阅`, plural(lookups, 'lookup')) : `${health.topics_with_sources}/${health.queried_topics}`}</span></div>
      {skipped && <p className="lv-hint">{unconfigured ? tx('未配置法规检索服务，本轮没有检索；意见引用的法条标注为“模型引用，待核对”。', 'No legal search service is configured, so nothing was searched; laws cited in findings are marked “model-cited, to verify”.')
        : tx('本档位不检索法规；意见引用的法条标注为“模型引用，待核对”。', 'This depth does not research the law; laws cited in findings are marked “model-cited, to verify”.')}</p>}
      {looked && <p className="lv-hint">{lookups ? tx(`模型在审查中按需查阅官方法规原文 ${lookups} 次，取得 ${review.sources.length} 个来源；意见可逐字引用这些原文，没有取得原文的法条标注为“模型引用，待核对”。`,
        `The model looked up official legal text ${plural(lookups, 'time')} as it reviewed and obtained ${plural(review.sources.length, 'source')}; findings can quote them word for word, and laws without official text are marked “model-cited, to verify”.`)
        : tx('模型可以按需检索官方法规原文，本轮没有检索；意见引用的法条标注为“模型引用，待核对”。', 'The model could look up official legal text as needed but did not this time; laws cited in findings are marked “model-cited, to verify”.')}</p>}
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
    {review.tools_offered && <section className="lv-basis-group" aria-label={tx('模型调用的工具', 'Tools the model called')}>
      <div className="lv-rail-label"><span>{tx('模型调用的工具', 'Tools the model called')}</span><span className="lv-mono">{review.tool_calls?.length || 0}</span></div>
      {groups.length ? groups.map(group => <div key={group.label || 'all'}>
        {group.label && <p className="lv-tool-step">{group.label}</p>}
        <ToolList calls={group.calls} label={group.label || tx('模型调用的工具', 'Tools the model called')} />
      </div>) : <p className="lv-hint">{tx('本轮模型没有调用工具。', 'The model did not call any tools this time.')}</p>}
      <p className="lv-hint">{tx('工具由本服务执行：法规检索只发送法规名称和通用法律概念，其他工具不离开本服务。', 'This service runs the tools: legal searches send only statute names and general legal terms, and the other tools never leave the service.')}</p>
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
