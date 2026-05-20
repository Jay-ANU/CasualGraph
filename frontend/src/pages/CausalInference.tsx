import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import {
  ArrowRight,
  Database,
  FileText,
  GitBranch,
  Network,
  Search,
} from 'lucide-react';
import { GraphVisualizer } from '../components';
import type { GraphData, GraphHighlightPath } from '../types/graph';

const graphEnginePreviewGraph: GraphData = {
  nodes: [
    { id: 'company', label: 'Company', domain: 'general', type: 'Company', confidence: 0.98 },
    { id: 'climate_target', label: 'Climate target', domain: 'environmental', type: 'Target', confidence: 0.9 },
    { id: 'scope_2', label: 'Scope 2', domain: 'environmental', type: 'Metric', confidence: 0.86 },
    { id: 'transition_risk', label: 'Transition risk', domain: 'governance', type: 'Risk', confidence: 0.8 },
    { id: 'evidence', label: 'Evidence', domain: 'general', type: 'Source passage', confidence: 0.92 },
  ],
  edges: [
    {
      source: 'company',
      target: 'climate_target',
      relationship_type: 'HAS_TARGET',
      confidence: 0.88,
      evidence: 'The company states a climate target in the report.',
      domain: 'environmental',
    },
    {
      source: 'company',
      target: 'scope_2',
      relationship_type: 'REPORTS_METRIC',
      confidence: 0.84,
      evidence: 'Scope 2 emissions are disclosed in the emissions table.',
      domain: 'environmental',
    },
    {
      source: 'transition_risk',
      target: 'company',
      relationship_type: 'AFFECTS',
      confidence: 0.72,
      evidence: 'Transition risk is discussed in governance oversight.',
      domain: 'governance',
    },
    {
      source: 'evidence',
      target: 'climate_target',
      relationship_type: 'SUPPORTS',
      confidence: 0.9,
      evidence: 'Source passage supports the extracted target.',
      domain: 'general',
    },
  ],
  metadata: {
    node_count: 5,
    edge_count: 4,
    is_directed: true,
    is_acyclic: false,
  },
};

const graphEnginePreviewPath: GraphHighlightPath = {
  nodes: ['company', 'climate_target', 'evidence'],
  edges: [['company', 'climate_target'], ['evidence', 'climate_target']],
};

