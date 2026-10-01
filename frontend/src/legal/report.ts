import type { Review } from './types';
import { findingStatus } from './findingStatus';
import { sourceKindLabel } from './sourceLabels';
import { coverageStatusLabel, failedSteps, kindLabel, reviewOutcome, tierLabel, tierOf } from './labels';
import { currentLang, pick, tr, type Lang } from '../i18n/core';
import { labelOf, serverText, type Pair } from './i18n';

const STATUS: Record<string, Pair> = {
  completed: ['已完成', 'Finished'], partial: ['部分完成', 'Partly finished'], running: ['进行中', 'In progress'], queued: ['排队中', 'Queued'],
  failed: ['已暂停', 'Paused'], cancelled: ['已停止', 'Stopped'],
};
const OUTCOME: Record<string, Pair> = {
  failed_steps: ['部分完成（有步骤未完成）', 'Partly finished (some steps did not finish)'],
  evidence_gaps: ['已完成（部分法律问题未取得官方原文）', 'Finished (no official text for some legal issues)'],
  to_confirm: ['已完成（部分意见待确认）', 'Finished (some findings to confirm)'],
};
const EVIDENCE: Record<string, Pair> = {
  supported: ['已有依据', 'Supported'], quick: ['极速审查，未经复核', 'Ultra-fast review, not verified'], unconfirmed: ['待核实', 'To verify'], rejected: ['复核已排除', 'Excluded on verification'],
};
const SEVERITY: Record<string, Pair> = { high: ['高风险', 'High risk'], medium: ['中风险', 'Medium risk'], low: ['提示', 'Advisory'] };
const DECISION: Record<string, Pair> = {
  pending: ['待处理', 'Pending'], accepted: ['已纳入修订', 'Included in the revision'], draft: ['手工修改（待复核）', 'Manual edit (to be checked)'], rejected: ['保留原文', 'Original kept'],
};

