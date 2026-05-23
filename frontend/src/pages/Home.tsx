import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { Link } from 'react-router-dom';
import {
  ArrowRight,
  BookOpenCheck,
  BrainCircuit,
  Database,
  Download,
  FileCheck2,
  FileSearch,
  Github,
  MessageSquare,
  Network,
  ScreenShare,
  ShieldCheck,
} from 'lucide-react';
import { githubRepositoryUrl } from '../config/downloads';

const workflowSteps = [
  {
    step: '01',
    title: 'Upload reports',
    description: 'Add annual reports, ESG disclosures, coursework drafts, notes, or screenshots into one private workspace.',
    icon: FileSearch,
  },
  {
    step: '02',
    title: 'Ask with context',
    description: 'Ask business, ESG, strategy, finance, or academic questions without manually searching hundreds of pages.',
    icon: MessageSquare,
  },
  {
    step: '03',
    title: 'Check the evidence',
    description: 'Keep citations, chunks, graph nodes, and reasoning traces close enough to verify before using the answer.',
    icon: FileCheck2,
  },
  {
    step: '04',
    title: 'Turn it into work',
    description: 'Draft analysis, compare companies, review Word documents, and refine arguments from the same evidence base.',
    icon: BookOpenCheck,
  },
];

const useCases = [
  {
    title: 'Business report writing',
    description: 'Upload company reports and ask the agent to build a supported analysis outline, identify missing metrics, and refine claims.',
  },
  {
    title: 'ESG disclosure review',
    description: 'Track emissions, workforce, governance, risk, and strategy evidence across long reports with source-backed answers.',
  },
  {
    title: 'Company comparison',
    description: 'Compare disclosure quality, strategy signals, risks, and graph relationships across selected companies.',
  },
  {
    title: 'Academic study support',
    description: 'Turn screenshots and documents into study notes, concept explanations, follow-up questions, and evidence-aware drafts.',
  },
];

const domains = [
  { label: 'E', title: 'Environment', detail: 'Emissions, energy, climate risk, water, waste.', color: 'var(--cg-domain-e)' },
  { label: 'S', title: 'Social', detail: 'Workforce, safety, diversity, suppliers, community.', color: 'var(--cg-domain-s)' },
  { label: 'G', title: 'Governance', detail: 'Board oversight, audit controls, ethics, compliance.', color: 'var(--cg-domain-g)' },
  { label: 'AI', title: 'AI Insight', detail: 'RAG routing, graph reasoning, prediction, review.', color: 'var(--cg-domain-ai)' },
];

const evidenceRules = [
  'Answers should cite retrieved report chunks when evidence exists.',
  'Unsupported claims should be softened or marked as needing evidence.',
  'Graph context should show which concepts and relationships shaped the answer.',
  'General guidance should remain useful instead of refusing harmless questions.',
];

