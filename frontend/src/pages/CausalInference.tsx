import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import {
  ArrowRight,
  Database,
  FileText,
  GitBranch,
  Maximize2,
  Search,
  SlidersHorizontal,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';
import { GraphVisualizer } from '../components';
import type { GraphData, GraphHighlightPath } from '../types/graph';
import { useAuth } from '../contexts/AuthContext';

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
  if (value >= 1000) return `${(value / 1000).toFixed(1)}k`;
  return value.toLocaleString();
};

const GRAPH_OVERVIEW_NODE_LIMIT = 1500;
const GRAPH_OVERVIEW_EDGE_LIMIT = 3000;
const GRAPH_FULL_NODE_LIMIT = 25000;
const GRAPH_FULL_EDGE_LIMIT = 30000;

const leftStats = [
  ['Environmental', 'Scope 1-3'],
  ['Social', 'Suppliers'],
  ['Governance', 'Controls'],
];

const graphRelations = [
  ['Company', 'reports', 'Scope 3 category 1'],
  ['Category 1', 'uses evidence from', 'Purchased goods'],
  ['Target', 'reduces', 'Operational emissions'],
];

interface GraphWorkbenchPreviewProps {
  graphStatus: GraphLoadStatus;
  statusLabel: string;
  nodeCountLabel: string;
  edgeCountLabel: string;
  sourceLabel: string;
  onOpenAgent: () => void;
  onOpenGraph: () => void;
}