/** Markdown report built from the export payload; content is escaped, not rendered. Labels follow the interface language. */
const escaped = (value: string) => value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
export function ReviewReport(review: Review, lang: Lang = currentLang()): string {
  const say = (zh: string, en: string) => pick(zh, en, lang);
  const label = (map: Record<string, Pair>, key: string) => labelOf(map, key, lang);
  const server = (text: string) => escaped(serverText(text, lang));
  const severity = (value: string) => label(SEVERITY, value) || value;
  const status = label(OUTCOME, reviewOutcome(review) || '') || label(STATUS, review.status) || review.status;
  const out = [say('# 合同审查报告', '# Contract review report'), '', say(`审查编号：${review.id}`, `Review ID: ${review.id}`), say(`审查状态：${status}`, `Status: ${status}`),
    say(`模型：${review.profile?.model?.id || '历史记录未提供'}`, `Model: ${review.profile?.model?.id || 'not recorded'}`),
    say(`我方角色：${review.profile?.our_role || '未记录'}`, `Our role: ${review.profile?.our_role ? tr(review.profile.our_role, lang) : 'not recorded'}`),
    say(`审查方式：${tierLabel(tierOf(review), lang)}`, `Review depth: ${tierLabel(tierOf(review), lang)}`), '', serverText(review.notice, lang)];
  if (review.profile?.scenario) {
    const scenario = review.profile.scenario;
    out.push('', say('## 审查场景', '## Scenario'), say(`${escaped(scenario.label)} · 目录版本 ${scenario.catalog_version}`, `${escaped(tr(scenario.label, lang))} · catalogue version ${scenario.catalog_version}`),
      escaped(scenario.role_focus || ''), ...scenario.checks.map(c => say(`专项检查：${escaped(c.title)}`, `Scenario check: ${server(c.title)}`)),
      say(`核对材料：${scenario.materials.map(escaped).join('；')}`, `Materials to check: ${scenario.materials.map(server).join('; ')}`), server(scenario.limits));
  }
  if (review.transaction_brief) {
    const b = review.transaction_brief;
    const context = (value: string | undefined, fallback: string) => escaped(tr(value || fallback, lang));
    out.push('', say('## 交易信息（用户提供，未经核实）', '## Transaction details (stated by the user, not verified)'),
      say(`履行阶段：${escaped(b.context.performance_stage || '未知')}`, `Performance stage: ${context(b.context.performance_stage, '未知')}`),
      say(`附件声明：${escaped(b.context.attachments_status || '未知')}`, `Attachments: ${context(b.context.attachments_status, '未知')}`),
      say(`业务重点：${escaped(b.context.business_priority || '综合审查')}`, `Business priority: ${context(b.context.business_priority, '综合审查')}`),
      say(`金额：${escaped(b.context.deal_value == null ? '未提供' : `${b.context.deal_value} ${b.context.currency}`)}`,
        `Amount: ${escaped(b.context.deal_value == null ? 'not given' : `${b.context.deal_value} ${b.context.currency}`)}`));
    for (const gap of b.gaps) out.push('', say(`资料缺口：${escaped(gap.message)}`, `Gap: ${server(gap.message)}`));
  }
  if (review.skills?.length) {
    out.push('', say('## 审查技能', '## Review skills'), ...review.skills.map(skill => say(`${escaped(skill.name)}（v${escaped(skill.version)}）：${escaped(skill.reason)}`,
      `${server(skill.name)} (v${escaped(skill.version)}): ${server(skill.reason)}`)), say('审查技能是审查方法与检查清单，不是法律依据。', 'Review skills are methods and checklists, not legal authority.'));
  }
  if (review.research?.status === 'skipped') out.push('', say('## 法律检索', '## Legal research'), say('本档位不检索法规；法律意见引用的法条为模型引用，待核对。', 'This depth does not research the law; laws cited in legal findings are model-cited and still need checking.'));
  else if (review.evidence_health) {
    const h = review.evidence_health;
    out.push('', say('## 法律检索', '## Legal research'), say(`取得来源：${h.topics_with_sources}/${h.queried_topics} 项；版本待核验：${h.version_pending} 个来源。`,
      `Sources found: ${h.topics_with_sources}/${h.queried_topics}; version to verify: ${h.version_pending} ${h.version_pending === 1 ? 'source' : 'sources'}.`), serverText(h.notice, lang));
  }
  out.push('', say('## 审查意见', '## Findings'));
  for (const [index, f] of review.findings.entries()) {
    const evidence = label(EVIDENCE, findingStatus(f));
    const level = findingStatus(f) === 'supported' ? severity(f.severity)
      : findingStatus(f) === 'quick' ? say(`${severity(f.severity)}（未经复核）`, `${severity(f.severity)} (not verified)`)
      : say('不作为已成立风险计级', 'Not rated as an established risk');
    out.push('', `### ${index + 1}. ${escaped(f.title)}`,
      say(`类别：${kindLabel(f.kind, lang) || f.kind}；依据状态：${evidence}；风险等级：${level}；原文段落：${f.block_id || '待确定插入位置'}`,
        `Category: ${kindLabel(f.kind, lang) || f.kind}; basis: ${evidence}; risk level: ${level}; paragraph: ${f.block_id || 'insertion point to be decided'}`),
      '', say('原文：', 'Original:'), escaped(f.original_quote), '', say('影响：', 'Impact:'), escaped(f.impact), '', say('分析：', 'Analysis:'), escaped(f.reason));
    if (f.agent_title) out.push('', say(`审查维度：${escaped(f.agent_title)}`, `Reviewed by: ${server(f.agent_title)}`));
    if (f.missing_facts.length) out.push('', say('待补充信息：', 'Facts needed:'), ...f.missing_facts.map(escaped));
    for (const ref of f.law_refs || []) {
      const matched = ref.status === 'source_matched';
      out.push('', say(`法条：${escaped(ref.law)}${ref.article ? ' ' + escaped(ref.article) : ''}（${matched ? '已对照官方原文' : '模型引用，待核对'}）${ref.point ? '：' + escaped(ref.point) : ''}`,
        `Law: ${escaped(ref.law)}${ref.article ? ' ' + escaped(ref.article) : ''} (${matched ? 'matched to official text' : 'model-cited, to verify'})${ref.point ? ': ' + escaped(ref.point) : ''}`));
    }
    if (f.verification_note) out.push('', say('复核说明：', 'Verification note:'), server(f.verification_note));
    for (const c of f.citations) {
      const s = review.sources.find(source => source.id === c.source_id);
      if (s) out.push('', say(`依据：${escaped(s.title)}`, `Basis: ${escaped(s.title)}`), escaped(c.supporting_quote), s.url,
        say(`来源类型（规则初筛）：${sourceKindLabel(s, lang)}；检索时间：${s.retrieved_at}；版本和适用性待人工核验。`,
          `Source type (rule-based screen): ${sourceKindLabel(s, lang)}; retrieved: ${s.retrieved_at}; version and applicability to be checked by a person.`));
    }
    for (const id of f.policy_ids) {
      const p = review.policies.find(item => item.id === id);
      if (p) out.push('', say(`公司规范：${escaped(p.title)} v${p.version}`, `Company policy: ${escaped(p.title)} v${p.version}`), escaped(p.text));
    }
    const decision = review.decisions[f.id];
    out.push('', say(`处理决定：${label(DECISION, decision?.decision || 'pending') || decision?.decision}`, `Decision: ${label(DECISION, decision?.decision || 'pending') || decision?.decision}`));
    if (decision?.text || f.suggested_text) out.push('', say('修改后条款：', 'Revised clause:'), escaped(decision?.text || f.suggested_text));
  }
  out.push('', review.draft_approval ? say('修订组合状态：用户已确认精确修改组合（非签署或企业授权审批）', 'Revision status: the user confirmed the exact set of edits (not a signature or corporate approval)')
    : say('修订组合状态：尚未最终确认', 'Revision status: not yet confirmed'), '', say('## 审查范围', '## Review scope'));
  for (const c of review.coverage) out.push('', `### ${server(c.title)} · ${coverageStatusLabel(c.status, lang)}`, server(c.note), server(c.verification_note || ''));
  for (const step of failedSteps(review, lang)) out.push('', say(`未完成：${escaped(step.title)}。${escaped(step.message)}`, `Not finished: ${escaped(step.title)}. ${escaped(step.message)}`));
  out.push('', say('本报告仅供参考，不构成法律意见，亦不保证脱敏质量、法规时效或合同整体安全。Word 修订版含真实信息及删除内容，分享前请复核。',
    'This report is for reference only. It is not legal advice and does not guarantee the quality of the redaction, that the law cited is current, or that the contract as a whole is safe. The tracked-changes Word file contains real information and deleted text; check it before sharing.'), '');
  return out.join('\n');
}