const ResearchDeskPreview: React.FC = () => (
  <div className="cg-tool-panel overflow-hidden">
    <div className="flex items-center justify-between border-b border-hairline px-4 py-3">
      <div className="flex items-center gap-2">
        <span className="h-2.5 w-2.5 rounded-full bg-ink" />
        <span className="h-2.5 w-2.5 rounded-full bg-hairline" />
        <span className="h-2.5 w-2.5 rounded-full bg-hairline" />
      </div>
      <span className="font-mono text-[11px] font-medium text-ink-stone">CausalGraph Research Desk</span>
    </div>

    <div className="grid min-h-[430px] lg:grid-cols-[190px_minmax(0,1fr)]">
      <aside className="hidden border-r border-hairline bg-surface-soft p-4 lg:block">
        <div className="mb-4 flex items-center gap-2 text-[12px] font-semibold text-ink">
          <Database className="h-4 w-4" />
          Knowledge base
        </div>
        {['Apple ESG Report', 'Coca-Cola Strategy', 'Costco Sustainability'].map((item, index) => (
          <div
            key={item}
            className={`mb-2 border-b border-hairline pb-3 text-[12px] leading-5 ${
              index === 0 ? 'font-semibold text-ink' : 'text-ink-steel'
            }`}
          >
            {item}
            <div className="mt-1 font-mono text-[10px] text-ink-stone">{index === 0 ? 'selected' : 'indexed'}</div>
          </div>
        ))}
      </aside>

      <div className="min-w-0 p-4 sm:p-5">
        <div className="mb-5 flex flex-wrap items-center gap-2">
          {domains.map((domain) => (
            <span key={domain.label} className="inline-flex items-center gap-2 rounded-full border border-hairline px-3 py-1 text-[12px] font-semibold text-ink-charcoal">
              <span className="h-2 w-2 rounded-full" style={{ background: domain.color }} />
              {domain.title}
            </span>
          ))}
        </div>

        <div className="ml-auto w-fit max-w-[82%] rounded-2xl rounded-br-md bg-ink px-4 py-3 text-[13px] leading-5 text-white">
          What evidence supports Apple's ESG strategy improving financial performance?
        </div>

        <div className="mt-5 grid gap-4 border-l border-hairline pl-4">
          <div>
            <div className="mb-2 inline-flex items-center gap-2 text-[12px] font-semibold text-ink">
              <BrainCircuit className="h-4 w-4" />
              Evidence-aware answer
            </div>
            <p className="text-[14px] leading-6 text-ink-charcoal">
              The current evidence supports a cautious claim: ESG strategy may improve long-term resilience,
              but a direct financial-performance claim needs revenue, margin, cost-saving, or risk-mitigation evidence.
            </p>
          </div>

          <div className="grid gap-2 sm:grid-cols-3">
            {[
              ['Cited chunks', '6'],
              ['Graph nodes', '24'],
              ['Evidence gaps', '3'],
            ].map(([value, label]) => (
              <div key={label} className="border-y border-hairline py-3">
                <div className="font-display text-[30px] font-semibold leading-none text-ink">{value}</div>
                <div className="mt-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-ink-stone">{label}</div>
              </div>
            ))}
          </div>

          <div className="rounded-xl bg-surface-soft p-4">
            <div className="mb-3 text-[12px] font-semibold uppercase tracking-[0.12em] text-ink-stone">Suggested next move</div>
            <p className="text-[13px] leading-6 text-ink-charcoal">
              Add financial metrics or rewrite the claim into a more defensible paragraph before using it in a report.
            </p>
          </div>
        </div>
      </div>
    </div>
  </div>
);

