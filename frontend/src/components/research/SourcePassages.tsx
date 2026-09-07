import React, { useEffect, useRef } from 'react';
import { FileText } from 'lucide-react';
import type { RagSource } from '../../types/api';
import { formatSourceDocumentTitle } from '../../pages/agent/ragUi';
import { sourceLocation } from './citations';

export default function SourcePassages({ sources, activeId }: { sources: RagSource[]; activeId?: string | null }) {
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const target = Array.from(root.current?.querySelectorAll<HTMLElement>('[data-source-id]') || [])
      .find(element => element.dataset.sourceId === activeId);
    if (!target) return;
    const frame = window.requestAnimationFrame(() => {
      target.scrollIntoView({ block: 'nearest', behavior: 'auto' });
      target.focus({ preventScroll: true });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [activeId, sources]);
  return <div ref={root} className="research-source-list">
    <p className="research-source-intro">Retrieved passages, in their original wording. Check the context before reusing a claim.</p>
    {sources.length === 0 ? <p>No cited evidence yet.</p> : sources.map((source, index) =>
      <article key={`${source.document_id}-${source.chunk_id}-${index}`} tabIndex={-1} data-source-id={source.chunk_id}
        className={`research-source-article${source.chunk_id === activeId ? ' is-selected' : ''}`}>
        <header><span className="research-source-number">{index + 1}</span><div><h3>{formatSourceDocumentTitle(source)}</h3>
          <span><FileText size={12} aria-hidden="true" />{sourceLocation(source)}</span></div></header>
        {source.text ? <blockquote>{source.text}</blockquote> : <p>The excerpt is not available for this source.</p>}
        <details className="research-source-id"><summary>Source identifier</summary><code>{source.chunk_id || 'Not provided'}</code></details>
      </article>)}
  </div>;
}