const GraphWorkbenchPreview: React.FC<GraphWorkbenchPreviewProps> = ({
  graphStatus,
  statusLabel,
  nodeCountLabel,
  edgeCountLabel,
  sourceLabel,
  onOpenAgent,
  onOpenGraph,
}) => {
  const statusTone = graphStatus === 'ready'
    ? 'bg-emerald-300/[0.14] text-emerald-100'
    : graphStatus === 'loading'
      ? 'bg-white/[0.08] text-white/70'
      : 'bg-amber-300/[0.13] text-amber-100';

  return (
    <div className="moon-workbench-grid">
      <aside className="moon-workbench-sidebar">
        <div className="moon-pill w-fit px-3 py-1 text-[12px] font-semibold">Graph</div>
        <div className="mt-5">
          <h1 className="font-display text-[36px] font-semibold leading-[0.98] text-white sm:text-[44px] xl:text-[50px]">
            Evidence graph explorer
          </h1>
          <p className="mt-4 text-[14px] leading-6 moon-copy">
            Turn report excerpts into entities, relationships, and source-backed paths before the agent writes.
          </p>
        </div>

        <div className="mt-5 flex flex-wrap gap-2">
          {leftStats.map(([label, value]) => (
            <span key={label} className="rounded-full border border-white/[0.12] bg-white/[0.045] px-3 py-1.5 text-[12px] font-semibold text-white/74">
              {label}
              <span className="ml-2 text-white/36">{value}</span>
            </span>
          ))}
        </div>

        <div className="mt-5 rounded-[18px] border border-white/[0.10] bg-white/[0.045] p-4">
          <div className="flex items-center gap-3 rounded-full border border-white/[0.12] bg-black/25 px-3 py-2 text-white/46">
            <Search className="h-4 w-4" />
            <span className="truncate text-[13px]">Search claims, metrics, companies...</span>
          </div>
          <div className="mt-4 grid grid-cols-2 gap-2">
            <button type="button" onClick={onOpenGraph} className="moon-btn-primary !px-4 !py-2.5 text-[13px]">
              Open graph
              <ArrowRight className="h-4 w-4" />
            </button>
            <button type="button" onClick={onOpenAgent} className="moon-btn-secondary !px-4 !py-2.5 text-[13px]">
              Ask agent
            </button>
          </div>
        </div>

        <div className="moon-sidebar-stats mt-5">
          {[
            [nodeCountLabel, 'Nodes'],
            [edgeCountLabel, 'Edges'],
            [sourceLabel, 'Reports'],
            ['All', 'Scope'],
          ].map(([value, label]) => (
            <div key={label}>
              <strong>{value}</strong>
              <span>{label}</span>
            </div>
          ))}
        </div>
      </aside>

      <main className="moon-graph-canvas">
        <div className="moon-graph-toolbar">
          <div>
            <div className="font-mono text-[10px] font-semibold uppercase tracking-[0.18em] text-white/38">Evidence map</div>
            <div className="mt-0.5 text-[16px] font-semibold text-white">CausalGraph live workspace</div>
          </div>
          <div className="flex items-center gap-2">
            <span className={`rounded-full px-3 py-1 text-[11px] font-semibold ${statusTone}`}>{statusLabel}</span>
            <button type="button" className="moon-toolbar-button" aria-label="Graph layout">
              <SlidersHorizontal className="h-4 w-4" />
            </button>
            <button type="button" className="moon-toolbar-button" aria-label="Fit graph">
              <Maximize2 className="h-4 w-4" />
            </button>
          </div>
        </div>

        <div className="moon-graph-stage">
          <div className="moon-graph-toolrail">
            <button type="button" aria-label="Zoom in"><ZoomIn className="h-4 w-4" /></button>
            <button type="button" aria-label="Zoom out"><ZoomOut className="h-4 w-4" /></button>
            <button type="button" aria-label="Filter graph"><GitBranch className="h-4 w-4" /></button>
          </div>

          <svg className="moon-graph-svg" viewBox="0 0 1120 680" preserveAspectRatio="xMidYMid slice" role="img" aria-label="Evidence graph preview">
            <defs>
              <filter id="graphGlow" x="-40%" y="-40%" width="180%" height="180%">
                <feGaussianBlur stdDeviation="5" result="blur" />
                <feMerge>
                  <feMergeNode in="blur" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
              <radialGradient id="nodeFill" cx="50%" cy="45%" r="62%">
                <stop offset="0%" stopColor="rgba(255,255,255,0.16)" />
                <stop offset="100%" stopColor="rgba(10,10,10,0.94)" />
              </radialGradient>
            </defs>

            <g className="moon-graph-backdrop">
              {[
                [84, 95, 9], [138, 210, 13], [176, 388, 11], [232, 104, 10], [276, 264, 15],
                [312, 506, 12], [382, 170, 11], [430, 418, 14], [506, 76, 9], [548, 548, 15],
                [632, 214, 12], [694, 92, 16], [742, 344, 11], [812, 524, 13], [868, 178, 11],
                [926, 304, 17], [984, 106, 10], [1028, 470, 12], [1082, 252, 9],
              ].map(([x, y, r], index) => (
                <circle key={`bg-${index}`} cx={x} cy={y} r={r} />
              ))}
              {[
                'M84 95 C162 156 196 172 276 264',
                'M138 210 C236 170 312 156 382 170',
                'M176 388 C250 342 348 348 430 418',
                'M276 264 C374 224 482 246 560 316',
                'M382 170 C480 118 598 128 694 92',
                'M430 418 C526 360 640 360 742 344',
                'M548 548 C630 506 718 500 812 524',
                'M632 214 C724 166 816 158 868 178',
                'M742 344 C830 328 894 306 926 304',
                'M926 304 C994 260 1036 254 1082 252',
                'M812 524 C908 490 970 480 1028 470',
              ].map((d) => (
                <path key={d} className="moon-graph-link hairline" d={d} />
              ))}
            </g>

            <path className="moon-graph-link muted" d="M154 342 C246 238 362 220 478 292" />
            <path className="moon-graph-link muted" d="M154 342 C266 424 398 462 560 392" />
            <path className="moon-graph-link muted" d="M478 292 C594 226 720 212 858 252" />
            <path className="moon-graph-link muted" d="M560 392 C658 348 762 352 878 430" />
            <path className="moon-graph-link muted" d="M560 392 C482 478 408 520 320 556" />
            <path className="moon-graph-link muted" d="M560 392 C608 496 684 552 784 574" />
            <path className="moon-graph-link muted dash" d="M478 292 C514 374 530 418 560 392" />
            <path className="moon-graph-link muted dash" d="M858 252 C890 312 900 366 878 430" />
            <path className="moon-graph-link active" d="M154 342 C246 238 362 220 478 292 C594 226 720 212 858 252" />

            {[
              [154, 342, 27, 'Company', 'Apple'],
              [478, 292, 42, 'Metric', 'Scope 3'],
              [858, 252, 31, 'Evidence', 'chunk 205'],
              [560, 392, 33, 'Topic', 'Category 1'],
              [878, 430, 27, 'Policy', 'Supplier'],
              [320, 556, 27, 'Risk', 'Transport'],
              [784, 574, 29, 'Claim', 'Target'],
              [688, 180, 24, 'Audit', 'Science'],
              [1012, 336, 25, 'Control', 'Governance'],
              [624, 82, 22, 'Source', 'Report'],
            ].map(([x, y, r, type, label]) => (
              <g key={`${type}-${label}`} className={`moon-graph-node-group ${label === 'Scope 3' ? 'is-selected' : ''}`} transform={`translate(${x} ${y})`}>
                <circle r={Number(r) + 11} />
                <circle r={Number(r)} />
                <text y="-4" textAnchor="middle">{type}</text>
                <text y="12" textAnchor="middle" className="node-label">{label}</text>
              </g>
            ))}
          </svg>

          <div className="moon-graph-minimap">
            <div className="moon-minimap-path" />
            <span />
            <span />
            <span />
          </div>

          <div className="moon-graph-legend">
            <span><i className="bg-emerald-300" /> Selected path</span>
            <span><i className="bg-white/45" /> Related nodes</span>
          </div>
        </div>
      </main>

      <aside className="moon-graph-inspector">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="font-mono text-[10px] font-semibold uppercase tracking-[0.18em] text-white/38">Entity</div>
            <h2 className="mt-2 text-[24px] font-semibold leading-tight text-white">GHG Emissions (Scope 3)</h2>
          </div>
          <div className="flex h-10 w-10 items-center justify-center rounded-full border border-emerald-300/24 bg-emerald-300/10 text-emerald-100">
            <Database className="h-4 w-4" />
          </div>
        </div>

        <div className="mt-5 flex flex-wrap gap-2">
          {['Environmental', 'Metric', 'High confidence'].map((label) => (
            <span key={label} className="rounded-full border border-white/[0.12] bg-white/[0.05] px-3 py-1 text-[11px] font-semibold text-white/70">
              {label}
            </span>
          ))}
        </div>

        <div className="mt-7">
          <div className="mb-3 font-mono text-[10px] font-semibold uppercase tracking-[0.18em] text-white/36">Relationships</div>
          <div className="space-y-2">
            {graphRelations.map(([source, relation, target]) => (
              <div key={`${source}-${target}`} className="moon-inspector-row">
                <span>{source}</span>
                <small>{relation}</small>
                <strong>{target}</strong>
              </div>
            ))}
          </div>
        </div>

        <div className="mt-7 rounded-[20px] border border-white/[0.10] bg-black/24 p-4">
          <div className="flex items-center gap-2 text-[12px] font-semibold text-white">
            <FileText className="h-4 w-4" />
            Evidence chunk
          </div>
          <p className="mt-3 text-[13px] leading-6 text-white/58">
            Purchased goods and services, upstream transportation, and product use appear as connected source-backed nodes.
          </p>
          <div className="mt-4 rounded-[14px] border border-white/[0.08] bg-white/[0.04] px-3 py-2 font-mono text-[11px] text-white/42">
            report_2024 - p.42 - lines 3-18
          </div>
        </div>

        <button type="button" onClick={onOpenGraph} className="moon-btn-secondary mt-6 w-full">
          View full evidence
          <ArrowRight className="h-4 w-4" />
        </button>
      </aside>
    </div>
  );
};

