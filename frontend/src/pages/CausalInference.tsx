import React, { useCallback, useEffect, useMemo, useState } from 'react';
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
import { useAuth } from '../contexts/AuthContext';

const emptyGraph: GraphData = {
  nodes: [],
  edges: [],
  metadata: {
    node_count: 0,
    edge_count: 0,
    is_directed: true,
    is_acyclic: false,
  },
};

const getApiBase = () => {
  const host = window.location.hostname || '127.0.0.1';
  const localApiHost = host === 'localhost' || host === '127.0.0.1';
  return process.env.REACT_APP_ESG_API_BASE || (localApiHost ? `http://${host}:8000` : '');
};

const normalizeGraphPayload = (payload: any): GraphData => {
  const rawNodes = Array.isArray(payload?.nodes) ? payload.nodes : [];
  const nodes: GraphData['nodes'] = rawNodes
    .map((node: any) => ({
      id: String(node?.id || '').trim(),
      label: String(node?.label || node?.name || node?.id || '').trim(),
      domain: String(node?.domain || node?.esg_domain || 'general'),
      type: String(node?.type || 'Entity'),
      confidence: Number(node?.confidence ?? 0.75),
      description: String(node?.description || ''),
      company: String(node?.company || ''),
      year: String(node?.year || ''),
      normalizedName: String(node?.normalizedName || node?.normalized_name || node?.id || ''),
      metadata: node?.metadata || {},
    }))
    .filter((node: GraphData['nodes'][number]) => node.id && node.label);

  const nodeIds = new Set(nodes.map((node) => node.id));
  const rawEdges = Array.isArray(payload?.edges) ? payload.edges : [];
  const edges: GraphData['edges'] = rawEdges
    .map((edge: any) => ({
      source: String(edge?.source || '').trim(),
      target: String(edge?.target || '').trim(),
      relationship_type: String(edge?.relationship_type || edge?.relation || edge?.type || 'RELATED_TO'),
      confidence: Number(edge?.confidence ?? 0.75),
      evidence: String(edge?.evidence || ''),
      domain: String(edge?.domain || 'general'),
      relationship_action: String(edge?.relationship_action || ''),
      relationship_nature: String(edge?.relationship_nature || ''),
      documentId: String(edge?.documentId || edge?.document_id || ''),
      chunkId: String(edge?.chunkId || edge?.chunk_id || ''),
      metadata: edge?.metadata || {},
    }))
    .filter((edge: GraphData['edges'][number]) => nodeIds.has(edge.source) && nodeIds.has(edge.target));

  return {
    nodes,
    edges,
    metadata: {
      ...(payload?.metadata || {}),
      node_count: nodes.length,
      edge_count: edges.length,
      is_directed: payload?.metadata?.is_directed ?? true,
      is_acyclic: payload?.metadata?.is_acyclic ?? false,
    },
  };
};

const getDegreeMap = (graph: GraphData) => {
  const degreeMap = new Map<string, number>();
  graph.nodes.forEach((node) => degreeMap.set(node.id, 0));
  graph.edges.forEach((edge) => {
    degreeMap.set(edge.source, (degreeMap.get(edge.source) || 0) + 1);
    degreeMap.set(edge.target, (degreeMap.get(edge.target) || 0) + 1);
  });
  return degreeMap;
};

const getGraphFocusNodeId = (graph: GraphData | null) => {
  if (!graph || graph.nodes.length === 0) return null;
  const degreeMap = getDegreeMap(graph);
  return [...graph.nodes].sort((a, b) => (degreeMap.get(b.id) || 0) - (degreeMap.get(a.id) || 0))[0]?.id || null;
};

const buildPreviewGraph = (graph: GraphData | null, maxNodes = 220, maxEdges = 340): GraphData => {
  if (!graph || graph.nodes.length === 0) return emptyGraph;
  const degreeMap = getDegreeMap(graph);
  const nodes = [...graph.nodes]
    .sort((a, b) => (degreeMap.get(b.id) || 0) - (degreeMap.get(a.id) || 0))
    .slice(0, maxNodes);
  const nodeIds = new Set(nodes.map((node) => node.id));
  const edges = graph.edges
    .filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target))
    .slice(0, maxEdges);
  return {
    nodes,
    edges,
    metadata: {
      node_count: nodes.length,
      edge_count: edges.length,
      is_directed: true,
      is_acyclic: false,
    },
  };
};

