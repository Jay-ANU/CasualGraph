import type { Block } from './types';

/** Placeholders written by the backend redactor, e.g. 【脱敏1】 and 【补充脱敏2】. */
const TOKEN = /【(?:补充)?脱敏\d+】/g;

export type TextPart = { kind: 'text' | 'redacted'; text: string };

/** Split display text so redaction placeholders can be drawn as redaction marks. */
export function splitRedactions(text: string): TextPart[] {
  const parts: TextPart[] = [];
  let last = 0;
  for (const match of text.matchAll(TOKEN)) {
    const start = match.index ?? 0;
    if (start > last) parts.push({ kind: 'text', text: text.slice(last, start) });
    parts.push({ kind: 'redacted', text: match[0] });
    last = start + match[0].length;
  }
  if (last < text.length) parts.push({ kind: 'text', text: text.slice(last) });
  return parts;
}

/** Shorten without cutting a redaction placeholder in half. */
export function truncateText(text: string, max: number): string {
  const chars = Array.from(text);
  if (chars.length <= max) return text;
  let cut = chars.slice(0, max).join('');
  const open = cut.lastIndexOf('【');
  if (open > cut.lastIndexOf('】')) cut = cut.slice(0, open);
  // Prefer ending on a natural pause when one is close to the limit.
  const pause = Math.max(cut.lastIndexOf('，'), cut.lastIndexOf('；'), cut.lastIndexOf('。'), cut.lastIndexOf('、'));
  if (pause >= Array.from(cut).length - 6 && pause > 0) cut = cut.slice(0, pause);
  return `${cut.trimEnd()}…`;
}

const HEADING = /^(第[一二三四五六七八九十百千零〇两\d]+[条章节款]|[一二三四五六七八九十]+[、.]|\d+(?:\.\d+)*[、.．])/;

/** A reader-facing name for a paragraph: its clause heading when it has one. */
export function clauseLabel(block: Pick<Block, 'id' | 'text'> | undefined, max = 18): string {
  if (!block) return '';
  const first = block.text.trim().split('\n')[0].trim();
  if (!first) return `第 ${block.id} 段`;
  if (HEADING.test(first)) return truncateText(first, 24);
  return truncateText(first, max);
}

export function isClauseHeading(line: string): boolean {
  return HEADING.test(line.trim());
}

export type PartyCandidate = { blockId: string; quote: string; context?: string };

/** Lines such as “甲方（采购方）：【脱敏1】” or “出租人：……”. */
const PARTY_LINE = /^\s*(?:[甲乙丙丁戊]方|[^\s：:（(，。；]{1,6}[方人])\s*(?:[（(][^）)\n]{1,12}[）)])?\s*[：:]\s*\S/;
const NOT_A_PARTY = /^(?:\s*)(?:法定代表人|联系人|代理人|委托代理人|负责人|经办人|授权代表人|签约代表人|收件人|开户人)/;

/**
 * Verbatim fragments the user can pick as “our party”. The list only quotes the
 * contract; it never decides which side the user is on.
 */
export function partyCandidates(blocks: Block[], limit = 8): PartyCandidate[] {
  const out: PartyCandidate[] = [];
  const seen = new Set<string>();
  const add = (block: Block, quote: string, context?: string) => {
    const value = quote.trim();
    if (value.length < 2 || value.length > 200 || seen.has(value) || !block.text.includes(value)) return;
    seen.add(value);
    out.push(context ? { blockId: block.id, quote: value, context } : { blockId: block.id, quote: value });
  };
  for (const block of blocks) {
    for (const line of block.text.split('\n')) {
      if (out.length >= limit) return out;
      if (line.trim().length <= 60 && PARTY_LINE.test(line) && !NOT_A_PARTY.test(line)) add(block, line);
    }
  }
  // Redacted names that are not already inside a party line, from the opening paragraphs.
  for (const block of blocks.slice(0, 12)) {
    for (const line of block.text.split('\n')) {
      if (NOT_A_PARTY.test(line)) continue;
      for (const match of line.matchAll(TOKEN)) {
        if (out.length >= limit) return out;
        if (!out.some(c => c.quote.includes(match[0]))) add(block, match[0], truncateText(line.trim(), 30));
      }
    }
  }
  return out;
}

/** Fragments inside one chosen paragraph, for the manual fallback. */
export function blockFragments(block: Block | undefined): string[] {
  const found = block?.text.match(/(?:甲方|乙方|丙方|丁方)[^，。；\n]{0,45}|【[^】]{1,30}】/g) || [];
  return [...new Set(found)].filter(text => text.length >= 2);
}