const CausalInference: React.FC = () => {
  const [knowledgeGraph, setKnowledgeGraph] = useState<GraphData | null>(null);
  const [graphStatus, setGraphStatus] = useState<GraphLoadStatus>('loading');
  const [graphScope, setGraphScope] = useState<'overview' | 'full'>('overview');
  const [showGraphExplorer, setShowGraphExplorer] = useState(false);
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
  }, [fetchKnowledgeGraph]);

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

  const openGraphExplorer = useCallback(() => {
    setShowGraphExplorer(true);
    window.setTimeout(() => {
      document.getElementById('live-graph')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 40);
  }, []);

  const previewGraph = useMemo(() => buildPreviewGraph(knowledgeGraph), [knowledgeGraph]);
  const fullFocusNodeId = useMemo(() => getGraphFocusNodeId(knowledgeGraph), [knowledgeGraph]);
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

  const nodeCountLabel = graphNodes > 0 ? compactNumber(graphNodes) : '1.5k';
  const edgeCountLabel = graphEdges > 0 ? compactNumber(graphEdges) : '3.0k';
  const sourceLabel = graphDocumentCount > 0
    ? compactNumber(graphDocumentCount)
    : graphSource === 'backend' ? '24' : graphSource;

  return (
    <div className="moon-page overflow-x-hidden">
      <section className="moon-section moon-workbench-shell border-b moon-hairline">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.42 }}
          className="relative z-10 mx-auto w-full max-w-[1920px] px-4 py-4 sm:px-5 lg:px-6 xl:px-8 2xl:px-10"
        >
          <GraphWorkbenchPreview
            graphStatus={graphStatus}
            statusLabel={graphStatusLabel}
            nodeCountLabel={nodeCountLabel}
            edgeCountLabel={edgeCountLabel}
            sourceLabel={sourceLabel}
            onOpenAgent={() => navigate('/agent')}
            onOpenGraph={openGraphExplorer}
          />
        </motion.div>
      </section>

      {showGraphExplorer && (
        <motion.section
          id="live-graph"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.32 }}
          className="mx-auto max-w-page-2xl px-4 py-12 sm:px-6 lg:px-8 xl:px-12 2xl:px-16"
        >
          <div className="mb-5 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
            <div>
              <h2 className="font-display text-[36px] font-semibold leading-tight text-white md:text-[48px]">
                Live backend graph
              </h2>
              <p className="mt-3 max-w-2xl text-[15px] leading-7 moon-copy">
                The full explorer stays below the product workbench, so the main route opens fast and still exposes the real graph when needed.
              </p>
            </div>
            {knowledgeGraph && knowledgeGraph.nodes.length > 0 && graphScope !== 'full' && (
              <button
                onClick={loadCompleteGraph}
                disabled={fullGraphLoading}
                className="moon-btn-secondary shrink-0 disabled:cursor-wait disabled:opacity-60"
              >
                {fullGraphLoading ? 'Loading full map' : 'Load full map'}
              </button>
            )}
          </div>

          <div className="moon-panel rounded-[28px] p-4 xl:p-5">
            {previewGraph.nodes.length > 0 ? (
              <div className="overflow-hidden rounded-2xl border border-white/10 bg-white">
                <GraphVisualizer
                  graph={knowledgeGraph || previewGraph}
                  height={640}
                  focusNodeId={fullFocusNodeId}
                  highlightPath={fullHighlightPath}
                />
              </div>
            ) : (
              <div className="rounded-2xl border border-white/10 bg-white/[0.035] px-6 py-20 text-center">
                <div className="font-mono text-[11px] font-semibold uppercase tracking-[0.16em] moon-muted">{graphStatusLabel}</div>
                <p className="mt-2 text-sm moon-copy">
                  Upload or sync documents so the backend can return extracted nodes and relationships.
                </p>
              </div>
            )}
          </div>
        </motion.section>
      )}
    </div>
  );
};

export default CausalInference;
