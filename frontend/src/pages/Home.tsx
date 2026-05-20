import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { Link } from 'react-router-dom';
import {
  ArrowRight,
  BarChart3,
  BrainCircuit,
  ChevronLeft,
  ChevronRight,
  Database,
  FileCheck2,
  FileSearch,
  GitBranch,
  Leaf,
  Network,
  ShieldCheck,
  Sparkles,
  Users,
} from 'lucide-react';

const demoVideoUrl = 'https://www.youtube-nocookie.com/embed/vju2vpjyhsw?rel=0&modestbranding=1';

const Home: React.FC = () => {
  const [activeShowcase, setActiveShowcase] = useState(0);

  const showcaseSlides = [
    {
      key: 'agent',
      label: 'Agent',
      eyebrow: 'CausalGraph Agent',
      title: 'Ask ESG questions. Get cited answers, graph context, and next steps.',
      description:
        'A research assistant that routes intent, searches private reports and global ESG knowledge, then returns evidence-backed responses in one workspace.',
    },
    {
      key: 'matrix',
      label: 'Matrix',
      eyebrow: 'ESG Intelligence Matrix',
      title: 'Four ESG lenses, one intelligence layer.',
      description:
        'Move between environment, social, governance, and AI reasoning without exposing raw database internals to end users.',
    },
    {
      key: 'demo',
      label: 'Demo',
      eyebrow: 'Workflow Demo',
      title: 'See the full loop from upload to answer.',
      description:
        'Watch reports become chunks, vectors, graph records, retrieved evidence, and final cited answers.',
    },
  ];

  const agentHighlights = [
    {
      icon: GitBranch,
      title: 'Plan the query',
      description: 'Routes intent, rewrites follow-ups, and decomposes complex ESG questions only when needed.',
    },
    {
      icon: FileSearch,
      title: 'Know your corpus',
      description: 'Searches private uploads plus global ESG knowledge with vector, BM25, layered, and graph retrieval.',
    },
    {
      icon: FileCheck2,
      title: 'Return the trail',
      description: 'Keeps citations, graph sources, timings, and prediction reasoning attached to the response.',
    },
  ];

  const domainCards = [
    {
      key: 'environmental',
      label: 'Environmental',
      title: 'Emissions',
      caption: 'Range I-III GHG, energy mix, water stewardship.',
      icon: Leaf,
      to: '/agent',
      background: 'var(--cg-domain-e)',
    },
    {
      key: 'social',
      label: 'Social',
      title: 'Workforce',
      caption: 'Diversity, safety, labour, community impact.',
      icon: Users,
      to: '/agent',
      background: 'var(--cg-domain-s)',
    },
    {
      key: 'governance',
      label: 'Governance',
      title: 'Controls',
      caption: 'Board independence, audit posture, policies.',
      icon: ShieldCheck,
      to: '/agent',
      background: 'var(--cg-domain-g)',
    },
    {
      key: 'ai',
      label: 'AI Insight',
      title: 'Reasoning',
      caption: 'RAG, graph context, prediction with evidence.',
      icon: Sparkles,
      to: '/causal-inference',
      background: 'var(--cg-domain-ai)',
    },
  ];

  const capabilities = [
    {
      icon: FileSearch,
      title: 'Evidence first',
      description: 'Answers are grounded in source passages, citations, and selected report context.',
    },
    {
      icon: Network,
      title: 'Graph-aware',
      description: 'Entities and relationships stay available for causal paths and graph-backed reasoning.',
    },
    {
      icon: BrainCircuit,
      title: 'Flash or deep',
      description: 'Fast responses for simple requests, deeper planning for multi-hop research questions.',
    },
    {
      icon: BarChart3,
      title: 'Reviewable outputs',
      description: 'Summaries, predictions, and answers keep enough structure for audit and iteration.',
    },
  ];

  const changeSlide = (direction: number) => {
    setActiveShowcase((current) => (current + direction + showcaseSlides.length) % showcaseSlides.length);
  };

  const renderAgentVisual = () => (
    <div className="grid h-full overflow-hidden rounded-2xl border border-hairline bg-surface-soft p-3 lg:grid-cols-[210px_minmax(0,1fr)_240px]">
      <div className="hidden min-h-0 border-r border-hairline pr-3 lg:block">
        <div className="mb-3 flex items-center justify-between">
          <span className="cg-eyebrow text-ink-steel">Library</span>
          <span className="font-mono text-[11px] text-ink-stone">18</span>
        </div>
        {['NVIDIA FY2025 Sustainability Report', 'Climate risk controls', 'Supplier code review'].map((title, index) => (
          <div key={title} className={`mb-2 rounded-lg border p-3 ${index === 0 ? 'border-ink bg-white' : 'border-hairline bg-white/70'}`}>
            <div className="line-clamp-2 text-[12px] font-semibold leading-5 text-ink">{title}</div>
            <div className="mt-2 flex items-center gap-2 text-[11px] text-ink-steel">
              <Database className="h-3 w-3" />
              <span>{index === 0 ? '42 concepts' : 'indexed'}</span>
            </div>
          </div>
        ))}
      </div>
      <div className="min-w-0 px-0 sm:px-3">
        <div className="rounded-xl border border-hairline bg-white p-4">
          <div className="mb-4 flex items-center justify-between border-b border-hairline pb-3">
            <div>
              <span className="cg-eyebrow text-ink-steel">Research answer</span>
              <h3 className="mt-1 text-[18px] font-semibold leading-6 text-ink">How did emissions change?</h3>
            </div>
            <span className="rounded-full bg-success-bg px-2.5 py-1 text-[11px] font-semibold text-success">Cited</span>
          </div>
          <div className="space-y-2 text-[13px] leading-6 text-ink-charcoal">
            <p>NVIDIA reports reduced market-based scope 2 emissions and connects the movement to renewable electricity procurement.</p>
            <p className="rounded-lg bg-surface-soft p-3 text-[12px] text-ink-steel">
              Evidence: sustainability report excerpt, emissions table, renewable electricity target.
            </p>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            {['Report p.14', 'Scope 2', 'Renewables'].map((label) => (
              <span key={label} className="rounded-md border border-hairline bg-white px-2 py-1 text-[11px] font-medium text-ink-charcoal">
                {label}
              </span>
            ))}
          </div>
        </div>
        <div className="mt-3 grid gap-3 sm:grid-cols-3">
          {agentHighlights.map((item) => {
            const Icon = item.icon;
            return (
              <div key={item.title} className="rounded-xl border border-hairline bg-white p-4">
                <Icon className="mb-3 h-4 w-4 text-ink-steel" />
                <h3 className="text-[14px] font-semibold">{item.title}</h3>
                <p className="mt-1 line-clamp-2 text-[12px] leading-5 text-ink-steel">{item.description}</p>
              </div>
            );
          })}
        </div>
      </div>
      <div className="hidden min-h-0 border-l border-hairline pl-3 lg:block">
        <div className="mb-3 flex items-center justify-between">
          <span className="cg-eyebrow text-ink-steel">Evidence</span>
          <span className="font-mono text-[11px] text-ink-stone">3 hits</span>
        </div>
        <div className="space-y-2">
          {['Scope 2 market-based emissions', 'Renewable electricity target', 'Board climate oversight'].map((item, index) => (
            <div key={item} className="rounded-lg border border-hairline bg-white p-3">
              <div className="text-[12px] font-semibold text-ink">{item}</div>
              <div className="mt-1 text-[11px] text-ink-steel">{82 - index * 9}% relevance</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );

  const renderMatrixVisual = () => (
    <div className="grid h-full grid-cols-2 gap-4 lg:grid-cols-4">
      {domainCards.map((card) => {
        const Icon = card.icon;
        return (
          <Link
            key={card.key}
            to={card.to}
            className="group relative overflow-hidden rounded-2xl p-5 text-white transition hover:-translate-y-0.5"
            style={{ background: card.background }}
          >
            <div className="relative flex h-full min-h-[250px] flex-col">
              <div className="flex items-center justify-between gap-3">
                <span className="text-[11px] font-bold uppercase tracking-[0.12em] text-white/90">{card.label}</span>
                <span className="rounded-full bg-white/95 px-2.5 py-1 text-[10px] font-bold text-ink">NEW</span>
              </div>
              <h3 className="mt-16 font-display text-[32px] font-semibold leading-none tracking-normal text-white">
                {card.title}
              </h3>
              <div className="mt-auto">
                <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-full border border-white/20 bg-black/10 backdrop-blur">
                  <Icon className="h-5 w-5" />
                </div>
                <p className="text-[13px] font-medium leading-6 text-white">{card.caption}</p>
              </div>
            </div>
          </Link>
        );
      })}
    </div>
  );

  const renderDemoVisual = () => (
    <div className="relative mx-auto max-w-4xl overflow-hidden rounded-2xl border border-hairline bg-ink">
      <div className="aspect-video">
        <iframe
          className="h-full w-full"
          src={demoVideoUrl}
          title="CausalGraphAI demonstration video"
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
          referrerPolicy="strict-origin-when-cross-origin"
          allowFullScreen
        />
      </div>
    </div>
  );

  const renderShowcaseVisual = () => {
    if (activeShowcase === 1) return renderMatrixVisual();
    if (activeShowcase === 2) return renderDemoVisual();
    return renderAgentVisual();
  };

  const activeSlide = showcaseSlides[activeShowcase];

  return (
    <div className="min-h-screen bg-canvas text-ink">
      <section className="relative overflow-hidden border-b border-hairline-soft bg-canvas">
        <div className="mx-auto max-w-page-wide px-4 py-9 sm:px-6 lg:px-8 lg:py-11 xl:max-w-page-xl 2xl:max-w-page-2xl">
          <motion.div
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.42 }}
            className="mx-auto max-w-4xl text-center"
          >
            <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-hairline bg-white/80 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-ink-steel shadow-sm backdrop-blur">
              <BrainCircuit className="h-3.5 w-3.5 text-ink" />
              <span>{activeSlide.eyebrow}</span>
            </div>
            <h1 className="font-display text-[46px] font-semibold leading-[1.02] tracking-normal text-ink sm:text-[64px] lg:text-[78px]">
              {activeShowcase === 1
                ? 'ESG Intelligence Matrix'
                : activeShowcase === 2
                  ? 'CausalGraph Demo'
                  : 'CausalGraph Agent'}
            </h1>
            <p className="mx-auto mt-5 max-w-3xl text-[16px] leading-7 text-ink-steel sm:text-[18px]">
              {activeShowcase === 1
                ? 'Unified intelligence across Environment, Social, Governance, and AI Insight. Actionable data, smarter decisions, and sustainable impact.'
                : activeShowcase === 2
                  ? 'Watch the ESG intelligence workflow in action: upload reports, retrieve evidence, reason over graph context, and generate cited answers.'
                  : 'Intelligent ESG research assistant for report search, evidence-backed answers, graph reasoning, and scenario analysis.'}
            </p>

            <div className="mt-6 flex flex-col items-center justify-center gap-3 sm:flex-row">
              <Link to="/agent" className="cg-btn-primary justify-center sm:min-w-[160px]">
                {activeShowcase === 2 ? 'Try Agent Now' : 'Open Agent'}
              </Link>
              <Link
                to={activeShowcase === 1 ? '/agent' : '/agent?tier=deep'}
                className="cg-btn-primary justify-center sm:min-w-[160px]"
              >
                {activeShowcase === 1 ? 'Start Research' : 'Try Deep Mode'}
              </Link>
              <Link to="/about" className="cg-btn-secondary justify-center sm:min-w-[160px]">
                Learn More
              </Link>
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.46, delay: 0.06 }}
            className="relative mx-auto mt-9 max-w-6xl"
          >
            <button
              type="button"
              onClick={() => changeSlide(-1)}
              className="absolute -left-4 top-1/2 z-20 hidden h-11 w-11 -translate-y-1/2 items-center justify-center rounded-full border border-hairline bg-white/90 text-ink shadow-card transition hover:bg-white md:flex"
              aria-label="Previous showcase"
            >
              <ChevronLeft className="h-5 w-5" />
            </button>
            <div className="cg-tool-panel p-3">
              <div className={activeShowcase === 2 ? 'overflow-visible' : 'h-[330px] overflow-hidden lg:h-[370px]'}>
                {renderShowcaseVisual()}
              </div>
              <div className="flex flex-col gap-3 px-3 pt-4 sm:flex-row sm:items-center sm:justify-between">
                <p className="max-w-3xl text-left text-[13px] leading-5 text-ink-steel">{activeSlide.description}</p>
                <div className="flex shrink-0 items-center gap-2">
                  {showcaseSlides.map((slide, index) => (
                    <button
                      key={slide.key}
                      type="button"
                      onClick={() => setActiveShowcase(index)}
                      className={`h-2 rounded-full transition-all ${
                        activeShowcase === index ? 'w-8 bg-ink' : 'w-2 bg-ink/25 hover:bg-ink/45'
                      }`}
                      aria-label={`Show ${slide.label}`}
                    />
                  ))}
                </div>
              </div>
            </div>
            <button
              type="button"
              onClick={() => changeSlide(1)}
              className="absolute -right-4 top-1/2 z-20 hidden h-11 w-11 -translate-y-1/2 items-center justify-center rounded-full border border-hairline bg-white/90 text-ink shadow-card transition hover:bg-white md:flex"
              aria-label="Next showcase"
            >
              <ChevronRight className="h-5 w-5" />
            </button>
          </motion.div>
        </div>
      </section>

      <section className="border-b border-hairline-soft bg-surface-soft">
        <div className="mx-auto max-w-page-wide px-4 py-14 sm:px-6 lg:px-8 xl:max-w-page-xl 2xl:max-w-page-2xl">
          <div className="mb-8 flex flex-col justify-between gap-4 lg:flex-row lg:items-end">
            <div className="max-w-2xl">
              <p className="cg-eyebrow">Built for review</p>
              <h2 className="mt-3 text-heading-lg tracking-normal lg:text-[52px]">
                Every answer keeps the evidence close.
              </h2>
            </div>
            <p className="max-w-xl text-[16px] leading-7 text-ink-steel">
              CausalGraph separates private user uploads from the global ESG knowledge layer while preserving retrieval breadth for questions that need external context.
            </p>
          </div>

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {capabilities.map((capability, idx) => {
              const Icon = capability.icon;
              return (
                <motion.div
                  key={capability.title}
                  initial={{ opacity: 0, y: 12 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.35, delay: idx * 0.04 }}
                  viewport={{ once: true }}
                  className="cg-tool-panel p-6"
                >
                  <div className="mb-5 flex h-11 w-11 items-center justify-center rounded-full bg-surface-soft text-ink">
                    <Icon className="h-5 w-5" />
                  </div>
                  <h3 className="text-[20px] font-semibold tracking-normal">{capability.title}</h3>
                  <p className="mt-2 text-[14px] leading-6 text-ink-steel">{capability.description}</p>
                </motion.div>
              );
            })}
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-page-wide px-4 py-14 sm:px-6 lg:px-8 xl:max-w-page-xl 2xl:max-w-page-2xl">
        <div className="grid gap-8 lg:grid-cols-[0.85fr_1.15fr] lg:items-center">
          <div>
            <p className="cg-eyebrow">Operating model</p>
            <h2 className="mt-3 text-heading-lg tracking-normal lg:text-[52px]">
              From disclosure text to reviewable intelligence.
            </h2>
            <p className="mt-4 max-w-xl text-[16px] leading-7 text-ink-steel">
              Uploads become searchable chunks, vectors, and graph records. The agent decides when to answer directly, when to retrieve more evidence, and when deeper reasoning is needed.
            </p>
            <Link to="/agent" className="cg-btn-primary mt-7 inline-flex">
              Try the workspace
              <ArrowRight className="h-4 w-4" />
            </Link>
          </div>

          <div className="cg-tool-panel p-4">
            <div className="grid gap-3 sm:grid-cols-2">
              {[
                ['01', 'Ingest', 'Parse files, chunk report text, preserve document ownership.'],
                ['02', 'Retrieve', 'Search private corpus and global ESG knowledge with hybrid retrieval.'],
                ['03', 'Reason', 'Use flash or deep routing depending on query complexity.'],
                ['04', 'Review', 'Return answer, citations, graph traces, and timing signals.'],
              ].map(([step, title, body]) => (
                <div key={step} className="rounded-xl bg-surface-soft p-5">
                  <div className="mb-6 flex items-center justify-between">
                    <span className="font-mono text-[12px] font-semibold text-ink-stone">{step}</span>
                    <Database className="h-4 w-4 text-ink-stone" />
                  </div>
                  <h3 className="text-[22px] font-semibold tracking-normal">{title}</h3>
                  <p className="mt-2 text-[14px] leading-6 text-ink-steel">{body}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-page-wide px-4 pb-16 sm:px-6 lg:px-8 xl:max-w-page-xl 2xl:max-w-page-2xl">
        <div className="overflow-hidden rounded-2xl bg-ink p-8 text-white sm:p-10 lg:flex lg:items-center lg:justify-between lg:gap-10">
          <div className="max-w-3xl">
            <p className="text-[12px] font-semibold uppercase tracking-[0.14em] text-white/55">Get started</p>
            <h2 className="mt-3 font-display text-[38px] font-semibold leading-tight tracking-normal text-white sm:text-[48px]">
              Bring reports in. Ask questions out. Keep the evidence attached.
            </h2>
          </div>
          <div className="mt-7 flex flex-col gap-3 sm:flex-row lg:mt-0">
            <Link to="/login" className="cg-btn-tertiary justify-center">
              Sign in
            </Link>
            <Link to="/agent" className="inline-flex items-center justify-center gap-2 rounded-full border border-white/30 px-6 py-3 text-[14px] font-semibold text-white transition hover:bg-white/10">
              Open Agent
              <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
};

export default Home;
