import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { ArrowRight, CheckCircle2, FileText, Mail, MapPin, Network, ShieldCheck } from 'lucide-react';
import { Link } from 'react-router-dom';

// MiniMax-style company page:
//   stark hero + quiet white tiles for principles + black footer-style CTA.
const About: React.FC = () => {
  const principles = [
    {
      title: 'Evidence before language',
      description: 'Answers stay anchored in retrieved passages and are presented with clear source context.',
      icon: ShieldCheck,
    },
    {
      title: 'Analyst-grade workflows',
      description: 'The interface is designed for review, comparison, and verification rather than one-off responses.',
      icon: FileText,
    },
    {
      title: 'Structured intelligence',
      description: 'Documents become searchable chunks, extracted relationships, and graph objects teams can inspect.',
      icon: Network,
    },
  ];

  const operatingAreas = [
    'ESG report question answering',
    'Sustainability disclosure review',
    'Causal relationship extraction',
    'Source-backed knowledge graph exploration',
    'Portfolio and company comparison workflows',
    'Governance, risk, and compliance research',
  ];
  const [activePrinciple, setActivePrinciple] = useState(principles[0].title);
  const [activeArea, setActiveArea] = useState(operatingAreas[0]);
  const currentPrinciple = principles.find((principle) => principle.title === activePrinciple) || principles[0];
  const CurrentPrincipleIcon = currentPrinciple.icon;

  return (
    <div className="min-h-screen bg-canvas text-ink">
      {/* ============== HERO ============== */}
      <section className="border-b" style={{ borderColor: 'var(--cg-hairline-soft)' }}>
        <div className="mx-auto max-w-page px-4 lg:max-w-page-wide xl:max-w-page-xl xl:px-12 2xl:max-w-page-2xl 2xl:px-16 py-section-lg sm:px-6 lg:px-8">
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45 }}
            className="max-w-4xl"
          >
            <h1
              className="font-display text-[40px] font-semibold sm:text-[56px] xl:text-[80px] 2xl:text-[96px]"
              style={{ lineHeight: 1.10, letterSpacing: 0 }}
            >
              We build evidence systems for ESG and risk teams.
            </h1>
            <p className="mt-6 max-w-3xl text-subtitle text-ink-steel xl:mt-8 xl:max-w-4xl xl:text-[20px] 2xl:text-[22px]">
              CausalGraph helps teams turn long-form corporate disclosures into verifiable answers,
              extracted relationships, and reviewable knowledge graphs. Designed for analysts who
              need to move quickly without losing the audit trail.
            </p>
          </motion.div>
        </div>
      </section>

      {/* ============== PRINCIPLES ============== */}
      <section className="mx-auto max-w-page px-4 lg:max-w-page-wide xl:max-w-page-xl xl:px-12 2xl:max-w-page-2xl 2xl:px-16 py-section sm:px-6 lg:px-8">
        <div className="mb-section-sm max-w-2xl">
          <p className="cg-eyebrow">Principles</p>
          <h2
            className="mt-3 text-heading-lg xl:text-[56px] 2xl:text-[64px]"
            style={{ letterSpacing: 0, lineHeight: 1.10 }}
          >
            What we anchor every decision to.
          </h2>
        </div>
        <div className="grid gap-4 rounded-2xl border border-hairline bg-white p-3 lg:grid-cols-[260px_minmax(0,1fr)]">
          <div className="flex gap-2 overflow-x-auto lg:block lg:space-y-1 lg:overflow-visible">
            {principles.map((principle) => (
              <button
                key={principle.title}
                type="button"
                onClick={() => setActivePrinciple(principle.title)}
                className={`shrink-0 rounded-xl px-4 py-3 text-left text-[13px] font-semibold transition lg:w-full ${
                  activePrinciple === principle.title
                    ? 'bg-ink text-white'
                    : 'text-ink-charcoal hover:bg-surface-soft'
                }`}
              >
                {principle.title}
              </button>
            ))}
          </div>
          <motion.div
            key={currentPrinciple.title}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.24 }}
            className="min-h-[220px] rounded-xl bg-surface-soft p-6"
          >
            <div className="mb-6 flex h-11 w-11 items-center justify-center rounded-full bg-white text-ink">
              <CurrentPrincipleIcon className="h-5 w-5" />
            </div>
            <h3 className="text-[28px] font-semibold tracking-normal text-ink">{currentPrinciple.title}</h3>
            <p className="mt-3 max-w-2xl text-body-md text-ink-steel">{currentPrinciple.description}</p>
          </motion.div>
        </div>
      </section>

      {/* ============== FOCUS AREAS ============== */}
      <section
        className="border-y"
        style={{ borderColor: 'var(--cg-hairline-soft)', background: 'var(--cg-surface-soft)' }}
      >
        <div className="mx-auto grid max-w-page lg:max-w-page-wide xl:max-w-page-xl 2xl:max-w-page-2xl gap-12 px-4 py-section sm:px-6 lg:grid-cols-[0.85fr,1.15fr] lg:px-8">
          <div>
            <p className="cg-eyebrow">Focus</p>
            <h2
              className="mt-3 text-heading-lg xl:text-[56px] 2xl:text-[64px]"
              style={{ letterSpacing: 0, lineHeight: 1.10 }}
            >
              What we focus on
            </h2>
            <p className="mt-4 max-w-md text-body-md text-ink-steel">
              The platform is built around high-trust document workflows where the source text
              matters as much as the final answer.
            </p>
          </div>
          <div className="rounded-2xl border border-hairline bg-canvas p-3">
            <div className="flex flex-wrap gap-2">
              {operatingAreas.map((area) => (
                <button
                  key={area}
                  type="button"
                  onClick={() => setActiveArea(area)}
                  className={`rounded-full border px-3 py-2 text-[13px] font-semibold transition ${
                    activeArea === area
                      ? 'border-ink bg-ink text-white'
                      : 'border-hairline bg-white text-ink-charcoal hover:border-ink'
                  }`}
                >
                  {area}
                </button>
              ))}
            </div>
            <motion.div
              key={activeArea}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.22 }}
              className="mt-4 flex items-start gap-3 rounded-xl bg-surface-soft p-5"
            >
              <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-ink-steel" />
              <div>
                <h3 className="text-[20px] font-semibold text-ink">{activeArea}</h3>
                <p className="mt-2 text-body-sm text-ink-steel">
                  This workflow stays evidence-first: source text, extracted relationships, and review context remain close to the final answer.
                </p>
              </div>
            </motion.div>
          </div>
        </div>
      </section>

      {/* ============== DOMAIN PRODUCT CARDS ============== */}
      <section className="mx-auto max-w-page px-4 lg:max-w-page-wide xl:max-w-page-xl xl:px-12 2xl:max-w-page-2xl 2xl:px-16 py-section sm:px-6 lg:px-8">
        <div className="grid gap-4 md:grid-cols-3">
          <div className="cg-product-card cg-product-card--coral flex h-full min-h-[200px] flex-col justify-between">
            <p className="text-caption font-semibold uppercase" style={{ letterSpacing: '0.08em', opacity: 0.78 }}>
              Domain
            </p>
            <div>
              <h3 className="font-display text-[40px] font-semibold leading-none xl:text-[48px] 2xl:text-[56px]" style={{ letterSpacing: 0 }}>
                ESG
              </h3>
              <p className="mt-3 text-body-sm" style={{ opacity: 0.86 }}>
                Disclosure analysis, targets, emissions, governance, and risk review.
              </p>
            </div>
          </div>
          <div className="cg-product-card cg-product-card--blue flex h-full min-h-[200px] flex-col justify-between">
            <p className="text-caption font-semibold uppercase" style={{ letterSpacing: '0.08em', opacity: 0.82 }}>
              Capability
            </p>
            <div>
              <h3 className="font-display text-[40px] font-semibold leading-none xl:text-[48px] 2xl:text-[56px]" style={{ letterSpacing: 0 }}>
                Graph
              </h3>
              <p className="mt-3 text-body-sm" style={{ opacity: 0.86 }}>
                Relationship extraction and causal graph exploration from unstructured text.
              </p>
            </div>
          </div>
          <div className="cg-product-card cg-product-card--purple flex h-full min-h-[200px] flex-col justify-between">
            <p className="text-caption font-semibold uppercase" style={{ letterSpacing: '0.08em', opacity: 0.86 }}>
              Reasoning
            </p>
            <div>
              <h3 className="font-display text-[40px] font-semibold leading-none xl:text-[48px] 2xl:text-[56px]" style={{ letterSpacing: 0 }}>
                RAG
              </h3>
              <p className="mt-3 text-body-sm" style={{ opacity: 0.86 }}>
                Retrieval-first answers with source passages available for verification.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ============== CONTACT ============== */}
      <section
        className="border-t"
        style={{ borderColor: 'var(--cg-hairline-soft)' }}
      >
        <div className="mx-auto grid max-w-page lg:max-w-page-wide xl:max-w-page-xl 2xl:max-w-page-2xl gap-8 px-4 py-section sm:px-6 md:grid-cols-2 lg:px-8">
          <div>
            <p className="cg-eyebrow">Contact</p>
            <h2 className="mt-3 text-heading-md font-semibold" style={{ letterSpacing: 0 }}>
              Talk to us.
            </h2>
            <p className="mt-4 max-w-xl text-body-md text-ink-steel">
              For product discussions, implementation support, or workflow evaluation, contact the
              CausalGraph team.
            </p>
            <Link to="/login" className="cg-btn-primary mt-6 inline-flex">
              Open the workspace
              <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
          <div className="space-y-3">
            <div className="flex items-center gap-3 rounded-xl border bg-canvas p-4"
                 style={{ borderColor: 'var(--cg-hairline)' }}>
              <Mail className="h-4 w-4 text-ink-steel" />
              <span className="text-body-sm text-ink-charcoal">contact@causalgraph.ai</span>
            </div>
            <div className="flex items-center gap-3 rounded-xl border bg-canvas p-4"
                 style={{ borderColor: 'var(--cg-hairline)' }}>
              <MapPin className="h-4 w-4 text-ink-steel" />
              <span className="text-body-sm text-ink-charcoal">Product and engineering teams in Australia</span>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
};

export default About;
