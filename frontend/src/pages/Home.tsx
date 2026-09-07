import React, { useState } from 'react';
import { ArrowRight, ArrowUpRight, BookOpenCheck, FileText, GitBranch, Search, ShieldCheck } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';

const questions = [
  'Compare climate commitments across my reports',
  'What evidence supports the emissions targets?',
  'Find gaps in Scope 3 reporting',
];

export default function Home() {
  const [question, setQuestion] = useState('');
  const navigate = useNavigate();
  const openQuestion = (prompt: string) => navigate(`/agent?prompt=${encodeURIComponent(prompt.trim())}`);
  return (
    <div className="research-home">
      <section className="research-hero">
        <div className="research-hero-copy">
          <div className="research-eyebrow"><span /> EVIDENCE-FIRST ESG RESEARCH</div>
          <h1>From disclosures<br />to <em>clearer decisions.</em></h1>
          <p className="research-hero-description">A research desk for the questions behind the report. Bring your documents, explore the connections, and follow every answer back to its evidence.</p>
          <form className="research-hero-search" onSubmit={event => { event.preventDefault(); if (question.trim()) openQuestion(question); }}>
            <Search size={20} aria-hidden="true" />
            <input aria-label="Ask a research question" placeholder="What would you like to understand?" value={question} onChange={event => setQuestion(event.target.value)} maxLength={2000} />
            <button type="submit" aria-label="Start research" disabled={!question.trim()}><ArrowRight size={20} /></button>
          </form>
          <div className="research-question-links">{questions.map(prompt => <button key={prompt} type="button" onClick={() => openQuestion(prompt)}>{prompt}<ArrowUpRight size={13} /></button>)}</div>
          <div className="research-hero-actions"><Link to="/agent" className="research-primary">Open research desk <ArrowUpRight size={17} /></Link><Link to="/causal-inference">Explore the graph <ArrowRight size={16} /></Link></div>
        </div>
        <div className="research-preview" aria-label="Illustrative evidence workflow preview">
          <div className="research-preview-header"><span><span className="research-mini-logo">C</span> RESEARCH NOTE</span><span>WORKFLOW PREVIEW</span></div>
          <div className="research-preview-question"><span className="research-eyebrow">THE QUESTION</span><h2>What sits behind a<br />climate commitment?</h2></div>
          <div className="research-preview-source"><FileText size={18} /><div><strong>Your sustainability report</strong><span>Retrieved passages · preserved citations</span></div><span className="research-source-tag">SOURCE</span></div>
          <div className="research-preview-route"><span>Reported target</span><span>Supporting action</span><span>Evidence gap</span></div>
          <div className="research-preview-answer"><div><BookOpenCheck size={18} /><strong>Make the distinction.</strong></div><p>A target describes an ambition. Check the baseline, timeframe, coverage, and disclosed actions before treating it as progress.</p><span>Illustrative guidance, not a finding from your reports.</span></div>
          <div className="research-preview-footer"><ShieldCheck size={14} /> Evidence before confidence.<span>01 / 03</span></div>
        </div>
      </section>
      <section className="research-principles" aria-label="Research workflow">
        <div><span className="research-step-number">01</span><FileText size={21} /><h2>Bring the source.</h2><p>Keep reports together in your library. Choose the documents that belong in the question.</p></div>
        <div><span className="research-step-number">02</span><GitBranch size={21} /><h2>Follow the connections.</h2><p>Move between focused questions and deeper research, with graph context and a visible retrieval process.</p></div>
        <div><span className="research-step-number">03</span><BookOpenCheck size={21} /><h2>Check the conclusion.</h2><p>Inspect passages and citations. Distinguish disclosed facts from assumptions and general analysis.</p></div>
      </section>
      <section className="research-bottom-line"><div><span className="research-eyebrow">MADE FOR THE WORK, NOT JUST THE ANSWER</span><h2>Keep your research inspectable.</h2></div><Link to="/agent">Start a conversation <ArrowUpRight size={18} /></Link></section>
      <footer className="research-footer"><span>CausalGraph · An evidence-first research workspace</span><div><Link to="/desktop">Desktop companion</Link><Link to="/about">About the project</Link></div></footer>
    </div>
  );
}
