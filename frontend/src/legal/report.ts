import type { Review } from './types';
import { findingStatus } from './findingStatus';
import { sourceKindLabel } from './sourceLabels';
import { COVERAGE_STATUS, KIND_LABEL, reviewOutcome } from './labels';

const STATUS: Record<string, string> = { completed: '已完成', partial: '部分完成', running: '进行中', queued: '排队中', failed: '已暂停', cancelled: '已停止' };
const OUTCOME: Record<string, string> = { failed_steps: '部分完成（有步骤未完成）', evidence_gaps: '已完成（部分法律问题未取得官方原文）', to_confirm: '已完成（部分意见待确认）' };
const EVIDENCE: Record<string, string> = { supported: '已有依据', unconfirmed: '待核实', rejected: '复核已排除' };
const SEVERITY: Record<string, string> = { high: '高风险', medium: '中风险', low: '提示' };
const DECISION: Record<string, string> = { pending: '待处理', accepted: '已纳入修订', draft: '手工修改（待复核）', rejected: '保留原文' };

/** Markdown report built from the export payload; content is escaped, not rendered. */
const escaped = (value: string) => value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
export function ReviewReport(review: Review): string {
  const out = ['# 合同审查报告', '', `审查编号：${review.id}`, `审查状态：${OUTCOME[reviewOutcome(review) || ''] || STATUS[review.status] || review.status}`, `模型：${review.profile?.model?.id || '历史记录未提供'}`, `我方角色：${review.profile?.our_role || '未记录'}`, `审查方式：${review.profile?.review_mode === 'multi_agent' ? '深度审查（多维度独立检查、交叉复核）' : '标准审查'}`, '', review.notice];
  if (review.profile?.scenario) {
    const scenario = review.profile.scenario;
    out.push('', '## 审查场景', `${escaped(scenario.label)} · 目录版本 ${scenario.catalog_version}`, escaped(scenario.role_focus || ''), ...scenario.checks.map(c => `专项检查：${escaped(c.title)}`), `核对材料：${scenario.materials.map(escaped).join('；')}`, escaped(scenario.limits));
  }
  if (review.transaction_brief) {
    const b = review.transaction_brief;
    out.push('', '## 交易信息（用户提供，未经核实）', `履行阶段：${escaped(b.context.performance_stage || '未知')}`, `附件声明：${escaped(b.context.attachments_status || '未知')}`, `业务重点：${escaped(b.context.business_priority || '综合审查')}`, `金额：${escaped(b.context.deal_value == null ? '未提供' : `${b.context.deal_value} ${b.context.currency}`)}`);
    for (const gap of b.gaps) out.push('', `资料缺口：${escaped(gap.message)}`);
  }
  if (review.evidence_health) out.push('', '## 法律检索', `取得来源：${review.evidence_health.topics_with_sources}/${review.evidence_health.queried_topics} 项；版本待核验：${review.evidence_health.version_pending} 个来源。`, review.evidence_health.notice);
  out.push('', '## 审查意见');
  for (const [index, f] of review.findings.entries()) {
    out.push('', `### ${index + 1}. ${escaped(f.title)}`, `类别：${KIND_LABEL[f.kind] || f.kind}；依据状态：${EVIDENCE[findingStatus(f)]}；风险等级：${findingStatus(f) === 'supported' ? SEVERITY[f.severity] || f.severity : '不作为已成立风险计级'}；原文段落：${f.block_id || '待确定插入位置'}`, '', '原文：', escaped(f.original_quote), '', '影响：', escaped(f.impact), '', '分析：', escaped(f.reason));
    if (f.agent_title) out.push('', `审查维度：${escaped(f.agent_title)}`);
    if (f.missing_facts.length) out.push('', '待补充信息：', ...f.missing_facts.map(escaped));
    for (const ref of f.law_refs || []) out.push('', `法条：${escaped(ref.law)}${ref.article ? ' ' + escaped(ref.article) : ''}（${ref.status === 'source_matched' ? '已对照官方原文' : '模型引用，待核对'}）${ref.point ? '：' + escaped(ref.point) : ''}`);
    if (f.verification_note) out.push('', '复核说明：', escaped(f.verification_note));
    for (const c of f.citations) { const s = review.sources.find(source => source.id === c.source_id); if (s) out.push('', `依据：${escaped(s.title)}`, escaped(c.supporting_quote), s.url, `来源类型（规则初筛）：${sourceKindLabel(s)}；检索时间：${s.retrieved_at}；版本和适用性待人工核验。`); }
    for (const id of f.policy_ids) { const p = review.policies.find(item => item.id === id); if (p) out.push('', `公司规范：${escaped(p.title)} v${p.version}`, escaped(p.text)); }
    const decision = review.decisions[f.id];
    out.push('', `处理决定：${DECISION[decision?.decision || 'pending'] || decision?.decision}`);
    if (decision?.text || f.suggested_text) out.push('', '修改后条款：', escaped(decision?.text || f.suggested_text));
  }
  out.push('', `修订组合状态：${review.draft_approval ? '用户已确认精确修改组合（非签署或企业授权审批）' : '尚未最终确认'}`, '', '## 审查范围');
  for (const c of review.coverage) out.push('', `### ${escaped(c.title)} · ${COVERAGE_STATUS[c.status] || c.status}`, escaped(c.note), escaped(c.verification_note || ''));
  for (const error of Object.values(review.batch_errors || {})) out.push('', `未完成：${escaped(error)}`);
  out.push('', '本报告仅供参考，不构成法律意见，亦不保证脱敏质量、法规时效或合同整体安全。Word 修订版含真实信息及删除内容，分享前请复核。', '');
  return out.join('\n');
}
