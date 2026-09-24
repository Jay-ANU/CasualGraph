import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Loader2 } from 'lucide-react';
import { GraphVisualizer } from '../components';
import type { GraphData } from '../types/graph';
import { useAuth } from '../contexts/AuthContext';
import useDocumentTitle from '../utils/useDocumentTitle';

type GraphLoadStatus = 'loading' | 'ready' | 'empty' | 'error';

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

const GRAPH_OVERVIEW_NODE_LIMIT = 1500;
const GRAPH_OVERVIEW_EDGE_LIMIT = 3000;
const GRAPH_FULL_NODE_LIMIT = 25000;
const GRAPH_FULL_EDGE_LIMIT = 30000;

const CausalInference: React.FC = () => {
  const [knowledgeGraph, setKnowledgeGraph] = useState<GraphData | null>(null);
  const [graphStatus, setGraphStatus] = useState<GraphLoadStatus>('loading');
  const [graphScope, setGraphScope] = useState<'overview' | 'full'>('overview');
  const [fullGraphLoading, setFullGraphLoading] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const { token } = useAuth();
  const apiBase = useMemo(() => getApiBase(), []);
  useDocumentTitle('Knowledge graph');

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
      } catch {
        if (cancelled) return;
        setKnowledgeGraph(emptyGraph);
        setGraphStatus('error');
      }
    };
    loadGraph();
    return () => {
      cancelled = true;
    };
  }, [fetchKnowledgeGraph, reloadKey]);

  const loadCompleteGraph = async () => {
    if (fullGraphLoading || graphScope === 'full') return;
    setFullGraphLoading(true);
    try {
      const graph = await fetchKnowledgeGraph(GRAPH_FULL_NODE_LIMIT, GRAPH_FULL_EDGE_LIMIT);
      setKnowledgeGraph(graph);
      setGraphScope('full');
      setGraphStatus(graph.nodes.length > 0 ? 'ready' : 'empty');
    } catch {
      setGraphStatus('error');
    } finally {
      setFullGraphLoading(false);
    }
  };

  const nodeCount = knowledgeGraph?.nodes.length || 0;
  const edgeCount = knowledgeGraph?.edges.length || 0;
  const documentCount = Number((knowledgeGraph?.metadata as { document_count?: number } | undefined)?.document_count || 0);
  const mayBeTruncated =
    graphScope === 'overview' && (nodeCount >= GRAPH_OVERVIEW_NODE_LIMIT || edgeCount >= GRAPH_OVERVIEW_EDGE_LIMIT);
  const statValue = (value: number) => (graphStatus === 'ready' ? value.toLocaleString() : '—');

  return (
    <div className="mx-auto max-w-content px-5 pb-24 pt-14 sm:px-8 sm:pt-20">
      <header className="flex flex-col gap-8 lg:flex-row lg:items-end lg:justify-between">
        <div className="max-w-2xl">
          <h1 className="display text-[40px] leading-[1.06] sm:text-display-lg">Knowledge graph</h1>
          <p className="mt-4 text-[17px] leading-relaxed text-ink-3">
            The entities and relationships extracted from reports in the shared library: targets, metrics, policies and
            who oversees them. Choose a domain to see its entities, then select one to read the evidence behind it.
          </p>
        </div>
        <dl className="flex gap-10 lg:pb-1">
          {[
            ['Entities', statValue(nodeCount)],
            ['Relationships', statValue(edgeCount)],
            ...(documentCount > 0 && graphStatus === 'ready' ? [['Reports', documentCount.toLocaleString()]] : []),
          ].map(([label, value]) => (
            <div key={label}>
              <dt className="text-xs text-ink-4">{label}</dt>
              <dd className="mt-1 text-2xl font-medium tabular-nums text-ink">{value}</dd>
            </div>
          ))}
        </dl>
      </header>

      <section className="mt-10" aria-live="polite">
        {graphStatus === 'loading' && (
          <div className="flex h-[480px] items-center justify-center gap-2 rounded-xl border border-line bg-white text-sm text-ink-3">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading the graph…
          </div>
        )}

        {graphStatus === 'error' && (
          <div className="rounded-xl border border-line bg-white px-6 py-20 text-center">
            <p className="font-medium text-ink">The graph couldn’t be loaded</p>
            <p className="mx-auto mt-1 max-w-md text-sm text-ink-3">
              The graph service didn’t respond. It may be starting up — try again in a moment.
            </p>
            <button type="button" onClick={() => setReloadKey((key) => key + 1)} className="btn btn-secondary btn-sm mt-5">
              Try again
            </button>
          </div>
        )}

        {graphStatus === 'empty' && (
          <div className="rounded-xl border border-dashed border-line-strong px-6 py-20 text-center">
            <p className="font-medium text-ink">No graph yet</p>
            <p className="mx-auto mt-1 max-w-md text-sm text-ink-3">
              Entities appear here once reports have been uploaded and processed in the research desk.
            </p>
            <Link to="/agent" className="btn btn-secondary btn-sm mt-5">
              Open the research desk
            </Link>
          </div>
        )}

        {graphStatus === 'ready' && knowledgeGraph && (
          <>
            <GraphVisualizer graph={knowledgeGraph} height={620} />
            {mayBeTruncated && (
              <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-sm text-ink-3">
                <span>
                  Showing {nodeCount.toLocaleString()} entities. The full graph may include more and can take a while to draw.
                </span>
                <button
                  type="button"
                  onClick={loadCompleteGraph}
                  disabled={fullGraphLoading}
                  className="btn btn-secondary btn-sm"
                >
                  {fullGraphLoading && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                  {fullGraphLoading ? 'Loading the full graph…' : 'Load the full graph'}
                </button>
              </div>
            )}
          </>
        )}
      </section>

      <section className="mt-20 grid gap-10 border-t border-line pt-12 md:grid-cols-2">
        <div>
          <h2 className="text-lg font-medium text-ink">How the graph is built</h2>
          <p className="mt-2 max-w-md leading-relaxed text-ink-3">
            When a report is uploaded, each passage is read for entities — companies, targets, metrics, policies — and
            the relationships between them. Each relationship keeps the evidence it was extracted from, so it can be
            checked against the report.
          </p>
        </div>
        <div>
          <h2 className="text-lg font-medium text-ink">Ask questions about it</h2>
          <p className="mt-2 max-w-md leading-relaxed text-ink-3">
            In Deep mode the research desk can draw on this graph alongside the report passages when it plans an
            answer, and it shows each step it took.
          </p>
          <Link to="/agent" className="mt-4 inline-flex items-center gap-1.5 text-sm font-medium text-ink transition-[gap] hover:gap-2.5">
            Open the research desk <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      </section>
    </div>
  );
};

export default CausalInference;