const buildHighlightPath = (graph: GraphData | null): GraphHighlightPath | null => {
  if (!graph || graph.edges.length === 0) return null;
  const firstEdge = graph.edges[0];
  const chain = [firstEdge.source, firstEdge.target];
  const nextEdge = graph.edges.find((edge) => edge.source === firstEdge.target && edge.target !== firstEdge.source);
  if (nextEdge) chain.push(nextEdge.target);
  return {
    nodes: chain,
    edges: chain.slice(0, -1).map((source, index) => [source, chain[index + 1]]),
  };
};

const compactNumber = (value: number) => {
  if (value >= 10000) return `${(value / 1000).toFixed(1)}k`;
  return value.toLocaleString();
};

const GRAPH_OVERVIEW_NODE_LIMIT = 1500;
const GRAPH_OVERVIEW_EDGE_LIMIT = 3000;
const GRAPH_FULL_NODE_LIMIT = 25000;
const GRAPH_FULL_EDGE_LIMIT = 30000;

const CausalInference: React.FC = () => {
  const [selectedWorkflow, setSelectedWorkflow] = useState('disclosures');
  const [knowledgeGraph, setKnowledgeGraph] = useState<GraphData | null>(null);
  const [graphStatus, setGraphStatus] = useState<'loading' | 'ready' | 'empty' | 'error'>('loading');
  const [graphScope, setGraphScope] = useState<'overview' | 'full'>('overview');
  const [fullGraphLoading, setFullGraphLoading] = useState(false);
  const navigate = useNavigate();
  const { token } = useAuth();
  const apiBase = useMemo(() => getApiBase(), []);

  const fetchKnowledgeGraph = useCallback(async (nodeLimit: number, edgeLimit: number) => {
    const response = await fetch(`${apiBase}/public/knowledge-graph?limit=${nodeLimit}&edge_limit=${edgeLimit}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      throw new Error(payload?.message || payload?.error || 'Unable to load knowledge graph');
    }
    return normalizeGraphPayload(payload);
  }, [apiBase, token]);

  useEffect(() => {
    let cancelled = false;
    const loadGraph = async () => {
      setGraphStatus('loading');
      try {
        const graph = await fetchKnowledgeGraph(GRAPH_OVERVIEW_NODE_LIMIT, GRAPH_OVERVIEW_EDGE_LIMIT);
        if (cancelled) return;
        setKnowledgeGraph(graph);
        setGraphScope('overview');
        setGraphStatus(graph.nodes.length > 0 ? 'ready' : 'empty');
      } catch (error) {
        if (cancelled) return;
        console.error('Failed to load real knowledge graph:', error);
        setKnowledgeGraph(emptyGraph);
        setGraphStatus('error');
      }
    };
    loadGraph();
    return () => {
      cancelled = true;
    };
  }, [fetchKnowledgeGraph]);

  const loadCompleteGraph = async () => {
    if (fullGraphLoading || graphScope === 'full') return;
    setFullGraphLoading(true);
    try {
      const graph = await fetchKnowledgeGraph(GRAPH_FULL_NODE_LIMIT, GRAPH_FULL_EDGE_LIMIT);
      setKnowledgeGraph(graph);
      setGraphScope('full');
      setGraphStatus(graph.nodes.length > 0 ? 'ready' : 'empty');
    } catch (error) {
      console.error('Failed to load complete knowledge graph:', error);
    } finally {
      setFullGraphLoading(false);
    }
  };

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
  const previewGraph = useMemo(() => buildPreviewGraph(knowledgeGraph), [knowledgeGraph]);
  const previewFocusNodeId = useMemo(() => getGraphFocusNodeId(previewGraph), [previewGraph]);
  const fullFocusNodeId = useMemo(() => getGraphFocusNodeId(knowledgeGraph), [knowledgeGraph]);
  const previewHighlightPath = useMemo(() => buildHighlightPath(previewGraph), [previewGraph]);
  const fullHighlightPath = useMemo(() => buildHighlightPath(knowledgeGraph), [knowledgeGraph]);
  const graphNodes = knowledgeGraph?.nodes.length || 0;
  const graphEdges = knowledgeGraph?.edges.length || 0;
  const graphDocumentCount = Number((knowledgeGraph?.metadata as any)?.document_count || 0);
  const graphSource = String((knowledgeGraph?.metadata as any)?.source || 'backend');
  const graphStatusLabel = graphStatus === 'ready'
    ? 'Real graph'
    : graphStatus === 'loading'
      ? 'Loading'
      : graphStatus === 'empty'
        ? 'No data'
        : 'Unavailable';

  return (
    <div className="min-h-screen overflow-x-hidden bg-canvas text-ink">
      <section className="border-b border-hairline-soft">
        <div className="mx-auto grid max-w-page gap-10 px-4 py-16 sm:px-6 lg:max-w-page-wide lg:grid-cols-[0.95fr_1.05fr] lg:px-8 lg:py-20 xl:max-w-page-xl xl:px-12 2xl:max-w-page-2xl 2xl:px-16">
          <motion.div
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.42 }}
            className="min-w-0 flex flex-col justify-center"
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
            className="cg-tool-panel min-w-0 p-4"
          >
            <div className="rounded-xl bg-surface-soft p-5">
              <div className="flex items-center justify-between gap-4 border-b border-hairline pb-4">
                <div>
                  <div className="cg-eyebrow text-ink-stone">Knowledge map</div>
                  <div className="mt-1 text-[18px] font-semibold text-ink">Report evidence graph</div>
                </div>
                <span className={`rounded-full px-3 py-1 text-[12px] font-semibold ${
                  graphStatus === 'ready' ? 'bg-success-bg text-success' : 'bg-surface text-ink-steel'
                }`}>
                  {graphStatusLabel}
                </span>
              </div>

              <div className="mt-5">
                {previewGraph.nodes.length > 0 ? (
                  <GraphVisualizer
                    graph={previewGraph}
                    compact
                    height={340}
                    focusNodeId={previewFocusNodeId}
                    highlightPath={previewHighlightPath}
                  />
                ) : (
                  <div className="rounded-xl border border-hairline bg-white px-5 py-16 text-center">
                    <div className="cg-eyebrow text-ink-stone">{graphStatusLabel}</div>
                    <p className="mt-2 text-sm text-ink-steel">No real graph nodes are available from the backend yet.</p>
                  </div>
                )}
              </div>

              <div className="mt-4 grid gap-3 sm:grid-cols-3">
                {[
                  [compactNumber(graphNodes), 'real nodes'],
                  [compactNumber(graphEdges), 'real edges'],
                  [graphDocumentCount ? compactNumber(graphDocumentCount) : graphSource, 'source'],
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
        <div className="mb-8 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl">
            <p className="cg-eyebrow">Clustered knowledge graph</p>
            <h2 className="mt-3 text-heading-lg xl:text-[56px]" style={{ letterSpacing: 0, lineHeight: 1.1 }}>
              E, S, G, and AI stay readable at scale.
            </h2>
            <p className="mt-4 text-body-md text-ink-steel xl:text-[18px]">
              The clusters are only the review lens. Every visible dot is a real extracted entity from the backend graph, grouped by ESG/AI semantics.
            </p>
          </div>
          {knowledgeGraph && knowledgeGraph.nodes.length > 0 && graphScope !== 'full' && (
            <button
              onClick={loadCompleteGraph}
              disabled={fullGraphLoading}
              className="cg-btn-secondary shrink-0 justify-center disabled:cursor-wait disabled:opacity-60"
            >
              {fullGraphLoading ? 'Loading complete graph' : 'Load complete graph'}
            </button>
          )}
          <div className="hidden h-px flex-1 bg-hairline lg:block" />
        </div>

        <div className="cg-tool-panel min-w-0 p-4 xl:p-5">
          {knowledgeGraph && knowledgeGraph.nodes.length > 0 ? (
            <GraphVisualizer
              graph={knowledgeGraph}
              height={640}
              focusNodeId={fullFocusNodeId}
              highlightPath={fullHighlightPath}
            />
          ) : (
            <div className="rounded-xl border border-hairline bg-white px-6 py-20 text-center">
              <div className="cg-eyebrow text-ink-stone">{graphStatusLabel}</div>
              <p className="mt-2 text-sm text-ink-steel">
                Upload or sync documents so the backend can return real extracted nodes and relationships.
              </p>
            </div>
          )}
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
