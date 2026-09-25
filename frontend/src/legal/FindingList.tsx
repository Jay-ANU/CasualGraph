import { Search } from 'lucide-react';
import type { Block, Finding, Review } from './types';
import { findingStatus } from './findingStatus';
import { KIND_FILTERS } from './labels';
import { FindingCard } from './FindingCard';
import { ic } from './icon';

type Props = {
  review: Review; findings: Finding[]; blocks: Block[]; busy: boolean; active: boolean;
  kind: string; status: string; query: string;
  onKind: (value: string) => void; onStatus: (value: string) => void; onQuery: (value: string) => void; onClear: () => void;
  onLocate: (id: string) => void; onDecision: (f: Finding, value: string, text: string, legalBasis: boolean, manual: boolean) => void;
};

export function FindingList(p: Props) {
  const open = p.findings.filter(f => findingStatus(f) !== 'rejected');
  const excluded = p.findings.filter(f => findingStatus(f) === 'rejected');
  const card = (f: Finding, first: boolean) => <FindingCard key={`${p.review.id}-${f.id}-${p.review.decisions[f.id]?.version || 0}`} finding={f} review={p.review}
    block={p.blocks.find(b => b.id === f.block_id)} busy={p.busy} initiallyOpen={first} onLocate={p.onLocate}
    onDecision={(value, text, legalBasis, manual) => p.onDecision(f, value, text, legalBasis, manual)} />;
  return <section className="lv-results" id="legal-results" aria-labelledby="legal-results-title">
    <div className="lv-section-head">
      <h2 id="legal-results-title">{p.active ? '已发现的意见' : '逐条意见'}</h2>
      <span>{p.findings.length} 项</span>
    </div>
    <div className="lv-toolbar">
      <div className="lv-segmented" role="group" aria-label="意见类别">
        {KIND_FILTERS.map(([key, label]) => <button key={key} aria-pressed={p.kind === key} className={p.kind === key ? 'selected' : ''} onClick={() => p.onKind(key)}>{label}</button>)}
      </div>
      <div className="lv-toolbar-row">
        <label className="lv-search-field"><Search {...ic} size={15} /><input aria-label="查找审查意见" value={p.query} onChange={e => p.onQuery(e.target.value)} placeholder="搜索条款或意见" /></label>
        <select className="lv-select lv-select-sm" aria-label="处理状态" value={p.status} onChange={e => p.onStatus(e.target.value)}>
          <option value="all">全部状态</option><option value="pending">待处理</option><option value="unconfirmed">待核实</option>
          <option value="accepted">已纳入修订</option><option value="draft">手工修改</option><option value="rejected">已保留原文</option>
        </select>
      </div>
    </div>
    {open.map((f, i) => card(f, i === 0))}
    {excluded.length > 0 && <details className="lv-disclosure lv-excluded">
      <summary>复核后排除的疑点 · {excluded.length}</summary>
      <p className="lv-hint">这些是审查中提出、但复核没有支持的候选意见，列出来供你参考。</p>
      {excluded.map(f => card(f, false))}
    </details>}
    {!p.findings.length && <div className="lv-empty-result">
      <h3>{p.active ? '暂时还没有意见' : '没有符合条件的意见'}</h3>
      <p>{p.active ? '审查仍在进行，发现的问题会陆续出现在这里。' : '换个关键词或清除筛选试试。没有结果不代表没有风险。'}</p>
      {!p.active && <button className="lv-secondary" onClick={p.onClear}>清除筛选</button>}
    </div>}
  </section>;
}
