import { currentLang, pick, registerEnglish, tr, type Lang } from '../i18n/core';
import { LEGAL_EN } from '../i18n/legal.en';

// The desk's dictionary loads with the desk, not with the landing page.
registerEnglish(LEGAL_EN);

/**
 * Language helpers for the contract desk. Interface copy is written as a Chinese and
 * English pair next to each other; Chinese that arrives as data (catalogue values, the
 * review service's fixed messages) goes through the dictionary in i18n/legal.en.ts.
 * Contract text, redactions and model output are never translated.
 */

/** One piece of copy in both languages: [中文, English]. */
export type Pair = readonly [zh: string, en: string];

/** The label for a key of a bilingual map in the given language; undefined for unknown keys. */
export function labelOf(map: Record<string, Pair>, key: string, lang: Lang = currentLang()): string | undefined {
  if (!Object.prototype.hasOwnProperty.call(map, key)) return undefined;
  const [zh, en] = map[key];
  return pick(zh, en, lang);
}

/** “1 note”, “3 notes”: English counts with a regular or given plural. */
export const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

/** A dictionary entry, or undefined when the text has none (so callers can tell “unknown” from “same”). */
function known(text: string): string | undefined {
  const en = tr(text, 'en');
  return en === text ? undefined : en;
}

/**
 * A list the service joins with “、” or “；” (rule titles contain “、” themselves), in English
 * when every item is known; otherwise the original, so nothing is half guessed.
 */
function titleList(text: string, separator: string): string {
  const memo = new Map<number, string[] | null>();
  const from = (start: number): string[] | null => {
    if (memo.has(start)) return memo.get(start)!;
    let found: string[] | null = null;
    // Longest known title first, then the rest of the list after the separator.
    for (let end = text.length; end > start && !found; end--) {
      if (end < text.length && !text.startsWith(separator, end)) continue;
      const en = known(text.slice(start, end));
      if (en === undefined) continue;
      if (end === text.length) found = [en];
      else {
        const rest = from(end + separator.length);
        if (rest) found = [en, ...rest];
      }
    }
    memo.set(start, found);
    return found;
  };
  return from(0)?.join('; ') ?? text;
}

const AGENT_TITLE = /^(?:法律风险审查|公司利益审查|公司规范审查|证据与覆盖复核|全文协调与冲突检查)$/;
const REVIEW_LABEL: Record<string, string> = { 极速审查: 'Ultra-fast review', 快速审查: 'Fast review', 本轮检查: 'Review', 协作检查: 'Team review' };
const REVIEW_SCOPE: Record<string, string> = {
  '': '',
  '（未做法规检索和独立复核）': ' (no legal research or independent verification)',
  '（已逐项复核，未做法规检索和全文交叉核对）': ' (findings verified; no legal research or whole-contract cross-check)',
};
const SEARCH_NAME: Record<string, string> = { 公开搜索: 'public web search' };

type Rule = [RegExp, (m: RegExpMatchArray) => string | null];

