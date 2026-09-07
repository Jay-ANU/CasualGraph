import React, { useState } from 'react';
import { ArrowUp, Check, ChevronRight, FileText, PanelRightClose, PanelRightOpen } from 'lucide-react';
import ResearchAnswer from './ResearchAnswer';
import SourcePassages from './SourcePassages';
import type { RagSource } from '../../types/api';

// Deliberately synthetic. These records never enter the user's library or an API.
const sources: Array<RagSource & { page: number }> = [
  { chunk_id: 'example-2025-12', document_title: 'Sustainability report 2025', page: 12,
    text: 'Our 2030 emissions target covers Scope 1 and Scope 2. Progress is measured against a 2020 baseline. Scope 3 emissions are not included in this target.' },
  { chunk_id: 'example-2025-18', document_title: 'Sustainability report 2025', page: 18,
    text: 'We are developing an inventory of supply-chain emissions. A separate Scope 3 reduction target has not yet been established.' },
];
const content = '### What the target covers\nThe report’s 2030 target covers **Scope 1 and Scope 2**, measured against a 2020 baseline. It does not include Scope 3. [example-2025-12]\n\n### What is still missing\nThe company is developing its supply-chain inventory, but has not established a separate Scope 3 reduction target. [example-2025-18]\n\nThis is a boundary on the disclosed target—not evidence that supply-chain emissions are falling.';

export default function ResearchPreview() {
  const [open, setOpen] = useState(true);
  const [activeId, setActiveId] = useState<string | null>(null);
  return <section className="research-product-preview" aria-label="Interactive product example">
    <header className="preview-toolbar"><span><img src="/brand/logo-mark.svg" alt="" />Research desk<ChevronRight size={12} /><span>Climate targets</span></span>
      <span className="preview-example-label">Illustrative example</span></header>
    <div className={`preview-workbench${open ? '' : ' is-reading'}`}>
      <aside className="preview-library"><div>Reports <span>1</span></div><div className="preview-report"><FileText size={16} /><span>Sustainability report<small>2025 · Example document</small></span><Check size={12} /></div>
        <p>Select the reports that belong in your question.</p></aside>
      <div className="preview-conversation"><div className="preview-question">Does the emissions target include Scope 3?</div>
        <ResearchAnswer content={content} sources={sources} onCitation={source => { setOpen(true); setActiveId(source.chunk_id); }} />
        <button type="button" className="preview-source-toggle" onClick={() => { setOpen(!open); setActiveId(null); }} aria-expanded={open} aria-controls="preview-evidence">
          {open ? <PanelRightClose size={14} /> : <PanelRightOpen size={14} />} {open ? 'Hide sources' : 'Inspect 2 sources'}
        </button>
        <div className="preview-composer" aria-hidden="true"><span>Ask a follow-up about this report…</span><ArrowUp size={17} /></div>
      </div>
      {open && <aside className="preview-evidence" id="preview-evidence"><header>Evidence <span>2 passages</span><button type="button" onClick={() => setOpen(false)} aria-label="Close example evidence"><PanelRightClose size={16} /></button></header>
        <SourcePassages sources={sources} activeId={activeId} /></aside>}
    </div>
    <footer>Interactive example · Fictional excerpts, not a result from your documents.<span>Click a citation to inspect the passage.</span></footer>
  </section>;
}
