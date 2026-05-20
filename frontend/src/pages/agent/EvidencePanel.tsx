import React from 'react';
import { FileText } from 'lucide-react';

import { GraphVisualizer } from '../../components';
import type { GraphData } from '../../types/graph';
import type { RagGraphSource } from '../../types/api';
import { formatRelationLabel, pickEvidenceSnippet } from './ragUi';

export interface EvidenceCard {
  rank: number;
  documentTitle: string;
  chunkLabel: string;
  sourceType: string;
  domain: string;
  snippet: string;
  relevance: number | null;
}

interface EvidencePanelProps {
  evidenceCards: EvidenceCard[];
  latestGraphSources?: RagGraphSource;
  tracePreviewGraph: GraphData | null;
  graphEdges: NonNullable<RagGraphSource['edges']>;
  neo4jConnected: boolean;
}

const EvidencePanel: React.FC<EvidencePanelProps> = ({
  evidenceCards,
  latestGraphSources,
  tracePreviewGraph,
  graphEdges,
  neo4jConnected,
}) => (
  <aside className="cg-sidebar hidden w-[340px] shrink-0 flex-col overflow-hidden border-l border-hairline xl:flex 2xl:w-[420px]">
    <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5">
      <section>
        <div className="flex items-center justify-between">
          <span className="cg-eyebrow block text-ink-steel">Evidence — last answer</span>
          {evidenceCards.length > 0 && (
            <span className="text-[11px] text-ink-stone">
              {evidenceCards.length} passages
            </span>
          )}
        </div>
        {evidenceCards.length === 0 ? (
          <p className="mt-3 text-[13px] leading-[1.55] text-ink-stone">
            No retrieved passages yet. Ask a question to anchor an answer in the corpus.
          </p>
        ) : (
          <ol className="mt-3 space-y-3">
            {evidenceCards.map((card) => {
              const badgeTone =
                card.relevance === null
                  ? 'bg-surface-soft text-ink-steel'
                  : card.relevance >= 60
                    ? 'bg-emerald-50 text-emerald-700'
                    : card.relevance >= 35
                      ? 'bg-amber-50 text-amber-700'
                      : 'bg-surface-soft text-ink-charcoal';
              return (
                <li
                  key={`${card.chunkLabel || card.documentTitle}-${card.rank}`}
                  className="cg-list-row p-3"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <div className="mb-1 flex items-center gap-1.5">
                        <span className="inline-flex h-4 min-w-4 items-center justify-center rounded bg-surface-soft px-1 text-[10px] font-semibold text-ink-charcoal">
                          {card.rank}
                        </span>
                        <span className="truncate text-[12px] font-semibold text-ink">
                          {card.documentTitle}
                        </span>
                      </div>
                      <div className="flex flex-wrap items-center gap-1.5">
                        {card.chunkLabel && (
                          <span className="text-[11px] text-ink-stone">
                            {card.chunkLabel}
                          </span>
                        )}
                        {card.domain && (
                          <span className="rounded bg-surface-soft px-1.5 py-0.5 text-[11px] font-medium text-ink-charcoal">
                            {card.domain}
                          </span>
                        )}
                        {card.sourceType && (
                          <span className="rounded bg-surface-soft px-1.5 py-0.5 text-[11px] font-medium text-ink-charcoal">
                            {card.sourceType}
                          </span>
                        )}
                      </div>
                    </div>
                    <FileText className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ink-faint" />
                  </div>

                  {card.snippet ? (
                    <blockquote className="mt-2 rounded-md border-l-2 border-hairline bg-surface-soft px-2.5 py-2 text-[12px] leading-[1.55] text-ink-charcoal">
                      {card.snippet}
                    </blockquote>
                  ) : (
                    <p className="mt-2 text-[12px] text-ink-stone">
                      No readable excerpt was returned for this passage.
                    </p>
                  )}

                  <div className="mt-2 flex items-center justify-between">
                    <span className="cg-eyebrow text-ink-stone">Evidence chunk</span>
                    <span className={`rounded px-1.5 py-0.5 text-[11px] font-semibold ${badgeTone}`}>
                      {card.relevance === null ? 'retrieved' : `${card.relevance}% relevance`}
                    </span>
                  </div>
                </li>
              );
            })}
          </ol>
        )}
      </section>

      {((latestGraphSources?.matched_entities?.length ?? 0) > 0 ||
        (latestGraphSources?.edges?.length ?? 0) > 0) && (
        <section className="mt-6">
          <div className="flex items-center justify-between">
            <span className="cg-eyebrow block text-ink-steel">Graph trace</span>
            <span className="text-[11px] text-ink-stone">
              {(latestGraphSources?.matched_entities?.length ?? 0)} nodes · {(latestGraphSources?.edges?.length ?? 0)} edges
            </span>
          </div>
          <div className="cg-tool-panel mt-3 p-3">
            {tracePreviewGraph && (
              <div className="mb-3">
                <GraphVisualizer
                  graph={tracePreviewGraph}
                  compact
                  height={220}
                  focusNodeId={tracePreviewGraph.edges[0]?.source || null}
                />
              </div>
            )}

            {(latestGraphSources?.matched_entities?.length ?? 0) > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {(latestGraphSources?.matched_entities || [])
                  .slice(0, 10)
                  .map((entity: any, idx: number) => (
                    <span
                      key={`${entity?.id || entity?.label || idx}-${idx}`}
                      className="inline-flex items-center rounded-md border border-hairline bg-surface-soft px-1.5 py-0.5 text-[11px] font-medium text-ink-charcoal"
                    >
                      {String(entity?.label || entity?.name || entity?.id || '—').slice(0, 28)}
                    </span>
                  ))}
              </div>
            )}

            {graphEdges.length > 0 && (
              <ul className="mt-3 space-y-2">
                {graphEdges.map((edge, idx) => (
                  <li key={`${edge.source}-${edge.target}-${idx}`} className="rounded-md border border-hairline bg-surface-soft p-2">
                    <div className="cg-eyebrow text-ink-steel">
                      {formatRelationLabel(edge.relationship_type || edge.relation_type)}
                    </div>
                    <div className="mt-1 text-[12px] leading-5 text-ink-charcoal">
                      <span className="font-medium text-ink">{String(edge.source || '—')}</span>
                      <span className="mx-1 text-ink-stone">→</span>
                      <span className="font-medium text-ink">{String(edge.target || '—')}</span>
                    </div>
                    {edge.evidence && (
                      <p className="mt-1 line-clamp-2 text-[12px] leading-[1.45] text-ink-steel">
                        {pickEvidenceSnippet(String(edge.evidence))}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            )}

            {(latestGraphSources?.edges?.length || 0) > graphEdges.length && (
              <p className="mt-2 text-[12px] text-ink-stone">
                Showing {graphEdges.length} of {latestGraphSources?.edges?.length || 0} relationships.
              </p>
            )}
          </div>
        </section>
      )}
    </div>

    <div className="flex items-center justify-between border-t border-hairline bg-surface-soft px-4 py-2">
      <div className="flex items-center gap-1.5 text-[11px] text-ink-steel">
        <span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-500" />
        <span>Graph trace</span>
        <span className="text-ink-faint">·</span>
        <span>{neo4jConnected ? 'available' : 'local evidence'}</span>
      </div>
      <span className="text-[11px] text-ink-stone">
        Answers cite the passages they were grounded on.
      </span>
    </div>
  </aside>
);

export default EvidencePanel;