/** Messages the service builds from a fixed frame and titles or counts. Anchored, so nothing else matches. */
const RULES: Rule[] = [
  [/^正在分项审查：(.+)$/s, m => `Reviewing: ${titleList(m[1], '、')}`],
  [/^正在审查：(.+)$/s, m => `Reviewing: ${titleList(m[1], '、')}`],
  [/^正在检索：(.+)$/s, m => `Searching: ${titleList(m[1], '、')}`],
  [/^法律资料检索：(.+)$/s, m => `Legal research: ${titleList(m[1], '、')}`],
  [/^分项审查已完成 (\d+)\/(\d+) 项(，正在复核其余各项|，其余各项审查中)?$/, m =>
    `Item review: ${m[1]}/${m[2]} finished${m[3] ? m[3].includes('复核') ? '; verifying the rest' : '; reviewing the rest' : ''}`],
  [/^已规划法律检索：(\d+) 个问题，正在通过 (.+) 检索$/, m =>
    `Legal research planned: ${plural(Number(m[1]), 'issue')}, searching with ${SEARCH_NAME[m[2]] ?? m[2]}`],
  [/^多个审查 Agent 正在分别检查合同（已完成 (\d+)\/(\d+) 项）$/, m => `Review agents are checking the contract (${m[1]}/${m[2]} done)`],
  [/^(极速审查|快速审查|本轮检查|协作检查)部分完成：(\d+) 个步骤未完成，可重试；已完成的意见可先处理$/, m =>
    `${REVIEW_LABEL[m[1]]} partly finished: ${plural(Number(m[2]), 'step')} did not finish and can be retried; you can work on the finished findings now`],
  [/^(极速审查|快速审查|本轮检查|协作检查)部分完成：部分规则未完成审查，请查看覆盖缺口$/, m =>
    `${REVIEW_LABEL[m[1]]} partly finished: some checks did not finish; see the coverage gaps`],
  [/^(极速审查|快速审查|本轮检查|协作检查)完成，请逐项确认；(\d+) 个法律问题未取得官方原文，可重新检索$/, m =>
    `${REVIEW_LABEL[m[1]]} finished; confirm each finding. No official text for ${plural(Number(m[2]), 'legal issue')}; you can search again`],
  [/^(极速审查|快速审查|本轮检查|协作检查)完成(（[^）]*）)?，其中 (\d+) 项意见需人工确认$/, m => m[2] && !(m[2] in REVIEW_SCOPE) ? null
    : `${REVIEW_LABEL[m[1]]} finished${REVIEW_SCOPE[m[2] || '']}; ${plural(Number(m[3]), 'finding')} need${m[3] === '1' ? 's' : ''} your confirmation`],
  [/^(极速审查|快速审查|本轮检查|协作检查)完成(（[^）]*）)?，请逐项确认$/, m => m[2] && !(m[2] in REVIEW_SCOPE) ? null
    : `${REVIEW_LABEL[m[1]]} finished${REVIEW_SCOPE[m[2] || '']}; confirm each finding`],
  // Agent notes while a team review runs.
  [/^第 (\d+)\/(\d+) 项：(.+)$/s, m => `Item ${m[1]}/${m[2]}: ${titleList(m[3], '、')}`],
  [/^复核([^：]+)：(.+)$/s, m => AGENT_TITLE.test(m[1]) ? `Verifying ${known(m[1])}: ${titleList(m[2], '、')}` : null],
  [/^核对 (\d+) 项拟议修改能否同时成立$/, m => `Checking that ${plural(Number(m[1]), 'proposed edit')} can stand together`],
  // Step titles (“分项审查：A；B”) and coverage titles (“法律风险审查 / A”).
  [/^([^：]+)：(.+)$/s, m => AGENT_TITLE.test(m[1]) || m[1] === '分项审查' ? `${known(m[1])}: ${titleList(m[2], '；')}` : null],
  [/^([^/]+) \/ (.+)$/s, m => AGENT_TITLE.test(m[1]) ? `${known(m[1])} / ${known(m[2]) ?? m[2]}` : null],
  // Why a review skill was loaded: “通用审查方法；合同场景：采购合同；合同涉及：…”.
  [/^(?:通用审查方法|合同场景：[^；]+|合同涉及：[^；]+)(?:；(?:通用审查方法|合同场景：[^；]+|合同涉及：[^；]+))*$/, m => m[0].split('；').map(part =>
    part === '通用审查方法' ? 'General review method'
      : part.startsWith('合同场景：') ? `Contract type: ${known(part.slice(5)) ?? part.slice(5)}`
      : `Contract mentions: ${part.slice(5)}`).join('; ')],
  [/^意见提到的(.+)未见于合同原文、所附依据或所列法条，请核对后再采纳。$/s, m =>
    `The finding mentions ${m[1]}, which is not in the contract, the attached sources or the cited laws. Check before adopting it.`],
  [/^第 (\d+) 页未提取到文字，可能为扫描页；请提供可复制文字的 PDF 或 DOCX。$/, m =>
    `No text was found on page ${m[1]}; it may be a scan. Provide a PDF with selectable text, or a DOCX.`],
  [/^YData 请求失败（HTTP (\d+)），请检查网关及所选模型的聊天接口支持。$/, m =>
    `The YData request failed (HTTP ${m[1]}). Check the gateway and that the selected model supports chat.`],
  [/^(.+) 模型尚未配置 YData Key，请管理员配置 (.+)。$/, m => `No YData key is configured for ${m[1]} models. Ask an administrator to set ${m[2]}.`],
];

/**
 * Text the review service sends (stages, agent notes, step and coverage titles, gaps,
 * errors) in the current language. Exact messages come from the dictionary, messages
 * with counts and titles from the frames above; anything else is shown as sent.
 */
export function serverText(text: string | null | undefined, lang: Lang = currentLang()): string {
  if (!text || lang !== 'en') return text || '';
  const exact = known(text);
  if (exact !== undefined) return exact;
  for (const [pattern, render] of RULES) {
    const match = text.match(pattern);
    const out = match && render(match);
    if (out) return out;
  }
  return text;
}