const Home: React.FC = () => {
  const [activeUseCase, setActiveUseCase] = useState(useCases[0].title);
  const [activeDomain, setActiveDomain] = useState(domains[0].label);
  const [activeEvidenceRule, setActiveEvidenceRule] = useState(0);
  const currentUseCase = useCases.find((item) => item.title === activeUseCase) || useCases[0];
  const currentDomain = domains.find((item) => item.label === activeDomain) || domains[0];
  const currentEvidenceRule = evidenceRules[activeEvidenceRule] || evidenceRules[0];

  return (
    <div className="min-h-screen overflow-x-hidden bg-canvas text-ink">
      <section className="border-b border-hairline-soft bg-canvas">
        <div className="mx-auto grid max-w-page-wide gap-10 px-4 py-14 sm:px-6 lg:grid-cols-[0.86fr_1.14fr] lg:items-center lg:px-8 lg:py-16 xl:max-w-page-xl xl:gap-14 xl:px-12 2xl:max-w-page-2xl 2xl:px-16">
          <motion.div
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.42 }}
            className="max-w-3xl"
          >
            <h1 className="font-display text-[54px] font-semibold leading-[1.02] tracking-normal text-ink sm:text-[72px] xl:text-[88px]">
              CausalGraph AI
            </h1>
            <p className="mt-6 max-w-2xl text-[18px] leading-8 text-ink-steel">
              Upload reports, ask questions, inspect the evidence, and turn ESG or business documents
              into grounded analysis instead of unsupported AI text.
            </p>
            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              <Link to="/agent" className="cg-btn-primary justify-center">
                Open research desk
                <ArrowRight className="h-4 w-4" />
              </Link>
              <Link to="/desktop" className="cg-btn-secondary justify-center">
                <Download className="h-4 w-4" />
                Download desktop
              </Link>
              <a href={githubRepositoryUrl} target="_blank" rel="noreferrer" className="cg-btn-tertiary justify-center">
                <Github className="h-4 w-4" />
                GitHub
              </a>
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.46, delay: 0.06 }}
            className="min-w-0"
          >
            <ResearchDeskPreview />
          </motion.div>
        </div>
      </section>

      <section className="border-b border-hairline-soft bg-surface-soft">
        <div className="mx-auto max-w-page-wide px-4 py-12 sm:px-6 lg:px-8 xl:max-w-page-xl xl:px-12 2xl:max-w-page-2xl 2xl:px-16">
          <div className="mb-8 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div className="max-w-3xl">
              <p className="cg-eyebrow">What it does</p>
              <h2 className="mt-3 text-heading-lg tracking-normal lg:text-[52px]">
                One workspace from raw report to usable analysis.
              </h2>
            </div>
            <p className="max-w-xl text-[16px] leading-7 text-ink-steel">
              CausalGraph is built for the moment after you receive a long document and need to write,
              compare, explain, or verify something from it.
            </p>
          </div>

          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {workflowSteps.map((item) => {
              const Icon = item.icon;
              return (
                <div key={item.title} className="cg-tool-panel p-5">
                  <div className="mb-7 flex items-center justify-between">
                    <span className="font-mono text-[12px] font-semibold text-ink-stone">{item.step}</span>
                    <Icon className="h-5 w-5 text-ink" />
                  </div>
                  <h3 className="text-[21px] font-semibold tracking-normal text-ink">{item.title}</h3>
                  <p className="mt-3 text-[14px] leading-6 text-ink-steel">{item.description}</p>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-page-wide px-4 py-14 sm:px-6 lg:px-8 xl:max-w-page-xl xl:px-12 2xl:max-w-page-2xl 2xl:px-16">
        <div className="grid gap-8 lg:grid-cols-[0.86fr_1.14fr] lg:items-start">
          <div className="lg:sticky lg:top-28">
            <p className="cg-eyebrow">Use cases</p>
            <h2 className="mt-3 text-heading-lg tracking-normal lg:text-[52px]">
              Built for business and academic work, not just chat.
            </h2>
            <p className="mt-4 max-w-xl text-[16px] leading-7 text-ink-steel">
              The product is useful when the answer must become a report paragraph, a defensible claim,
              a comparison table, or a study explanation.
            </p>
            <Link to="/agent" className="cg-btn-primary mt-7 inline-flex">
              Start with your reports
              <ArrowRight className="h-4 w-4" />
            </Link>
          </div>

          <div className="grid gap-4 rounded-2xl border border-hairline bg-white p-3 sm:grid-cols-[220px_minmax(0,1fr)]">
            <div className="flex gap-2 overflow-x-auto sm:block sm:space-y-1 sm:overflow-visible">
              {useCases.map((item) => {
                const active = item.title === activeUseCase;
                return (
                  <button
                    key={item.title}
                    type="button"
                    onClick={() => setActiveUseCase(item.title)}
                    className={`shrink-0 rounded-xl px-4 py-3 text-left text-[13px] font-semibold transition sm:w-full ${
                      active ? 'bg-ink text-white' : 'text-ink-charcoal hover:bg-surface-soft'
                    }`}
                  >
                    {item.title}
                  </button>
                );
              })}
            </div>
            <motion.div
              key={currentUseCase.title}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.24 }}
              className="min-h-[190px] rounded-xl bg-surface-soft p-5"
            >
              <h3 className="text-[24px] font-semibold tracking-normal text-ink">{currentUseCase.title}</h3>
              <p className="mt-3 max-w-2xl text-[15px] leading-7 text-ink-steel">{currentUseCase.description}</p>
              <Link to="/agent" className="cg-btn-secondary mt-6 inline-flex">
                Try this workflow
                <ArrowRight className="h-4 w-4" />
              </Link>
            </motion.div>
          </div>
        </div>
      </section>

      <section className="border-y border-hairline-soft bg-canvas">
        <div className="mx-auto grid max-w-page-wide gap-8 px-4 py-14 sm:px-6 lg:grid-cols-[1fr_1fr] lg:px-8 xl:max-w-page-xl xl:px-12 2xl:max-w-page-2xl 2xl:px-16">
          <div>
            <p className="cg-eyebrow">Knowledge graph</p>
            <h2 className="mt-3 text-heading-lg tracking-normal lg:text-[52px]">
              E, S, G, and AI stay separated enough to inspect.
            </h2>
            <p className="mt-4 max-w-2xl text-[16px] leading-7 text-ink-steel">
              The graph view groups extracted report entities into practical review lenses, then lets users
              drill down into real nodes and relationships.
            </p>
          </div>

          <div className="rounded-3xl p-4 text-white" style={{ background: currentDomain.color }}>
            <div className="flex flex-wrap gap-2">
              {domains.map((domain) => (
                <button
                  key={domain.label}
                  type="button"
                  onClick={() => setActiveDomain(domain.label)}
                  className={`h-10 min-w-10 rounded-full border px-3 text-[13px] font-semibold transition ${
                    domain.label === activeDomain
                      ? 'border-white bg-white text-ink'
                      : 'border-white/35 text-white hover:bg-white/10'
                  }`}
                >
                  {domain.label}
                </button>
              ))}
            </div>
            <motion.div
              key={currentDomain.label}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.24 }}
              className="mt-16"
            >
              <div className="flex items-center justify-between gap-4">
                <h3 className="font-display text-[44px] font-semibold leading-none text-white">{currentDomain.title}</h3>
                <Network className="h-7 w-7 opacity-80" />
              </div>
              <p className="mt-4 max-w-lg text-[15px] leading-7 text-white/82">{currentDomain.detail}</p>
              <Link to="/causal-inference" className="mt-7 inline-flex items-center gap-2 rounded-full bg-white px-4 py-2 text-[13px] font-semibold text-ink transition hover:bg-white/90">
                Explore graph
                <ArrowRight className="h-4 w-4" />
              </Link>
            </motion.div>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-page-wide px-4 py-14 sm:px-6 lg:px-8 xl:max-w-page-xl xl:px-12 2xl:max-w-page-2xl 2xl:px-16">
        <div className="grid gap-8 lg:grid-cols-[1.05fr_0.95fr] lg:items-center">
          <div>
            <p className="cg-eyebrow">Evidence contract</p>
            <h2 className="mt-3 text-heading-lg tracking-normal lg:text-[52px]">
              Every useful answer should tell you what it knows and what is missing.
            </h2>
            <p className="mt-4 max-w-2xl text-[16px] leading-7 text-ink-steel">
              This is the difference between a generic assistant and an ESG research system.
              CausalGraph keeps the source trail visible so users can use the output in real work.
            </p>
          </div>

          <div className="rounded-2xl bg-ink p-6 text-white">
            <div className="mb-6 flex items-center justify-between gap-4">
              <ShieldCheck className="h-8 w-8 text-white/80" />
              <span className="font-mono text-[12px] text-white/55">
                {activeEvidenceRule + 1}/{evidenceRules.length}
              </span>
            </div>
            <motion.p
              key={currentEvidenceRule}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.22 }}
              className="min-h-[96px] text-[20px] font-semibold leading-8 text-white"
            >
              {currentEvidenceRule}
            </motion.p>
            <div className="mt-7 grid grid-cols-4 gap-2">
              {evidenceRules.map((rule, index) => (
                <button
                  key={rule}
                  type="button"
                  onClick={() => setActiveEvidenceRule(index)}
                  className={`h-2 rounded-full transition ${
                    index === activeEvidenceRule ? 'bg-white' : 'bg-white/25 hover:bg-white/45'
                  }`}
                  aria-label={`Show evidence rule ${index + 1}`}
                />
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="border-t border-hairline-soft bg-surface-soft">
        <div className="mx-auto grid max-w-page-wide gap-8 px-4 py-14 sm:px-6 lg:grid-cols-[1fr_1fr] lg:px-8 xl:max-w-page-xl xl:px-12 2xl:max-w-page-2xl 2xl:px-16">
          <div className="cg-tool-panel p-6">
            <Github className="mb-8 h-8 w-8 text-ink" />
            <h2 className="text-[30px] font-semibold tracking-normal text-ink">Open source by default.</h2>
            <p className="mt-3 text-[15px] leading-7 text-ink-steel">
              The public repository contains the app code and configuration templates. Private keys,
              databases, vector indexes, and uploaded documents stay outside the repository.
            </p>
            <a href={githubRepositoryUrl} target="_blank" rel="noreferrer" className="cg-btn-secondary mt-6 inline-flex">
              View GitHub
              <ArrowRight className="h-4 w-4" />
            </a>
          </div>

          <div className="cg-tool-panel p-6">
            <ScreenShare className="mb-8 h-8 w-8 text-ink" />
            <h2 className="text-[30px] font-semibold tracking-normal text-ink">Desktop companion for active work.</h2>
            <p className="mt-3 text-[15px] leading-7 text-ink-steel">
              Drop reports, summarize screens, review Word drafts, and continue asking without returning
              to the browser every time your research context changes.
            </p>
            <Link to="/desktop" className="cg-btn-primary mt-6 inline-flex">
              Download desktop
              <Download className="h-4 w-4" />
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
};

export default Home;
