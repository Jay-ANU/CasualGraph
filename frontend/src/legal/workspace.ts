import type { Block, Contract, Decision, Finding, Review } from './types';
import { findingStatus } from './findingStatus';
import { findingTone } from './labels';
import type { Tone } from './labels';
import { diffText } from './diff';
import { truncateText } from './text';

/**
 * Layout logic for the document desk: which stage the contract is in, how
 * findings are numbered on the paper, the clause outline, and how a
 * paragraph's text splits into marked runs. Pure, so it is unit tested.
 */

export type Stage = 'redaction' | 'setup' | 'running' | 'results' | 'export';
/** Which rail a finished review shows; set by the stepper and the rail's own links. */
export type DeskView = 'work' | 'setup' | 'export';

export const STEP_LABELS = ['脱敏', '设置', '审查', '处理', '导出'] as const;
const STEP_OF: Record<Stage, number> = { redaction: 0, setup: 1, running: 2, results: 3, export: 4 };
export const stepOf = (stage: Stage) => STEP_OF[stage];

export const isActive = (r: Pick<Review, 'status'> | null | undefined) => Boolean(r && ['queued', 'running'].includes(r.status));
export const isDone = (r: Pick<Review, 'status'> | null | undefined) => Boolean(r && ['completed', 'partial'].includes(r.status));

export function deskStage(contract: Pick<Contract, 'status'>, review: Pick<Review, 'status'> | null, view: DeskView): Stage {
  if (contract.status === 'redaction_pending') return 'redaction';
  if (!review) return 'setup';
  if (isActive(review)) return 'running';
  if (view === 'setup') return 'setup';
  if (view === 'export' && isDone(review)) return 'export';
  return 'results';
}

export type Numbered = { finding: Finding; n: number };

/**
 * Open findings in reading order (paragraph, then position of the quote), numbered
 * from 1. Numbers never change when a decision is made, so the paper, the outline
 * and the rail always agree. Findings the critic rejected are kept apart, unnumbered.
 */
export function numberFindings(findings: Finding[], blocks: Block[]): { open: Numbered[]; excluded: Finding[] } {
  const order = new Map(blocks.map((b, i) => [b.id, i]));
  const text = new Map(blocks.map(b => [b.id, b.text]));
  const place = (f: Finding) => {
    const at = f.block_id ? order.get(f.block_id) : undefined;
    if (at === undefined) return [Number.MAX_SAFE_INTEGER, 0];
    const quote = f.original_quote?.trim();
    const offset = quote ? (text.get(f.block_id!) || '').indexOf(quote) : -1;
    return [at, offset < 0 ? 0 : offset];
  };
  const open = findings.map((finding, index) => ({ finding, index, key: place(finding) }))
    .filter(x => findingStatus(x.finding) !== 'rejected')
    .sort((a, b) => a.key[0] - b.key[0] || a.key[1] - b.key[1] || a.index - b.index)
    .map((x, i) => ({ finding: x.finding, n: i + 1 }));
  return { open, excluded: findings.filter(f => findingStatus(f) === 'rejected') };
}

export type ToneFilter = 'all' | Exclude<Tone, 'excluded'>;
export const TONE_FILTERS: ToneFilter[] = ['all', 'high', 'mid', 'low', 'unconfirmed'];

export function toneCounts(open: Numbered[]): Record<ToneFilter, number> {
  const counts: Record<ToneFilter, number> = { all: open.length, high: 0, mid: 0, low: 0, unconfirmed: 0 };
  for (const { finding } of open) {
    const tone = findingTone(finding);
    if (tone !== 'excluded') counts[tone]++;
  }
  return counts;
}

export const filterByTone = (open: Numbered[], tone: ToneFilter) => tone === 'all' ? open : open.filter(x => findingTone(x.finding) === tone);

/** A decision that settles a finding for navigation: adopted, kept as is, or saved as a human revision. */
export const isDecided = (d?: Decision) => Boolean(d && d.decision !== 'pending');
/** Adopted or saved as a human revision: these reach the revised draft. */
export const isRevised = (d?: Decision) => Boolean(d && ['accepted', 'draft'].includes(d.decision));

export type MarkerState = 'open' | 'prelim' | 'revised' | 'kept';

/** How a finding's number is drawn: preliminary while the review runs, then by the reviewer's decision. */
export function markerState(decision: Decision | undefined, running: boolean): MarkerState {
  if (running) return 'prelim';
  if (isRevised(decision)) return 'revised';
  return decision?.decision === 'rejected' ? 'kept' : 'open';
}

/** J / K: the neighbour in the visible list, staying put at either end. */
export function stepFinding(ids: string[], current: string | null, delta: 1 | -1): string | null {
  if (!ids.length) return null;
  const i = current ? ids.indexOf(current) : -1;
  if (i < 0) return ids[delta > 0 ? 0 : ids.length - 1];
  return ids[Math.min(ids.length - 1, Math.max(0, i + delta))];
}

/** After a decision: the next undecided finding below, else the first one above, else stay. */
export function nextUndecided(ids: string[], decisions: Record<string, Decision>, current: string): string {
  const i = ids.indexOf(current);
  const open = (id: string) => id !== current && !isDecided(decisions[id]);
  return ids.slice(i + 1).find(open) || ids.slice(0, Math.max(0, i)).find(open) || current;
}

export type ClauseName = { no: string; name: string };
const CLAUSE_NO = /^(第[一二三四五六七八九十百千零〇两\d]+[条章节款]|[一二三四五六七八九十]+(?=[、.．])|\d+(?:\.\d+)+|\d+(?=[、.．]))/;

