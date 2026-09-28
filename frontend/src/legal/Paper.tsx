import { useI18n } from '../i18n/useI18n';
import { Fragment } from 'react';
import type { ReactNode } from 'react';
import { Columns, FileText } from 'lucide-react';
import type { Block, Contract, Decision } from './types';
import type { PartyCandidate } from './text';
import { diffText } from './diff';
import { fileTitle, findingTone, TONE_LABEL } from './labels';
import type { Numbered, Run, Stage } from './workspace';
import { headingEnd, isRevised, markerState, pagesOf, paragraphRuns } from './workspace';
import { Marker } from './Marker';
import { Redline, RichText } from './ui';
import { ic } from './icon';

type Props = {
  contract: Contract; blocks: Block[]; stage: Stage; decisions: Record<string, Decision>;
  /** Findings drawn on the paper at this stage, already numbered. */
  items: Numbered[]; selected: string | null; located: { id: string; n: number } | null;
  originals: Block[] | null; busy: boolean;
  candidates: PartyCandidate[]; party: { blockId: string; quote: string };
  detail?: string;
  onSelect: (id: string) => void; onParty: (blockId: string, quote: string) => void; onCompare: () => void;
};

const LEGEND = ['high', 'mid', 'low', 'unconfirmed'] as const;

/** Original values in place of the placeholders; shown only while comparing, never sent to a model. */
function Compare({ redacted, original }: { redacted: string; original: string }) {
  const head = redacted.slice(0, headingEnd(redacted));
  const keep = head && original.startsWith(head) ? head : '';
  return <>{keep && <strong className="lv-para-heading">{keep}</strong>}
    {diffText(redacted.slice(keep.length), original.slice(keep.length)).map((part, i) => part.kind === 'same' ? <RichText key={i} text={part.text} />
      : part.kind === 'ins' ? <span key={i} className="lv-original">{part.text}</span> : null)}</>;
}

function Runs({ runs, blockId, selected, running, party, onParty }: {
  runs: Run[]; blockId: string; selected: string | null; running: boolean;
  party: { blockId: string; quote: string }; onParty: (blockId: string, quote: string) => void;
}) {
  const { t } = useI18n();
  return <>{runs.map((run, i) => {
    let node: ReactNode = <RichText text={run.text} />;
    if (run.heading) node = <strong className="lv-para-heading">{node}</strong>;
    if (run.finding) {
      node = <span className={`lv-mark tone-${findingTone(run.finding)}${run.finding.id === selected ? ' is-selected' : ''}${running ? ' is-prelim' : ''}`}>{node}</span>;
    } else if (run.party) {
      const quote = run.party, on = party.blockId === blockId && party.quote === quote;
      node = <button type="button" className={`lv-pick${on ? ' is-on' : ''}`} aria-pressed={on} aria-label={t("在正文中选择我方主体：{0}", { "0": quote })}
        onClick={event => { event.stopPropagation(); onParty(blockId, quote); }}>{node}{on && <span className="lv-pick-tag" aria-hidden="true">{t("我方")}</span>}</button>;
    }
    return <Fragment key={i}>{node}</Fragment>;
  })}</>;
}

/** The contract as paper: findings numbered in the margin, quoted passages marked, adopted edits shown as a redline. */
export function Paper(p: Props) {
  const { t } = useI18n();
  const pages = pagesOf(p.blocks);
  const running = p.stage === 'running';
  const picking = p.stage === 'setup';
  const marking = p.stage === 'results' || running;
  return <section className={`lv-paper-desk stage-${p.stage}`} aria-label={t("合同正文")}>
    <div className="lv-desk-bar">
      <span className="lv-desk-file"><FileText {...ic} size={14} /><span className="lv-desk-name">{p.contract.name}</span>
        <span aria-hidden="true">·</span><span>{p.stage === 'redaction' ? t("自动脱敏") : t("已脱敏")} {p.contract.replacement_count}{' '}{t("处")}</span></span>
      {p.stage === 'redaction' && <button className={`lv-toggle${p.originals ? ' is-on' : ''}`} aria-pressed={Boolean(p.originals)} disabled={p.busy} onClick={p.onCompare}>
        <Columns {...ic} size={14} />{t("对照原件")}</button>}
      {p.stage === 'results' && p.items.length > 0 && <span className="lv-legend" aria-hidden="true">
        {LEGEND.map(tone => <span key={tone}><i className={`lv-legend-mark tone-${tone}`} />{t(TONE_LABEL[tone])}</span>)}</span>}
      {p.stage === 'export' && <span className="lv-legend">{t("修订预览")}<del>{t("删除")}</del><ins>{t("新增")}</ins></span>}
      {running && p.detail && <span className="lv-desk-detail">{p.detail}</span>}
    </div>
    <div className="lv-sheets">
      {pages.map((page, i) => <article className="lv-sheet" key={`${page.page}-${i}`}>
        {i === 0 && <h1 className="lv-sheet-title">{fileTitle(p.contract.name)}</h1>}
        {page.blocks.map(block => {
          const here = p.items.filter(x => x.finding.block_id === block.id);
          const revised = p.stage === 'results' || p.stage === 'export' ? here.find(x => isRevised(p.decisions[x.finding.id])) : undefined;
          const original = p.stage === 'redaction' ? p.originals?.find(o => o.id === block.id) : undefined;
          const clickable = p.stage === 'results' && here.length > 0;
          const located = p.located?.id === block.id;
          const after = revised ? p.decisions[revised.finding.id].text : '';
          const head = block.text.slice(0, headingEnd(block.text));
          const body = original ? <Compare redacted={block.text} original={original.text} />
            // The clause heading stays set in bold when the revision keeps it.
            : revised && head && after.startsWith(head) ? <><strong className="lv-para-heading"><RichText text={head} /></strong><Redline before={block.text.slice(head.length)} after={after.slice(head.length)} /></>
            : revised ? <Redline before={block.text} after={after} />
            : <Runs runs={paragraphRuns(block.text, picking ? p.candidates.filter(c => c.blockId === block.id).map(c => ({ quote: c.quote, party: c.quote }))
              : marking ? here.map(x => ({ quote: x.finding.original_quote, finding: x.finding })) : [], headingEnd(block.text))}
              blockId={block.id} selected={p.selected} running={running} party={p.party} onParty={p.onParty} />;
          return <div key={`${block.id}-${located ? p.located?.n : 0}`} id={`legal-block-${block.id}`}
            className={`lv-block${here.some(x => x.finding.id === p.selected) ? ' is-selected' : ''}${clickable ? ' is-clickable' : ''}${located ? ' is-located' : ''}`}
            onClick={clickable ? () => p.onSelect(here[0].finding.id) : undefined}>
            {here.length > 0 && !picking && <span className="lv-margin">{here.map(x => {
              const marker = <Marker n={x.n} finding={x.finding} state={markerState(p.decisions[x.finding.id], running)} />;
              return p.stage === 'results'
                ? <button key={x.finding.id} className="lv-margin-mark" aria-label={t("第 {0} 条批注：{1}", { "0": x.n, "1": x.finding.title })}
                  onClick={event => { event.stopPropagation(); p.onSelect(x.finding.id); }}>{marker}</button>
                : <Fragment key={x.finding.id}>{marker}</Fragment>;
            })}</span>}
            <p className="lv-para">{body}</p>
          </div>;
        })}
        {pages.length > 1 && <footer className="lv-sheet-foot" aria-hidden="true">— {i + 1} / {pages.length} —</footer>}
      </article>)}
    </div>
  </section>;
}
