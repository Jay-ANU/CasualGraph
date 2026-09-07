import React, { useState } from 'react';
import { ArrowRight, ArrowUpRight, Search } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import ResearchPreview from '../components/research/ResearchPreview';
import { githubRepositoryUrl } from '../config/downloads';

export default function Home() {
  const [question, setQuestion] = useState('');
  const navigate = useNavigate();
  return <div className="research-home">
    <section className="research-home-intro" aria-labelledby="home-heading">
      <div className="research-home-eyebrow">CausalGraph / ESG research</div>
      <div className="research-home-heading"><h1 id="home-heading" aria-label="Research the report. Keep the source in view.">Research the report.<br /><span>Keep the source in view.</span></h1>
        <div><p>Work across sustainability disclosures.{' '}<br />Ask a question, compare the evidence,{' '}<br />and follow an answer back to its source.</p>
          <Link to="/agent" className="research-home-cta">Open research desk <ArrowUpRight size={16} /></Link></div></div>
      <form className="research-home-question" onSubmit={event => { event.preventDefault(); if (question.trim()) navigate(`/agent?prompt=${encodeURIComponent(question.trim())}`); }}>
        <Search size={16} aria-hidden="true" /><input value={question} onChange={event => setQuestion(event.target.value)} maxLength={2000} aria-label="Ask a research question" placeholder="Ask about a company, target, or disclosure…" />
        <button type="submit" aria-label="Start research" disabled={!question.trim()}><ArrowRight size={17} /></button>
      </form>
    </section>
    <div className="research-home-product"><ResearchPreview /></div>
    <section className="research-home-detail">
      <h2>A report is only<br />the starting point.</h2>
      <div><article><span>01</span><div><h3>Work across your sources</h3><p>Upload reports and select the documents for each question. Keep the scope explicit as your research develops.</p></div></article>
        <article><span>02</span><div><h3>Read the evidence in context</h3><p>Open a citation beside the answer. Read the retrieved passage in full, without leaving the conversation.</p></div></article>
        <article><span>03</span><div><h3>Follow the relationships</h3><p>Explore the entities and connections extracted from your reports. Treat a graph as a route to evidence, not proof of causation.</p><Link to="/causal-inference">Explore the graph <ArrowUpRight size={14} /></Link></div></article></div>
    </section>
    <footer className="research-home-footer"><Link className="research-home-brand" to="/"><img src="/brand/logo-mark.svg" alt="" />CausalGraph</Link>
      <div><Link to="/desktop">Desktop</Link><a href="https://youtu.be/62L-VOsRu8U" target="_blank" rel="noreferrer">Watch walkthrough</a><a href={githubRepositoryUrl} target="_blank" rel="noreferrer">GitHub <ArrowUpRight size={12} /></a></div></footer>
  </div>;
}
