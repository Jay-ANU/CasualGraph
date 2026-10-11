import type { Review, ToolCall } from './types';
import { currentLang, pick, type Lang } from '../i18n/core';
import { plural } from './i18n';

/**
 * The tools a chat-style review's model can call, and what each call did, in the reader's language.
 * The service records each call as data (tool, what was asked, status and counts); the words are here.
 */
const ACTION: Record<string, [string, string]> = {
  search_law: ['检索法规', 'Searched the law'],
  read_law_article: ['查阅法条', 'Read an article'],
  find_in_contract: ['查找合同', 'Searched the contract'],
  read_paragraphs: ['读取段落', 'Re-read paragraphs'],
  calculate: ['计算', 'Calculated'],
  date_calc: ['计算日期', 'Counted dates'],
  check_revision: ['核对修改', 'Checked an edit'],
};

/** Tools that look up official legal text. */
export const LEGAL_TOOLS = new Set(['search_law', 'read_law_article']);

export function toolAction(call: Pick<ToolCall, 'name'>, lang: Lang = currentLang()): string {
  const pair = ACTION[call.name];
  return pair ? pick(pair[0], pair[1], lang) : pick('调用工具', 'Called a tool', lang);
}

export type ToolTone = 'running' | 'ok' | 'warn' | 'muted';

/** What came back from one call, in a few words. */
export function toolOutcome(call: ToolCall, lang: Lang = currentLang()): { text: string; tone: ToolTone } {
  const say = (zh: string, en: string) => pick(zh, en, lang);
  const n = call.count ?? 0;
  switch (call.status) {
    case 'running': return { text: say('进行中', 'running'), tone: 'running' };
    case 'ok':
      switch (call.name) {
        case 'search_law': return { text: say(`取得 ${n} 个官方来源`, plural(n, 'official source')), tone: 'ok' };
        case 'read_law_article': return { text: say('已取得官方原文', 'official text found'), tone: 'ok' };
        case 'find_in_contract':
        case 'read_paragraphs': return { text: say(`${n} 段`, plural(n, 'paragraph')), tone: 'ok' };
        case 'calculate':
        case 'date_calc': return { text: call.result ? `= ${call.result}` : say(`相差 ${n} 天`, plural(n, 'day') + ' apart'), tone: 'ok' };
        case 'check_revision': return { text: say('通过', 'passed'), tone: 'ok' };
        default: return { text: say('完成', 'done'), tone: 'ok' };
      }
    case 'empty': return { text: LEGAL_TOOLS.has(call.name) ? say('未取得官方原文', 'no official text found') : say('未找到', 'nothing found'), tone: 'muted' };
    case 'issues': {
      const count = call.problems?.length || 0;
      return { text: say(`未通过 · ${count} 个问题`, `did not pass · ${plural(count, 'problem')}`), tone: 'warn' };
    }
    case 'rejected': return call.reason === 'unsafe'
      ? { text: say('检索词含合同信息，未发出', 'not sent: the query named contract details'), tone: 'warn' }
      : { text: say('请求无效，未执行', 'not run: invalid request'), tone: 'muted' };
    case 'limit': return { text: say('已达上限，未执行', 'not run: limit reached'), tone: 'muted' };
    case 'timeout': return { text: say('超时', 'timed out'), tone: 'warn' };
    default: return { text: say('出错', 'failed'), tone: 'warn' };
  }
}

/** One line for a call, as the activity log shows it. */
export function toolLine(call: ToolCall, lang: Lang = currentLang()): string {
  return toolAction(call, lang) + (call.detail ? pick('：', ': ', lang) + call.detail : '');
}

const STEP: Record<string, [string, string]> = { review: ['通读初审', 'First read'], final: ['复读定稿', 'Re-read'] };

/** A review's tool calls by the answer that made them, in order; one unnamed group when there is only one answer. */
export function toolGroups(review: Pick<Review, 'tool_calls' | 'review_tier'>, lang: Lang = currentLang()): { label: string; calls: ToolCall[] }[] {
  const calls = review.tool_calls || [];
  const steps = [...new Set(calls.map(c => c.step))];
  if (review.review_tier !== 'fast' || steps.length < 2) return calls.length ? [{ label: '', calls }] : [];
  return steps.map(step => ({ label: STEP[step] ? pick(STEP[step][0], STEP[step][1], lang) : step, calls: calls.filter(c => c.step === step) }));
}

/** How many times the model looked up official legal text (calls answered without running excluded). */
export const legalLookups = (review: Pick<Review, 'tool_calls'>) =>
  (review.tool_calls || []).filter(c => LEGAL_TOOLS.has(c.name) && !['limit', 'rejected'].includes(c.status)).length;
