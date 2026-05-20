// Deprecated: legacy Predict JSON renderer. The Agent now streams free-form
// markdown for both Flash and Deep tiers, so this panel is no longer mounted.
// Kept for one release in case any stored session messages still contain a
// prediction payload. Slated for removal in a follow-up cleanup PR.
import React from 'react';
import type { CausalChainStep, PredictionAnswer as PredictionAnswerType } from '../types/api';

interface PredictionAnswerProps {
  answer: PredictionAnswerType;
  onGraphReferenceClick?: (refs: string[]) => void;
}

const CONFIDENCE_LABELS: Record<PredictionAnswerType['confidence'], string> = {
  low: 'Low confidence',
  medium: 'Medium confidence',
  high: 'High confidence',
};

// CausalGraph design system: emerald is reserved for status banners and the
// Environmental domain pill. Reasoning steps and footnotes use the slate
// confidence ramp (low → mid → high) so visual weight tracks evidence weight.
const isGroundedInReport = (step: CausalChainStep) => {
  if (step.source_type === 'report_evidence') return true;
  if (step.evidence_refs?.some(ref => /^chunk_/i.test(ref))) return true;
  if (step.evidence_refs?.some(ref => /^prior_/i.test(ref) || /^reg_/i.test(ref))) return true;
  return false;
};

const getEvidenceLabel = (ref: string) => {
  if (/^chunk_/i.test(ref)) return 'Report evidence';
  if (/^prior_/i.test(ref)) return 'Academic prior';
  if (/^reg_/i.test(ref)) return 'Regulatory context';
  if (/^G\d+$/i.test(ref)) return 'Knowledge graph signal';
  return 'Supporting context';
};

const getEvidenceDescription = (ref: string) => {
  if (/^chunk_/i.test(ref)) return 'Retrieved from the company report corpus.';
  if (/^prior_/i.test(ref)) return 'Retrieved from the academic evidence layer.';
  if (/^reg_/i.test(ref)) return 'Retrieved from the regulatory context layer.';
  if (/^G\d+$/i.test(ref)) return 'Derived from the extracted relationship graph.';
  return 'Used as supporting context for this reasoning step.';
};

const buildFootnotes = (chain: CausalChainStep[]) => {
  const notes: Array<{ ref: string; number: number; grounded: boolean; graph: boolean; label: string; description: string }> = [];
  const seen = new Map<string, number>();

  chain.forEach(step => {
    (step.evidence_refs || []).filter(Boolean).forEach(ref => {
      if (seen.has(ref)) return;
      const number = notes.length + 1;
      seen.set(ref, number);
      notes.push({
        ref,
        number,
        grounded: isGroundedInReport(step),
        graph: /^G\d+$/i.test(ref),
        label: getEvidenceLabel(ref),
        description: getEvidenceDescription(ref),
      });
    });
  });

  return { notes, seen };
};

const getStepRefs = (step: CausalChainStep, refNumbers: Map<string, number>) =>
  (step.evidence_refs || [])
    .filter(ref => refNumbers.has(ref))
    .map(ref => ({ ref, number: refNumbers.get(ref) as number }));