const CausalInference: React.FC = () => {
  const [selectedWorkflow, setSelectedWorkflow] = useState('disclosures');
  const navigate = useNavigate();

  const pipeline = [
    {
      title: 'Parse',
      description: 'Clean report sections, tables, and source snippets.',
      icon: FileText,
    },
    {
      title: 'Extract',
      description: 'Detect entities, metrics, targets, risks, and claims.',
      icon: Database,
    },
    {
      title: 'Connect',
      description: 'Build evidence-linked relationships and graph paths.',
      icon: GitBranch,
    },
    {
      title: 'Retrieve',
      description: 'Use graph context to narrow RAG and cite sources.',
      icon: Search,
    },
  ];

  const workflows = [
    {
      id: 'disclosures',
      name: 'Disclosure Review',
      description: 'Find emissions movement, targets, climate risk statements, and governance controls.',
      prompt: 'Where does Apple explain climate targets, and what evidence supports the claim?',
      inputs: 'Report sections',
      outputs: 'Source-backed claims',
      review: 'Cited snippets',
      tags: ['Emissions', 'Targets', 'Governance', 'Risk'],
    },
    {
      id: 'supply-chain',
      name: 'Supply Chain Trace',
      description: 'Track supplier requirements, human-rights policies, audit signals, and remediation actions.',
      prompt: 'Which supplier policy statements connect to audit or remediation evidence?',
      inputs: 'Policies and actors',
      outputs: 'Responsibility paths',
      review: 'Audit trail',
      tags: ['Suppliers', 'Audit', 'Policy', 'Remediation'],
    },
    {
      id: 'portfolio',
      name: 'Portfolio Screening',
      description: 'Ask consistent graph-backed questions across company reports and compare answers.',
      prompt: 'Compare climate risk controls across the selected companies.',
      inputs: 'Companies',
      outputs: 'Comparable metrics',
      review: 'Benchmark evidence',
      tags: ['Benchmarking', 'Screening', 'Evidence'],
    },
  ];

  const selected = workflows.find((workflow) => workflow.id === selectedWorkflow) || workflows[0];

  return (
    <div className="min-h-screen bg-canvas text-ink">
      <section className="border-b border-hairline-soft">
        <div className="mx-auto grid max-w-page gap-10 px-4 py-16 sm:px-6 lg:max-w-page-wide lg:grid-cols-[0.95fr_1.05fr] lg:px-8 lg:py-20 xl:max-w-page-xl xl:px-12 2xl:max-w-page-2xl 2xl:px-16">
          <motion.div
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.42 }}
            className="flex flex-col justify-center"
          >
            <div className="mb-6 inline-flex w-fit items-center gap-2 rounded-full border border-hairline bg-surface px-3 py-2 text-[13px] font-semibold text-ink-charcoal">
              <Network className="h-4 w-4" />
              Graph Engine
            </div>
            <h1 className="font-display text-[46px] font-semibold leading-[1.02] tracking-normal text-ink sm:text-[68px] xl:text-[84px]">
              Structure before
              <br />
              synthesis.
            </h1>
            <p className="mt-7 max-w-2xl text-[17px] leading-8 text-ink-steel xl:text-[19px]">
              CausalGraph turns ESG reports into a reviewable knowledge graph first, then uses that structure to ground retrieval, citations, and agent reasoning.
            </p>
            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              <button onClick={() => navigate('/agent')} className="cg-btn-primary justify-center">
                Open research desk
                <ArrowRight className="h-4 w-4" />
              </button>
              <button onClick={() => navigate('/about')} className="cg-btn-secondary justify-center">
                View architecture
              </button>
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.46, delay: 0.06 }}
            className="cg-tool-panel p-4"
          >
            <div className="rounded-xl bg-surface-soft p-5">
              <div className="flex items-center justify-between gap-4 border-b border-hairline pb-4">
                <div>
                  <div className="cg-eyebrow text-ink-stone">Knowledge map</div>
                  <div className="mt-1 text-[18px] font-semibold text-ink">Report evidence graph</div>
                </div>
                <span className="rounded-full bg-success-bg px-3 py-1 text-[12px] font-semibold text-success">Live</span>
              </div>

              <div className="mt-5">
                <GraphVisualizer
                  graph={graphEnginePreviewGraph}
                  compact
                  height={340}
                  focusNodeId="company"
                  highlightPath={graphEnginePreviewPath}
                />
              </div>

              <div className="mt-4 grid gap-3 sm:grid-cols-3">
                {[
                  ['26k+', 'entities'],
                  ['19k+', 'edges'],
                  ['cited', 'relationships'],
                ].map(([value, label]) => (
                  <div key={label} className="rounded-2xl border border-hairline bg-white p-4">
                    <div className="font-display text-[28px] font-semibold leading-none tracking-normal">{value}</div>
                    <div className="mt-1 text-[12px] uppercase tracking-[0.14em] text-ink-stone">{label}</div>
                  </div>
                ))}
              </div>
            </div>
          </motion.div>
        </div>
      </section>

      <section className="mx-auto max-w-page px-4 py-section sm:px-6 lg:max-w-page-wide lg:px-8 xl:max-w-page-xl xl:px-12 2xl:max-w-page-2xl 2xl:px-16">
        <div className="mb-8 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div className="max-w-3xl">
            <p className="cg-eyebrow">Pipeline</p>
            <h2 className="mt-3 text-heading-lg xl:text-[56px]" style={{ letterSpacing: 0, lineHeight: 1.1 }}>
              One graph path from document to answer.
            </h2>
          </div>
          <div className="hidden h-px flex-1 bg-hairline md:block" />
        </div>

        <div className="grid gap-3 lg:grid-cols-4">
          {pipeline.map((item, idx) => {
            const Icon = item.icon;
            return (
              <motion.div
                key={item.title}
                initial={{ opacity: 0, y: 12 }}
                whileInView={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.34, delay: idx * 0.04 }}
                viewport={{ once: true }}
                className="cg-tool-panel relative p-5"
              >
                <div className="mb-6 flex items-center justify-between">
                  <div className="flex h-11 w-11 items-center justify-center rounded-full bg-surface text-ink">
                    <Icon className="h-5 w-5" />
                  </div>
                  <span className="text-[12px] font-semibold text-ink-stone">0{idx + 1}</span>
                </div>
                <h3 className="text-card-title font-semibold text-ink">{item.title}</h3>
                <p className="mt-2 text-body-sm text-ink-steel">{item.description}</p>
              </motion.div>
            );
          })}
        </div>
      </section>

      <section className="border-y border-hairline-soft bg-surface-soft">
        <div className="mx-auto max-w-page px-4 py-section sm:px-6 lg:max-w-page-wide lg:px-8 xl:max-w-page-xl xl:px-12 2xl:max-w-page-2xl 2xl:px-16">
          <div className="mb-8 max-w-3xl">
            <p className="cg-eyebrow">Workflow lens</p>
            <h2 className="mt-3 text-heading-lg xl:text-[56px]" style={{ letterSpacing: 0, lineHeight: 1.1 }}>
              Select the review job.
            </h2>
            <p className="mt-4 text-body-md text-ink-steel xl:text-[18px]">
              The graph engine is the same; the lens changes which entities, edges, and evidence trails are prioritised.
            </p>
          </div>

          <div className="grid gap-6 lg:grid-cols-[360px_minmax(0,1fr)]">
            <div className="space-y-2">
              {workflows.map((workflow) => {
                const active = selectedWorkflow === workflow.id;
                return (
                  <button
                    key={workflow.id}
                    onClick={() => setSelectedWorkflow(workflow.id)}
                    className={`w-full rounded-2xl border px-4 py-4 text-left transition ${
                      active ? 'border-ink bg-white shadow-sm' : 'border-transparent bg-transparent hover:border-hairline hover:bg-white/70'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-4">
                      <span className="font-semibold text-ink">{workflow.name}</span>
                      <span className={`h-2 w-2 rounded-full ${active ? 'bg-ink' : 'bg-hairline'}`} />
                    </div>
                    <p className="mt-2 text-body-sm text-ink-steel">{workflow.description}</p>
                  </button>
                );
              })}
            </div>

            <motion.div
              key={selected.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.28 }}
              className="cg-tool-panel p-6 xl:p-8"
            >
              <div className="flex flex-col gap-6">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <div className="cg-eyebrow text-ink-stone">Example prompt</div>
                    <h3 className="mt-3 max-w-3xl font-display text-[32px] font-semibold leading-[1.12] tracking-normal text-ink">
                      {selected.prompt}
                    </h3>
                  </div>
                  <button onClick={() => navigate('/agent')} className="cg-btn-primary shrink-0">
                    Run in agent
                    <ArrowRight className="h-4 w-4" />
                  </button>
                </div>

                <div className="grid gap-3 md:grid-cols-3">
                  {[
                    ['Inputs', selected.inputs],
                    ['Outputs', selected.outputs],
                    ['Review', selected.review],
                  ].map(([label, value]) => (
                    <div key={label} className="rounded-2xl border border-hairline bg-surface p-5">
                      <div className="cg-eyebrow text-ink-stone">{label}</div>
                      <div className="mt-2 text-[16px] font-semibold text-ink">{value}</div>
                    </div>
                  ))}
                </div>

                <div className="flex flex-wrap gap-2">
                  {selected.tags.map((tag) => (
                    <span key={tag} className="rounded-full border border-hairline bg-white px-3 py-1 text-[12px] font-semibold text-ink-charcoal">
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            </motion.div>
          </div>
        </div>
      </section>
    </div>
  );
};

export default CausalInference;