/** “第二条 价款与支付：……” → { no: 第二条, name: 价款与支付 }; null when the line is not a clause heading. */
export function clauseName(line: string): ClauseName | null {
  const text = line.trim();
  const match = text.match(CLAUSE_NO);
  if (!match) return null;
  const rest = text.slice(match[1].length).replace(/^[\s、.．:：]+/, '');
  const cut = rest.search(/[：:。；;，,]/);
  return { no: match[1], name: truncateText((cut > 0 ? rest.slice(0, cut) : cut === 0 ? '' : rest).trim(), 12) };
}

export type OutlineEntry = ClauseName & { id: string; blockIds: string[]; kind: 'clause' | 'preamble' | 'paragraph' };

/**
 * One entry per clause heading, holding the paragraphs up to the next heading;
 * paragraphs before the first heading form the “首部”. A contract without any
 * headings lists its paragraphs instead.
 */
export function clauseOutline(blocks: Block[]): OutlineEntry[] {
  const entries: OutlineEntry[] = [];
  let current: OutlineEntry | null = null;
  for (const block of blocks) {
    const heading = clauseName(block.text.split('\n')[0]);
    if (heading) { current = { ...heading, id: block.id, blockIds: [block.id], kind: 'clause' }; entries.push(current); }
    else if (current) current.blockIds.push(block.id);
    else { current = { no: '首部', name: '当事人', id: block.id, blockIds: [block.id], kind: 'preamble' }; entries.push(current); }
  }
  if (entries.some(e => e.kind === 'clause')) return entries;
  return blocks.map((b, i) => ({ id: b.id, blockIds: [b.id], kind: 'paragraph', no: `${i + 1}`, name: truncateText(b.text.split('\n')[0].trim(), 12) }));
}

/** How the rail names the place a finding sits: “第二条”, “2.1 付款安排”, “首部”, “第 3 段” or “全文”. */
export function placeLabel(entries: OutlineEntry[], blockId: string | null): string {
  const entry = blockId ? entries.find(e => e.blockIds.includes(blockId)) : undefined;
  if (!entry) return '全文';
  if (entry.kind === 'preamble') return '首部';
  if (entry.kind === 'paragraph') return `第 ${entry.no} 段`;
  return entry.no.startsWith('第') ? entry.no : `${entry.no} ${entry.name}`.trim();
}

export type Run = { text: string; finding?: Finding; party?: string; heading?: boolean };

/**
 * A paragraph cut into runs: quoted passages carry their finding (or a party
 * candidate its quote), and the clause heading line is flagged so it can be set
 * in bold. Overlapping quotes keep the earlier one; unmatched quotes mark nothing.
 */
export function paragraphRuns(text: string, marks: { quote: string; finding?: Finding; party?: string }[], headingEnd = 0): Run[] {
  const ranges = marks.map(m => {
    const quote = m.quote.trim();
    const start = quote ? text.indexOf(quote) : -1;
    return { ...m, start, end: start + quote.length };
  }).filter(r => r.start >= 0).sort((a, b) => a.start - b.start);
  const runs: Run[] = [];
  let at = 0;
  const push = (end: number, extra: Omit<Run, 'text'> = {}) => {
    // A run crossing the end of the heading line splits so only the heading is bold.
    for (const [from, to, heading] of [[at, Math.min(end, headingEnd), true], [Math.max(at, headingEnd), end, false]] as const) {
      if (to > from) runs.push({ text: text.slice(from, to), ...extra, ...(heading ? { heading } : {}) });
    }
    at = end;
  };
  for (const range of ranges) {
    if (range.start < at) continue;
    push(range.start);
    push(range.end, range.finding ? { finding: range.finding } : { party: range.party });
  }
  push(text.length);
  return runs;
}

/** Where the bold clause heading ends, when the paragraph opens with a heading line of its own. */
export function headingEnd(text: string): number {
  const newline = text.indexOf('\n');
  return newline > 0 && clauseName(text.slice(0, newline)) ? newline : 0;
}

const TOKEN = /【(?:补充)?脱敏\d+】/g;
export type TokenRow = { token: string; blockId: string; value?: string };

/**
 * Redaction placeholders in first-appearance order, with where each first
 * appears. With the original text loaded, a placeholder that the diff replaces
 * by exactly one run also gets that original value.
 */
export function redactionTokens(blocks: Block[], originals?: Block[] | null): TokenRow[] {
  const rows = new Map<string, TokenRow>();
  for (const block of blocks) for (const match of block.text.matchAll(TOKEN)) {
    if (!rows.has(match[0])) rows.set(match[0], { token: match[0], blockId: block.id });
  }
  if (originals) {
    for (const block of blocks) {
      const original = originals.find(o => o.id === block.id)?.text;
      if (!original) continue;
      const parts = diffText(block.text, original);
      parts.forEach((part, i) => {
        const next = parts[i + 1];
        const row = rows.get(part.text.trim());
        if (part.kind === 'del' && row && !row.value && next?.kind === 'ins' && next.text.trim()) row.value = next.text.trim();
      });
    }
  }
  return [...rows.values()];
}

/** Paragraphs grouped into sheets by page number; paragraphs without a page stay on the sheet before them. */
export function pagesOf(blocks: Block[]): { page: number | null; blocks: Block[] }[] {
  const pages: { page: number | null; blocks: Block[] }[] = [];
  for (const block of blocks) {
    const last = pages[pages.length - 1];
    if (last && (block.page == null || last.page == null || block.page === last.page)) {
      last.blocks.push(block);
      if (last.page == null && block.page != null) last.page = block.page;
    } else pages.push({ page: block.page ?? null, blocks: [block] });
  }
  return pages;
}