const PredictionAnswer: React.FC<PredictionAnswerProps> = ({ answer, onGraphReferenceClick }) => {
  const confidence = answer.confidence || 'low';
  const confidenceScore = typeof answer.confidence_score === 'number' ? Math.max(0, Math.min(100, Math.round(answer.confidence_score))) : null;
  const chain = Array.isArray(answer.causal_chain) ? answer.causal_chain : [];
  const assumptions = Array.isArray(answer.key_assumptions) ? answer.key_assumptions : [];
  const counterEvidence = Array.isArray(answer.counter_evidence) ? answer.counter_evidence : [];
  const { notes, seen: refNumbers } = buildFootnotes(chain);

  if (answer.parse_error) {
    return (
      <article className="rounded-xl border border-slate-200 bg-white px-5 py-5 text-slate-900 shadow-sm">
        <span className="cg-eyebrow block text-slate-500">
          Prediction response could not be parsed
        </span>
        <p className="mt-4 text-[15px] leading-[1.7]">{answer.prediction}</p>
        {answer.raw && (
          <pre className="mt-4 max-h-56 overflow-auto rounded-md border-l-2 border-slate-300 bg-slate-50 p-3 font-mono text-[12px] leading-5 text-slate-700">
            {answer.raw}
          </pre>
        )}
      </article>
    );
  }

  return (
    <article className="rounded-xl border border-slate-200 bg-white px-5 py-5 text-slate-950 shadow-sm sm:px-7 sm:py-6">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-slate-200 pb-3">
        <span className="cg-eyebrow text-slate-700">{CONFIDENCE_LABELS[confidence]}</span>
        {confidenceScore !== null && (
          <>
            <span className="text-slate-300" aria-hidden>·</span>
            <span className="inline-flex items-center rounded-md border border-slate-200 bg-slate-50 px-1.5 py-0.5 font-mono text-[11px] text-slate-700">
              score {confidenceScore}
            </span>
          </>
        )}
        <span className="text-slate-300" aria-hidden>·</span>
        <span className="text-[12px] leading-[1.55] text-slate-500">
          {answer.disclaimer || 'Scenario reasoning, not investment advice.'}
        </span>
      </div>

      {answer.confidence_rationale && (
        <p className="mt-3 text-[12px] leading-[1.55] text-slate-500">
          Confidence rationale: {answer.confidence_rationale}.
        </p>
      )}

      <p className="mt-5 border-l-2 border-slate-950 pl-4 font-display text-[18px] font-medium leading-[1.5] tracking-normal text-slate-950">
        {answer.prediction}
      </p>

      {counterEvidence.length > 0 && (
        <section className="mt-6 border-t border-slate-200 pt-4">
          <h4 className="font-display text-[15px] font-semibold leading-[1.4] tracking-normal text-slate-950">
            Counterpoint
          </h4>
          <div className="mt-3 space-y-3">
            {counterEvidence.map((item, index) => (
              <p key={`${item}-${index}`} className="text-[15px] leading-[1.7] text-slate-700">
                {item}
              </p>
            ))}
          </div>
        </section>
      )}

      {(chain.length > 0 || assumptions.length > 0) && (
        <details className="group mt-6 border-t border-slate-200 pt-3">
          <summary className="flex cursor-pointer list-none items-center gap-2 text-slate-500 hover:text-slate-700">
            <span className="text-slate-400 transition-transform group-open:rotate-90">›</span>
            <span className="cg-eyebrow text-slate-500 group-hover:text-slate-700">View reasoning</span>
            {chain.length > 0 && (
              <span className="font-mono text-[11px] text-slate-400">
                ({chain.length} steps)
              </span>
            )}
          </summary>

          <div className="mt-4 space-y-5">
            {chain.length > 0 ? chain.map((step, index) => {
              const refs = getStepRefs(step, refNumbers);
              const graphRefs = refs.filter(item => /^G\d+$/i.test(item.ref)).map(item => item.ref);
              const canOpenGraph = graphRefs.length > 0 && onGraphReferenceClick;
              const isSpeculation = step.source_type === 'speculation';

              return (
                <p key={`${step.step}-${index}`} className="text-[15px] leading-[1.7] text-slate-800">
                  <span
                    className={`mr-3 align-baseline font-mono text-[11px] font-semibold ${
                      isSpeculation ? 'text-slate-400' : 'text-slate-900'
                    }`}
                  >
                    {String(index + 1).padStart(2, '0')}
                  </span>
                  {step.step}
                  {refs.length > 0 && (
                    <span className="ml-1 whitespace-nowrap">
                      {refs.map(({ ref, number }) => (
                        <button
                          key={ref}
                          type="button"
                          disabled={!canOpenGraph || !/^G\d+$/i.test(ref)}
                          onClick={() => /^G\d+$/i.test(ref) && onGraphReferenceClick?.([ref])}
                          className={`align-super font-mono text-[10px] font-semibold leading-none ${
                            isSpeculation ? 'text-slate-400' : 'text-slate-700'
                          } ${
                            canOpenGraph && /^G\d+$/i.test(ref)
                              ? 'cursor-pointer underline decoration-slate-300 underline-offset-2 hover:text-slate-950'
                              : 'cursor-default'
                          }`}
                          title={ref}
                        >
                          {number}
                        </button>
                      ))}
                    </span>
                  )}
                  {isSpeculation && (
                    <span className="ml-2 rounded-md border border-slate-200 bg-slate-50 px-1.5 py-0.5 font-mono text-[10px] font-medium text-slate-500">
                      estimated
                    </span>
                  )}
                </p>
              );
            }) : null}
          </div>

          {assumptions.length > 0 && (
            <section className="mt-6 border-t border-slate-100 pt-4">
              <span className="cg-eyebrow block text-slate-500">Working assumptions</span>
              <p className="mt-3 text-[15px] leading-[1.7] text-slate-700">
                {assumptions.join(' ')}
              </p>
            </section>
          )}

          {notes.length > 0 && (
            <details className="group/inner mt-5 border-t border-slate-100 pt-3">
              <summary className="flex cursor-pointer list-none items-center gap-2 text-slate-400 hover:text-slate-600">
                <span className="text-slate-300 transition-transform group-open/inner:rotate-90">›</span>
                <span className="cg-eyebrow text-slate-400 group-hover/inner:text-slate-600">
                  View evidence
                </span>
                <span className="font-mono text-[11px] text-slate-400">({notes.length})</span>
              </summary>
              <ol className="mt-3 space-y-2 text-[12px] leading-5 text-slate-500">
                {notes.map(note => (
                  <li key={note.ref} className="flex gap-2">
                    <span
                      className={`w-5 shrink-0 font-mono font-semibold ${
                        note.grounded ? 'text-slate-700' : 'text-slate-400'
                      }`}
                    >
                      {note.number}
                    </span>
                    <button
                      type="button"
                      disabled={!note.graph || !onGraphReferenceClick}
                      onClick={() => note.graph && onGraphReferenceClick?.([note.ref])}
                      className={`text-left ${
                        note.grounded ? 'text-slate-700' : 'text-slate-400'
                      } ${
                        note.graph && onGraphReferenceClick
                          ? 'underline decoration-slate-300 underline-offset-2 hover:text-slate-950'
                          : ''
                      }`}
                    >
                      <span className="font-medium">{note.label}</span>
                      <span className="text-slate-500"> — {note.description}</span>
                    </button>
                  </li>
                ))}
              </ol>
            </details>
          )}
        </details>
      )}
    </article>
  );
};

export default PredictionAnswer;
