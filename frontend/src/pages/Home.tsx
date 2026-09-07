import React, { useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, ArrowUpRight, BookOpen, CheckCircle2, FileText, GitBranch, Layers, Search, ShieldCheck } from 'lucide-react';
import { githubRepositoryUrl } from '../config/downloads';

const views = ['Evidence', 'Connections', 'Analysis'] as const;
const examples = [
  { icon: Search, title: 'Compare disclosures', text: 'Which emissions categories are covered across the selected reports?' },
  { icon: GitBranch, title: 'Trace a relationship', text: 'What evidence connects a climate commitment to operational changes?' },
  { icon: ShieldCheck, title: 'Find the missing evidence', text: 'Which claims need another source before they can be reused?' },
];

export default function Home() {
  const [view, setView] = useState(0);
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const selectTab = (index: number) => {
    const next = (index + views.length) % views.length;
    setView(next);
    tabRefs.current[next]?.focus();
  };

  return (
    <div className="cg-research-home">
      <section className="research-hero" aria-labelledby="research-title">
        <div className="research-hero-copy">
          <div className="research-eyebrow"><span /> THE ESG RESEARCH WORKSPACE</div>
          <h1 id="research-title">Evidence first.<br /><em>Every answer.</em></h1>
          <p className="research-lead">Turn long reports into a clear line of inquiry. Ask across your documents, follow the connections, and inspect the evidence behind each answer.</p>
          <div className="research-actions">
            <Link className="research-button research-button-primary" to="/agent">Open research desk <ArrowRight size={18} aria-hidden="true" /></Link>
            <Link className="research-button research-button-secondary" to="/esg-demo">Explore the demo <ArrowUpRight size={17} aria-hidden="true" /></Link>
          </div>
          <div className="research-capabilities"><span>Report-grounded answers</span><span>Inspectable citations</span><span>DeepSeek V4 Pro profile</span></div>
        </div>
        <div className="research-preview" aria-label="Illustrative research workflow">
          <div className="research-preview-top"><span><Layers size={17} aria-hidden="true" /> Research notebook</span><span className="research-demo-label">ILLUSTRATIVE EXAMPLE</span></div>
          <div className="research-preview-question"><span className="research-eyebrow">A BETTER QUESTION</span><h2>What supports this claim?</h2><p>Keep the answer and its evidence in the same workspace.</p></div>
          <div className="research-tabs" role="tablist" aria-label="Workflow preview">
            {views.map((label, index) => (
              <button key={label} id={`preview-tab-${index}`} ref={(node) => { tabRefs.current[index] = node; }} type="button" role="tab" aria-selected={view === index} aria-controls={`preview-panel-${index}`} tabIndex={view === index ? 0 : -1} onClick={() => setView(index)} onKeyDown={(event) => {
                if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') { event.preventDefault(); selectTab(index + (event.key === 'ArrowRight' ? 1 : -1)); }
                if (event.key === 'Home' || event.key === 'End') { event.preventDefault(); selectTab(event.key === 'Home' ? 0 : views.length - 1); }
              }}>{label}</button>
            ))}
          </div>
          <div className="research-preview-panels">
            <section id="preview-panel-0" role="tabpanel" aria-labelledby="preview-tab-0" tabIndex={0} hidden={view !== 0}>
              <div className="research-source"><FileText size={19} aria-hidden="true" /><div><strong>Selected report</strong><span>Retrieved passage · original source retained</span></div><span className="research-source-tag">SOURCE</span></div>
              <blockquote>“The relevant passage from your report appears here, so the claim can be checked in context.”</blockquote>
              <div className="research-note"><CheckCircle2 size={16} aria-hidden="true" /> A citation is a starting point for verification, not a guarantee.</div>
            </section>
            <section id="preview-panel-1" role="tabpanel" aria-labelledby="preview-tab-1" tabIndex={0} hidden={view !== 1}>
              <div className="research-connection"><span>Report passage</span><ArrowRight size={18} aria-hidden="true" /><span>Extracted entity</span><ArrowRight size={18} aria-hidden="true" /><span>Related claim</span></div>
              <h3>Follow a connection. Check its source.</h3><p>Inspect extracted relationships alongside the text. A graph connection alone does not establish a causal effect.</p>
            </section>
            <section id="preview-panel-2" role="tabpanel" aria-labelledby="preview-tab-2" tabIndex={0} hidden={view !== 2}>
              <div className="research-analysis-row"><span>01</span><div><strong>What the report says</strong><p>Evidence-backed observations, with citations.</p></div></div>
              <div className="research-analysis-row"><span>02</span><div><strong>What still needs checking</strong><p>Missing disclosures, uncertainty, and clearly separated general analysis.</p></div></div>
            </section>
          </div>
          <div className="research-preview-footer"><ShieldCheck size={14} aria-hidden="true" /> Workflow illustration, not a result from your documents.</div>
        </div>
      </section>

      <section className="research-process" aria-label="Research workflow">
        {[['01', 'Bring your reports', 'Upload documents and select the evidence scope.'], ['02', 'Ask a precise question', 'Use Flash for a focused answer or Deep for broader research.'], ['03', 'Inspect before reusing', 'Review citations, source passages, and evidence gaps.']].map(([number, title, detail]) => (
          <div key={number}><span className="research-step-number">{number}</span><div><h2>{title}</h2><p>{detail}</p></div></div>
        ))}
      </section>

      <section className="research-usecases" aria-labelledby="usecases-title">
        <div className="research-section-heading"><div><span className="research-eyebrow">START WITH A QUESTION</span><h2 id="usecases-title">Less searching. More understanding.</h2></div><Link to="/agent">Start your own inquiry <ArrowUpRight size={17} aria-hidden="true" /></Link></div>
        <div className="research-usecase-grid">{examples.map(({ icon: Icon, title, text }) => (
          <article key={title}><Icon size={22} aria-hidden="true" /><h3>{title}</h3><p>{text}</p><Link to="/agent" aria-label={`Open research desk to ${title.toLowerCase()}`}>Open research desk <ArrowRight size={16} aria-hidden="true" /></Link></article>
        ))}</div>
      </section>

      <section className="research-bottom"><BookOpen size={28} aria-hidden="true" /><div><h2>Keep the source in the conversation.</h2><p>Your research deserves more than an answer without a reference.</p></div><Link className="research-button research-button-primary" to="/agent">Start researching <ArrowRight size={18} aria-hidden="true" /></Link></section>
      <footer className="research-footer"><span>CausalGraph AI · Evidence-led ESG research</span><div><Link to="/desktop">Desktop companion</Link><Link to="/about">About</Link><a href={githubRepositoryUrl} target="_blank" rel="noreferrer">Source code <ArrowUpRight size={14} aria-hidden="true" /></a></div></footer>
    </div>
  );
}
