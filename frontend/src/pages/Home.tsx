import React, { useRef, useState } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import { ArrowRight, ArrowUpRight, BookOpenCheck, FileText, GitBranch, Search, ShieldCheck, Plus, Play, Monitor, Github, Layers, ScanLine, Sparkles } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import EvidenceGlobe from '../components/EvidenceGlobe';
import { githubRepositoryUrl } from '../config/downloads';

const questions = [
  'Compare climate commitments across my reports',
  'What evidence supports the emissions targets?',
  'Find gaps in Scope 3 reporting',
];
const chapters = [
  { label: 'Collect', icon: FileText, title: 'Every source. One workspace.', description: 'Bring your reports together without losing what makes each source distinct. Select the documents that belong in your question.' },
  { label: 'Connect', icon: GitBranch, title: 'Go beyond the obvious.', description: 'Explore the relationships between claims, actions, and outcomes. Follow a connection back to the report that supports it.' },
  { label: 'Verify', icon: ShieldCheck, title: 'A clearer answer. A visible trail.', description: 'Keep disclosed facts, general analysis, and missing evidence separate. Inspect the source before you reuse a conclusion.' },
];

export default function Home() {
  const [question, setQuestion] = useState('');
  const [chapter, setChapter] = useState(0);
  const tabs = useRef<Array<HTMLButtonElement | null>>([]);
  const reduceMotion = useReducedMotion();
  const navigate = useNavigate();
  const openQuestion = (prompt: string) => navigate(`/agent?prompt=${encodeURIComponent(prompt.trim())}`);
  const reveal = { initial: { opacity: reduceMotion ? 1 : 0, y: reduceMotion ? 0 : 20 }, whileInView: { opacity: 1, y: 0 }, viewport: { once: true, amount: 0.12 }, transition: { duration: 0.65 } };
  const selectChapter = (index: number) => { const next = (index + chapters.length) % chapters.length; setChapter(next); tabs.current[next]?.focus(); };
  return (
    <div className="research-home">
      <section className="research-hero">
        <div className="research-hero-art" aria-hidden="true">
          <div className="research-wordmark">CausalGraph</div>
          <EvidenceGlobe />
          <span className="research-orbit-label orbit-source"><FileText size={13} /> Original sources</span>
          <span className="research-orbit-label orbit-graph"><GitBranch size={13} /> Connected evidence</span>
          <span className="research-star star-one" /><span className="research-star star-two" />
        </div>
        <div className="research-hero-copy">
          <div className="research-eyebrow"><span /> AN INTELLIGENCE LAYER FOR YOUR RESEARCH <ArrowUpRight size={12} /></div>
          <h1>From disclosures<br />to <em>clearer decisions.</em></h1>
          <p className="research-hero-description">Ask the question behind the report.<br className="research-mobile-break" /> Connect the dots. Keep the evidence.</p>
          <form className="research-hero-search" onSubmit={event => { event.preventDefault(); if (question.trim()) openQuestion(question); }}>
            <div className="research-search-row"><Search size={19} aria-hidden="true" /><input aria-label="Ask a research question" placeholder="What would you like to understand?" value={question} onChange={event => setQuestion(event.target.value)} maxLength={2000} /></div>
            <div className="research-search-tools"><span><Layers size={13} /> Your reports <span className="research-search-divider" /> Source-aware research</span><button type="submit" aria-label="Start research" disabled={!question.trim()}>Start research <ArrowRight size={15} aria-hidden="true" /></button></div>
          </form>
          <div className="research-question-links">{questions.map((prompt, index) => <button key={prompt} type="button" onClick={() => openQuestion(prompt)} title={prompt}><Plus size={12} aria-hidden="true" />{['Compare reports', 'Verify a claim', 'Find evidence gaps'][index]}</button>)}</div>
          <div className="research-hero-actions"><Link to="/agent">Open research desk <ArrowUpRight size={14} /></Link><Link to="/causal-inference">Explore the graph <ArrowRight size={14} /></Link></div>
        </div>
        <div className="research-hero-caption"><span>BUILT AROUND YOUR SOURCES</span><span className="research-scroll-hint">SCROLL TO EXPLORE <span>↓</span></span><span>NOT JUST ANOTHER ANSWER</span></div>
      </section>

      <section className="research-story" aria-labelledby="research-story-title">
        <motion.div className="research-section-heading" {...reveal}><div><span className="research-eyebrow">THE RESEARCH, NOT JUST THE RESULT</span><h2 id="research-story-title">Less searching.<br /><span>More understanding.</span></h2></div><p>From a stack of disclosures to a line of inquiry.<br />One continuous workflow, with the source always in view.</p></motion.div>
        <motion.div className="research-story-grid" {...reveal}>
          <div className="research-story-tabs" role="tablist" aria-label="Research workflow" aria-orientation="vertical">{chapters.map(({ label, icon: Icon, title, description }, index) => <button key={label} type="button" role="tab" ref={node => { tabs.current[index] = node; }} id={`chapter-tab-${index}`} aria-selected={chapter === index} aria-controls={`chapter-panel-${index}`} tabIndex={chapter === index ? 0 : -1} onClick={() => setChapter(index)} onKeyDown={event => { if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) { event.preventDefault(); selectChapter(event.key === 'Home' ? 0 : event.key === 'End' ? chapters.length - 1 : index + (event.key === 'ArrowDown' ? 1 : -1)); } }}><div className="research-chapter-meta"><span>0{index + 1}</span><Icon size={15} /><span>{label}</span><ArrowUpRight size={15} /></div><h3>{title}</h3><p>{description}</p></button>)}</div>
          <div className="research-preview" aria-label="Illustrative evidence workflow preview">
            <div className="research-preview-header"><span><img src="/brand/logo-mark.svg" alt="" /> Research notebook</span><span>WORKFLOW PREVIEW</span></div>
            {chapters.map((_, index) => <div key={index} id={`chapter-panel-${index}`} role="tabpanel" aria-labelledby={`chapter-tab-${index}`} tabIndex={0} hidden={chapter !== index} className="research-preview-panel">
              {index === 0 && <><div className="research-preview-label">YOUR STARTING POINT</div><h3>A library with context.</h3><p>Original documents, ready to explore.</p><div className="research-file-stack">{['Sustainability report', 'Annual disclosure', 'Research notes'].map((title, i) => <div key={title}><span className={`research-file-icon file-tone-${i}`}><FileText size={21} /></span><span><strong>{title}</strong><small>{['Company commitments and progress', 'Financial and operational context', 'Questions worth following'][i]}</small></span><span className="research-file-extension">{i === 2 ? 'TXT' : 'PDF'}</span></div>)}</div><div className="research-preview-note"><Layers size={14} /> Choose the sources. Set the scope.</div></>}
              {index === 1 && <><div className="research-preview-label">LOOK BETWEEN THE LINES</div><h3>Evidence, connected.</h3><p>A relationship is a lead. The source is the check.</p><div className="research-map" aria-label="Illustrative relationships, not an actual causal finding"><svg viewBox="0 0 440 210" aria-hidden="true"><path d="M220 105 Q120 100 75 45 M220 105 Q300 120 368 42 M220 105 Q130 165 80 170 M220 105 Q310 155 368 170" /><circle cx="220" cy="105" r="49" /><circle cx="220" cy="105" r="62" className="research-map-ring" /></svg><span className="map-center"><GitBranch size={21} /> Climate strategy</span><span className="map-node map-n1">Reported target</span><span className="map-node map-n2">Baseline</span><span className="map-node map-n3">Disclosed action</span><span className="map-node map-n4">Evidence gap</span></div></>}
              {index === 2 && <><div className="research-preview-label">A MORE DEFENSIBLE CONCLUSION</div><h3>What supports the claim?</h3><p>Keep the answer close to its evidence.</p><div className="research-answer-card"><span><Sparkles size={15} /> Research perspective</span><p>A climate target describes an ambition. Check its baseline, timeframe, coverage, and disclosed actions before treating it as progress.</p><div><span className="research-inline-source"><FileText size={12} /> Source passage</span><span className="research-inline-gap">Verify the baseline</span></div></div><div className="research-preview-note"><ShieldCheck size={14} /> Gaps stay visible. Assumptions stay labeled.</div></>}
            </div>)}
            <div className="research-preview-footer"><ShieldCheck size={13} /> Illustration only · not a finding from your reports.<span>0{chapter + 1} / 03</span></div>
          </div>
        </motion.div>
      </section>

      <section className="research-principles" aria-label="Research principles">
        {[{ icon: FileText, title: 'Bring the source.', text: 'Keep your reports together. Give every question the right context.' }, { icon: GitBranch, title: 'Follow the connections.', text: 'Move from a focused question to a deeper, cross-report investigation.' }, { icon: BookOpenCheck, title: 'Check the conclusion.', text: 'Review passages and citations before the answer becomes your work.' }].map(({ icon: Icon, title, text }, index) => <motion.div key={title} {...reveal}><span className="research-step-number">0{index + 1}</span><span className="research-principle-icon"><Icon size={20} /></span><h2>{title}</h2><p>{text}</p></motion.div>)}
      </section>
      <section className="research-resources" aria-label="Project resources"><a href={githubRepositoryUrl} target="_blank" rel="noreferrer"><Github size={21} /><div><strong>Open by design.</strong><span>Explore the code behind the research.</span></div><ArrowUpRight size={18} /></a><Link to="/desktop"><Monitor size={21} /><div><strong>Your desk, extended.</strong><span>Continue with the desktop companion.</span></div><ArrowUpRight size={18} /></Link><a href="https://youtu.be/62L-VOsRu8U" target="_blank" rel="noreferrer"><Play size={21} /><div><strong>See it in action.</strong><span>A walkthrough of the research workflow.</span></div><ArrowUpRight size={18} /></a></section>
      <section className="research-bottom-line"><div><ScanLine size={25} /><span className="research-eyebrow">THERE IS MORE TO THE STORY</span><h2>Find it in the evidence.</h2><p>Bring your next question. Let the research begin.</p></div><Link to="/agent" className="research-primary">Start a conversation <ArrowUpRight size={17} /></Link></section>
      <footer className="research-footer"><Link to="/" className="research-footer-brand"><img src="/brand/logo-mark.svg" alt="" /> CausalGraph</Link><span>An evidence-first research workspace.</span><div><Link to="/desktop">Desktop</Link><Link to="/about">About</Link><a href={githubRepositoryUrl} target="_blank" rel="noreferrer">GitHub <ArrowUpRight size={12} /></a></div></footer>
    </div>
  );
}
