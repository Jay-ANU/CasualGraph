import React, { useEffect, useId, useMemo, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import type { GraphData, GraphEdge, GraphHighlightPath, GraphNode } from '../types/graph';

interface KnowledgeGraphViewProps {
  graph: GraphData;
  width?: number;
  height?: number;
  compact?: boolean;
  focusNodeId?: string | null;
  selectedNodeId?: string | null;
  selectedEdgeId?: string | null;
  highlightPath?: GraphHighlightPath | null;
  onNodeSelect?: (node: GraphNode) => void;
  onEdgeSelect?: (edge: GraphEdge) => void;
}

type DomainKey = 'environmental' | 'social' | 'governance' | 'ai';
type ClusterTab = 'overview' | DomainKey;

type ClusterCategory = {
  label: string;
  shortLabel?: string;
  type: string;
  keywords: string[];
};

type ClusterDefinition = {
  key: DomainKey;
  tabLabel: string;
  label: string;
  short: string;
  relationship: string;
  description: string;
  color: string;
  textColor: string;
  softFill: string;
  ringFill: string;
  categories: ClusterCategory[];
};

type ClusterLayout = {
  definition: ClusterDefinition;
  x: number;
  y: number;
  radius: number;
  nodeCount: number;
  edgeCount: number;
  confidence: number;
  representativeEdge?: GraphEdge;
  categories: Array<ClusterCategory & {
    id: string;
    x: number;
    y: number;
    confidence: number;
    nodeCount: number;
    backingNode?: GraphNode;
  }>;
};

type CloudNode = {
  node: GraphNode;
  x: number;
  y: number;
  radius: number;
  categoryIndex: number;
};

const CLUSTERS: ClusterDefinition[] = [
  {
    key: 'environmental',
    tabLabel: 'Environmental',
    label: 'Environmental',
    short: 'E',
    relationship: 'has_impact_on',
    description: 'Climate, resource, and environmental operating signals extracted from disclosures.',
    color: '#1ba673',
    textColor: '#0f6f4d',
    softFill: '#f0fff4',
    ringFill: 'rgba(27, 166, 115, 0.10)',
    categories: [
      { label: 'Climate Strategy', type: 'Strategy', keywords: ['climate', 'carbon neutral', 'net zero', 'transition'] },
      { label: 'Emissions', type: 'Metric', keywords: ['emission', 'scope 1', 'scope 2', 'scope 3', 'ghg', 'carbon'] },
      { label: 'Renewable Energy', type: 'Initiative', keywords: ['renewable', 'clean energy', 'electricity', 'solar', 'wind'] },
      { label: 'Water', type: 'Resource', keywords: ['water', 'wastewater', 'stewardship'] },
      { label: 'Circularity', type: 'Program', keywords: ['circular', 'recycling', 'waste', 'packaging', 'reuse'] },
    ],
  },
  {
    key: 'social',
    tabLabel: 'Social',
    label: 'Social',
    short: 'S',
    relationship: 'influences',
    description: 'Workforce, supplier, community, and human-rights signals connected to report evidence.',
    color: '#1456f0',
    textColor: '#17437d',
    softFill: '#f2f7ff',
    ringFill: 'rgba(20, 86, 240, 0.10)',
    categories: [
      { label: 'Workforce Safety', type: 'Control', keywords: ['safety', 'injury', 'workforce', 'employee health'] },
      { label: 'Diversity & Inclusion', type: 'Metric', keywords: ['diversity', 'inclusion', 'dei', 'gender', 'representation'] },
      { label: 'Supplier Responsibility', type: 'Policy', keywords: ['supplier', 'supply chain', 'audit', 'sourcing'] },
      { label: 'Community Impact', type: 'Program', keywords: ['community', 'philanthropy', 'local', 'education'] },
      { label: 'Human Rights', type: 'Risk', keywords: ['human rights', 'labor', 'forced labor', 'modern slavery'] },
    ],
  },
  {
    key: 'governance',
    tabLabel: 'Governance',
    label: 'Governance',
    short: 'G',
    relationship: 'governs',
    description: 'Oversight, controls, ethics, compliance, and risk-management structure.',
    color: '#d99018',
    textColor: '#8a5600',
    softFill: '#fff8ec',
    ringFill: 'rgba(217, 144, 24, 0.13)',
    categories: [
      { label: 'Board Oversight', type: 'Oversight', keywords: ['board', 'committee', 'oversight', 'director'] },
      { label: 'Audit Controls', type: 'Control', keywords: ['audit', 'assurance', 'internal control', 'verification'] },
      { label: 'Ethics', type: 'Policy', keywords: ['ethics', 'code of conduct', 'anti bribery', 'integrity'] },
      { label: 'Risk Management', type: 'Risk', keywords: ['risk', 'scenario', 'enterprise risk', 'transition risk'] },
      { label: 'Compliance', type: 'Compliance', keywords: ['compliance', 'regulation', 'legal', 'reporting standard'] },
    ],
  },
  {
    key: 'ai',
    tabLabel: 'AI',
    label: 'AI Intelligence',
    short: 'AI',
    relationship: 'powers',
    description: 'Document understanding and reasoning capabilities that turn reports into graph context.',
    color: '#8b5cf6',
    textColor: '#6d3fd6',
    softFill: '#f7f4ff',
    ringFill: 'rgba(139, 92, 246, 0.12)',
    categories: [
      { label: 'Document Parsing', type: 'Capability', keywords: ['parse', 'parsing', 'document', 'pdf', 'chunk'] },
      { label: 'Retrieval', type: 'Capability', keywords: ['retrieval', 'rag', 'search', 'vector', 'embedding'] },
      { label: 'Reasoning', type: 'Capability', keywords: ['reasoning', 'causal', 'graph reasoning', 'analysis'] },
      { label: 'Summarization', type: 'Capability', keywords: ['summary', 'summarization', 'synthesis'] },
      { label: 'Prediction', type: 'Capability', keywords: ['prediction', 'forecast', 'scenario', 'impact'] },
    ],
  },
];

const CLUSTER_BY_KEY = new Map(CLUSTERS.map((cluster) => [cluster.key, cluster]));

const normalizeDomainKey = (value: string) => {
  const normalized = String(value || 'general').toLowerCase();
  if (normalized.includes('environment')) return 'environmental';
  if (normalized.includes('social')) return 'social';
  if (normalized.includes('govern')) return 'governance';
  if (normalized.includes('ai')) return 'ai';
  return 'general';
};

const inferNodeDomain = (node: GraphNode): DomainKey | 'general' => {
  const direct = normalizeDomainKey(node.domain);
  const haystack = `${node.domain} ${node.type} ${node.label} ${node.description || ''}`.toLowerCase();

  if (direct !== 'general') return direct as DomainKey;
  if (/\b(ai|llm|model|retrieval|rag|embedding|vector|reasoning|summary|summarization|prediction|parsing)\b/.test(haystack)) return 'ai';
  if (/(climate|emission|scope\s?[123]|ghg|carbon|renewable|energy|water|waste|circular|recycling)/.test(haystack)) return 'environmental';
  if (/(social|workforce|employee|diversity|inclusion|supplier|community|human rights|labor|safety|audit)/.test(haystack)) return 'social';
  if (/(governance|board|audit|ethic|risk|compliance|oversight|committee|policy|control)/.test(haystack)) return 'governance';
  return 'general';
};

const inferEdgeDomain = (edge: GraphEdge): DomainKey | 'general' => {
  const direct = normalizeDomainKey(edge.domain);
  const haystack = `${edge.domain} ${edge.relationship_type} ${edge.evidence || ''}`.toLowerCase();

  if (direct !== 'general') return direct as DomainKey;
  if (/(ai|llm|retrieval|rag|reasoning|summary|prediction|parsing|embedding|vector)/.test(haystack)) return 'ai';
  if (/(climate|emission|carbon|renewable|water|waste|circular|energy)/.test(haystack)) return 'environmental';
  if (/(social|workforce|employee|supplier|community|human rights|labor|safety)/.test(haystack)) return 'social';
  if (/(governance|board|audit|ethic|risk|compliance|oversight|control)/.test(haystack)) return 'governance';
  return 'general';
};

const makeEdgeId = (edge: GraphEdge) => `${edge.source}|${edge.relationship_type}|${edge.target}`;
const makePathEdgeId = (source: string, target: string) => `${source}|${target}`;

const formatTypeLabel = (value: string) => value.replace(/_/g, ' ');

const truncateLabel = (value: string, limit = 28) => {
  if (value.length <= limit) return value;
  return `${value.slice(0, limit - 1)}...`;
};

const splitLabel = (value: string, maxLineLength = 14) => {
  const words = value.split(/\s+/);
  const lines: string[] = [];
  let current = '';

  words.forEach((word) => {
    const next = current ? `${current} ${word}` : word;
    if (next.length > maxLineLength && current) {
      lines.push(current);
      current = word;
    } else {
      current = next;
    }
  });

  if (current) lines.push(current);
  return lines.slice(0, 2);
};

const categoryScore = (node: GraphNode, category: ClusterCategory) => {
  const haystack = `${node.label} ${node.type} ${node.description || ''}`.toLowerCase();
  return category.keywords.reduce((score, keyword) => score + (haystack.includes(keyword) ? 1 : 0), 0);
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

const hashString = (value: string) => {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
};

const getCategoryIndex = (node: GraphNode, definition: ClusterDefinition) => {
  const scored = definition.categories
    .map((category, index) => ({ index, score: categoryScore(node, category) }))
    .sort((a, b) => b.score - a.score)[0];

  if (scored && scored.score > 0) return scored.index;
  const metadataCategory = String(node.metadata?.categoryKey || node.metadata?.category || '').toLowerCase();
  const metadataIndex = definition.categories.findIndex((category) => {
    const normalizedLabel = category.label.toLowerCase().replace(/[^a-z0-9]+/g, '_');
    return metadataCategory.includes(normalizedLabel) || normalizedLabel.includes(metadataCategory);
  });
  if (metadataIndex >= 0) return metadataIndex;
  return hashString(node.id) % definition.categories.length;
};

const buildCloudNodes = (
  graph: GraphData,
  definition: ClusterDefinition,
  centers: Array<{ x: number; y: number }>,
  spread: number,
  dotRadius: number
): CloudNode[] => {
  return graph.nodes
    .filter((node) => inferNodeDomain(node) === definition.key)
    .map((node) => {
      const hash = hashString(node.id);
      const categoryIndex = getCategoryIndex(node, definition);
      const center = centers[categoryIndex] || centers[0];
      const angle = ((hash % 3600) / 3600) * Math.PI * 2;
      const unit = (((hash >>> 8) % 1000) + 1) / 1000;
      const radius = Math.sqrt(unit) * spread;

      return {
        node,
        x: center.x + Math.cos(angle) * radius,
        y: center.y + Math.sin(angle) * radius * 0.72,
        radius: dotRadius + ((hash >>> 18) % 4) * 0.12,
        categoryIndex,
      };
    });
};

const clusterPositions = (canvasWidth: number, canvasHeight: number, compact: boolean) => {
  const yLift = compact ? 0.03 : 0;
  return {
    environmental: { x: canvasWidth * 0.25, y: canvasHeight * (0.31 - yLift) },
    social: { x: canvasWidth * 0.75, y: canvasHeight * (0.31 - yLift) },
    governance: { x: canvasWidth * 0.25, y: canvasHeight * 0.72 },
    ai: { x: canvasWidth * 0.75, y: canvasHeight * 0.72 },
  } satisfies Record<DomainKey, { x: number; y: number }>;
};

const buildClusterLayouts = (
  graph: GraphData,
  canvasWidth: number,
  canvasHeight: number,
  compact: boolean
): ClusterLayout[] => {
  const degreeMap = getDegreeMap(graph);
  const positions = clusterPositions(canvasWidth, canvasHeight, compact);
  const clusterRadius = Math.max(compact ? 54 : 76, Math.min(canvasWidth, canvasHeight) * (compact ? 0.17 : 0.2));
  const categoryRadius = clusterRadius * (compact ? 0.62 : 0.66);

  return CLUSTERS.map((definition) => {
    const sourceNodes = graph.nodes
      .filter((node) => inferNodeDomain(node) === definition.key)
      .sort((a, b) => {
        const degreeDelta = (degreeMap.get(b.id) || 0) - (degreeMap.get(a.id) || 0);
        return degreeDelta || b.confidence - a.confidence;
      });
    const sourceEdges = graph.edges.filter((edge) => inferEdgeDomain(edge) === definition.key);
    const assignedNodes = new Set<string>();

    const categories = definition.categories.map((category, index) => {
      const scoredNodes = sourceNodes
        .map((node) => ({ node, score: categoryScore(node, category) }))
        .filter((item) => getCategoryIndex(item.node, definition) === index || item.score > 0)
        .sort((a, b) => b.score - a.score || b.node.confidence - a.node.confidence);
      const backingNode = scoredNodes.find((item) => !assignedNodes.has(item.node.id))?.node;
      const nodeCount = sourceNodes.filter((node) => getCategoryIndex(node, definition) === index).length;

      if (backingNode) assignedNodes.add(backingNode.id);

      const angle = -Math.PI / 2 + (index / definition.categories.length) * Math.PI * 2;
      return {
        ...category,
        id: backingNode?.id || `${definition.key}-${category.label.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`,
        x: positions[definition.key].x + Math.cos(angle) * categoryRadius,
        y: positions[definition.key].y + Math.sin(angle) * categoryRadius,
        confidence: backingNode?.confidence || 0,
        nodeCount,
        backingNode,
      };
    });

    const backingConfidence = sourceNodes.length
      ? sourceNodes.reduce((sum, node) => sum + node.confidence, 0) / sourceNodes.length
      : 0;

    return {
      definition,
      x: positions[definition.key].x,
      y: positions[definition.key].y,
      radius: clusterRadius,
      nodeCount: sourceNodes.length,
      edgeCount: sourceEdges.length,
      confidence: backingConfidence,
      representativeEdge: sourceEdges.sort((a, b) => b.confidence - a.confidence)[0],
      categories,
    };
  });
};

const summarizeGraph = (graph: GraphData) => ({
  nodes: graph.nodes.length,
  edges: graph.edges.length,
  categories: CLUSTERS.length,
});

const compactNumber = (value: number) => {
  if (value >= 10000) return `${(value / 1000).toFixed(0)}k`;
  return value.toLocaleString();
};

const getInitialClusterTab = (): ClusterTab => {
  if (typeof window === 'undefined') return 'overview';
  const requested = new URLSearchParams(window.location.search).get('graph') || window.location.hash.replace('#', '');
  return CLUSTERS.some((cluster) => cluster.key === requested) ? requested as DomainKey : 'overview';
};

const KnowledgeGraphView: React.FC<KnowledgeGraphViewProps> = ({
  graph,
  width = 800,
  height = 560,
  compact = false,
  focusNodeId,
  selectedNodeId,
  selectedEdgeId,
  highlightPath,
  onNodeSelect,
  onEdgeSelect,
}) => {
  const svgId = useId().replace(/:/g, '');
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(width);
  const initialTab = useMemo(() => compact ? 'overview' : getInitialClusterTab(), [compact]);
  const [activeTab, setActiveTab] = useState<ClusterTab>(initialTab);
  const [inspectedCluster, setInspectedCluster] = useState<DomainKey>(initialTab === 'overview' ? 'ai' : initialTab);
  const [inspectedCategoryId, setInspectedCategoryId] = useState<string | null>(null);
  const [internalSelectedNodeId, setInternalSelectedNodeId] = useState<string | null>(null);
  const [internalSelectedEdgeId, setInternalSelectedEdgeId] = useState<string | null>(null);

  const canvasWidth = Math.max(compact ? 260 : 300, Math.floor(containerWidth || width));
  const canvasHeight = compact ? Math.min(height, 340) : height;
  const stats = summarizeGraph(graph);
  const effectiveSelectedNodeId = selectedNodeId ?? internalSelectedNodeId;
  const effectiveSelectedEdgeId = selectedEdgeId ?? internalSelectedEdgeId;
  const clusterLayouts = useMemo(
    () => buildClusterLayouts(graph, canvasWidth, canvasHeight, compact),
    [graph, canvasWidth, canvasHeight, compact]
  );
  const graphNodeById = useMemo(() => new Map(graph.nodes.map((node) => [node.id, node])), [graph.nodes]);
  const inspectedLayout = clusterLayouts.find((cluster) => cluster.definition.key === inspectedCluster) || clusterLayouts[3];
  const selectedNode = effectiveSelectedNodeId ? graphNodeById.get(effectiveSelectedNodeId) || null : null;
  const selectedEdge = effectiveSelectedEdgeId ? graph.edges.find((edge) => makeEdgeId(edge) === effectiveSelectedEdgeId) || null : null;
  const overviewClouds = useMemo(() => {
    return clusterLayouts.map((cluster) => ({
      key: cluster.definition.key,
      nodes: buildCloudNodes(
        graph,
        cluster.definition,
        cluster.categories.map((category) => ({ x: category.x, y: category.y })),
        Math.max(7, cluster.radius * (compact ? 0.3 : 0.24)),
        compact ? 1.15 : 1.05
      ),
    }));
  }, [clusterLayouts, compact, graph]);
  const selectedEdgeIdSet = useMemo(
    () => new Set((highlightPath?.edges || []).flatMap(([source, target]) => [
      makePathEdgeId(source, target),
      makePathEdgeId(target, source),
    ])),
    [highlightPath]
  );
  const selectedNodeSet = useMemo(() => new Set(highlightPath?.nodes || []), [highlightPath]);

  useEffect(() => {
    const element = containerRef.current;
    if (!element) return;
    const updateWidth = () => setContainerWidth(element.getBoundingClientRect().width || width);

    updateWidth();
    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', updateWidth);
      return () => window.removeEventListener('resize', updateWidth);
    }

    const observer = new ResizeObserver(updateWidth);
    observer.observe(element);
    return () => observer.disconnect();
  }, [width]);

  useEffect(() => {
    if (!effectiveSelectedNodeId) return;
    const node = graph.nodes.find((item) => item.id === effectiveSelectedNodeId);
    const domain = node ? inferNodeDomain(node) : 'general';
    if (domain !== 'general') {
      setInspectedCluster(domain);
      setActiveTab(domain);
    }
  }, [effectiveSelectedNodeId, graph.nodes]);

  if (!graph.nodes.length) {
    return (
      <div className="cg-empty-state py-16 text-center">
        <span className="cg-eyebrow block text-ink-stone">No real graph available</span>
        <p className="mt-2 text-sm text-ink-steel">The backend did not return extracted nodes for this view.</p>
      </div>
    );
  }

  const focusNode = focusNodeId ? graph.nodes.find((node) => node.id === focusNodeId) : null;
  const coreLabel = focusNode?.label || 'CausalGraph Knowledge Graph';
  const coreX = canvasWidth / 2;
  const coreY = canvasHeight * (compact ? 0.51 : 0.52);
  const coreRadius = compact ? 36 : 54;

  const handleClusterSelect = (cluster: ClusterLayout) => {
    setInspectedCluster(cluster.definition.key);
    setActiveTab(cluster.definition.key);
    setInspectedCategoryId(null);
    setInternalSelectedNodeId(null);
    if (cluster.representativeEdge) {
      setInternalSelectedEdgeId(makeEdgeId(cluster.representativeEdge));
      onEdgeSelect?.(cluster.representativeEdge);
    }
  };

  const handleCategorySelect = (cluster: ClusterLayout, category: ClusterLayout['categories'][number]) => {
    setInspectedCluster(cluster.definition.key);
    setActiveTab(cluster.definition.key);
    setInspectedCategoryId(category.id);
    if (category.backingNode) {
      setInternalSelectedNodeId(category.backingNode.id);
      setInternalSelectedEdgeId(null);
      onNodeSelect?.(category.backingNode);
    }
  };

  const handleNodeSelect = (node: GraphNode) => {
    const domain = inferNodeDomain(node);
    if (domain !== 'general') {
      setInspectedCluster(domain);
      setActiveTab(domain);
    }
    setInternalSelectedNodeId(node.id);
    setInternalSelectedEdgeId(null);
    onNodeSelect?.(node);
  };

  const handleEdgeSelect = (edge: GraphEdge) => {
    setInternalSelectedEdgeId(makeEdgeId(edge));
    setInternalSelectedNodeId(null);
    onEdgeSelect?.(edge);
  };

  const renderDrilldownCanvas = (cluster: ClusterLayout) => {
    const definition = cluster.definition;
    const centerX = canvasWidth * 0.5;
    const centerY = canvasHeight * 0.54;
    const radius = Math.min(canvasWidth, canvasHeight) * (canvasWidth < 520 ? 0.3 : 0.36);
    const categoryCenters = definition.categories.map((category, index) => {
      const angle = -Math.PI / 2 + (index / definition.categories.length) * Math.PI * 2;
      return {
        category,
        x: centerX + Math.cos(angle) * radius * 0.58,
        y: centerY + Math.sin(angle) * radius * 0.48,
      };
    });
    const cloudNodes = buildCloudNodes(
      graph,
      definition,
      categoryCenters.map((category) => ({ x: category.x, y: category.y })),
      Math.max(10, radius * 0.18),
      canvasWidth < 520 ? 1.25 : 1.55
    );
    const cloudNodeById = new Map(cloudNodes.map((node) => [node.node.id, node]));
    const visibleEdges = graph.edges
      .filter((edge) => inferEdgeDomain(edge) === definition.key)
      .filter((edge) => cloudNodeById.has(edge.source) && cloudNodeById.has(edge.target))
      .slice(0, canvasWidth < 520 ? 80 : 260);
    const selectedCloudNode = effectiveSelectedNodeId ? cloudNodeById.get(effectiveSelectedNodeId) : null;

    return (
      <div ref={containerRef} className="min-w-0 overflow-hidden rounded-xl border border-hairline bg-white">
        <svg viewBox={`0 0 ${canvasWidth} ${canvasHeight}`} className="block w-full">
          <defs>
            <pattern id={`${svgId}-drill-grid`} width="32" height="32" patternUnits="userSpaceOnUse">
              <path d="M32 0H0V32" fill="none" stroke="rgba(10,10,10,0.035)" strokeWidth="1" />
            </pattern>
            <filter id={`${svgId}-drill-shadow`} x="-30%" y="-30%" width="160%" height="160%">
              <feDropShadow dx="0" dy="10" stdDeviation="12" floodColor="#0a0a0a" floodOpacity="0.10" />
            </filter>
          </defs>
          <rect x="0" y="0" width={canvasWidth} height={canvasHeight} fill="#ffffff" />
          <rect x="0" y="0" width={canvasWidth} height={canvasHeight} fill={`url(#${svgId}-drill-grid)`} />

          {!compact && (
            <g>
              <rect
                x={18}
                y={18}
                width={canvasWidth < 520 ? 128 : 148}
                height={30}
                rx={9}
                fill="#ffffff"
                stroke="#e5e7eb"
                onClick={() => {
                  setActiveTab('overview');
                  setInspectedCategoryId(null);
                }}
                className="cursor-pointer"
              />
              <text
                x={canvasWidth < 520 ? 82 : 92}
                y={38}
                textAnchor="middle"
                className="fill-slate-900 text-[12px] font-semibold"
                onClick={() => {
                  setActiveTab('overview');
                  setInspectedCategoryId(null);
                }}
              >
                Back to overview
              </text>
              <text x={18} y={72} className="fill-slate-400 text-[11px] font-semibold uppercase tracking-[0.14em]">
                Full subgraph
              </text>
              <text x={18} y={96} className="fill-slate-950 text-[18px] font-semibold">
                {definition.label}
              </text>
              <text x={18} y={116} className="fill-slate-500 text-[12px]">
                {cluster.nodeCount} real nodes · {cluster.edgeCount} real edges · {visibleEdges.length} visible links
              </text>
            </g>
          )}

          <ellipse
            cx={centerX}
            cy={centerY}
            rx={radius * 1.55}
            ry={radius * 1.1}
            fill={definition.ringFill}
            stroke={definition.color}
            strokeOpacity={0.18}
            strokeWidth={1.2}
          />

          {visibleEdges.map((edge, index) => {
            const source = cloudNodeById.get(edge.source);
            const target = cloudNodeById.get(edge.target);
            if (!source || !target) return null;
            const selected = effectiveSelectedEdgeId === makeEdgeId(edge);
            return (
              <line
                key={`${makeEdgeId(edge)}-${index}`}
                x1={source.x}
                y1={source.y}
                x2={target.x}
                y2={target.y}
                stroke={definition.color}
                strokeOpacity={selected ? 0.72 : 0.09}
                strokeWidth={selected ? 1.8 : 0.7}
                onClick={() => handleEdgeSelect(edge)}
                className="cursor-pointer"
              />
            );
          })}

          {cloudNodes.map((cloudNode) => {
            const selected = effectiveSelectedNodeId === cloudNode.node.id;
            const highlighted = selectedNodeSet.has(cloudNode.node.id);
            return (
              <circle
                key={cloudNode.node.id}
                cx={cloudNode.x}
                cy={cloudNode.y}
                r={selected || highlighted ? cloudNode.radius + 2.4 : cloudNode.radius}
                fill={definition.color}
                fillOpacity={selected || highlighted ? 0.95 : 0.48}
                stroke={selected || highlighted ? '#0a0a0a' : '#ffffff'}
                strokeWidth={selected || highlighted ? 1.6 : 0.45}
                onClick={() => handleNodeSelect(cloudNode.node)}
                className="cursor-pointer"
              />
            );
          })}

          {categoryCenters.map((item, index) => {
            const count = cloudNodes.filter((node) => node.categoryIndex === index).length;
            if (count === 0) return null;
            const lines = splitLabel(item.category.label, canvasWidth < 520 ? 10 : 16);
            return (
              <g key={item.category.label} onClick={() => {
                const firstNode = cloudNodes.find((node) => node.categoryIndex === index);
                if (firstNode) handleNodeSelect(firstNode.node);
                setInspectedCategoryId(firstNode?.node.id || null);
              }} className="cursor-pointer">
                <circle
                  cx={item.x}
                  cy={item.y}
                  r={canvasWidth < 520 ? 18 : 24}
                  fill="rgba(255,255,255,0.94)"
                  stroke={definition.color}
                  strokeWidth="1.4"
                  filter={`url(#${svgId}-drill-shadow)`}
                />
                <text
                  x={item.x}
                  y={item.y + 5}
                  textAnchor="middle"
                  className={`${canvasWidth < 520 ? 'text-[10px]' : 'text-[12px]'} font-bold`}
                  fill={definition.textColor}
                >
                  {item.category.label
                    .split(/\s|&/)
                    .map((word) => word[0])
                    .join('')
                    .slice(0, 2)}
                </text>
                {!compact && (
                  <>
                    <text
                      x={item.x}
                      y={item.y + (canvasWidth < 520 ? 35 : 44) - (lines.length - 1) * 6}
                      textAnchor="middle"
                      className="fill-slate-950 text-[11px] font-semibold"
                      stroke="#ffffff"
                      strokeWidth="4"
                      paintOrder="stroke"
                    >
                      {lines.map((line, lineIndex) => (
                        <tspan key={line} x={item.x} dy={lineIndex === 0 ? 0 : 13}>
                          {line}
                        </tspan>
                      ))}
                    </text>
                    <text
                      x={item.x}
                      y={item.y + (canvasWidth < 520 ? 62 : 72)}
                      textAnchor="middle"
                      className="fill-slate-500 text-[10px]"
                      stroke="#ffffff"
                      strokeWidth="3"
                      paintOrder="stroke"
                    >
                      {count} nodes
                    </text>
                  </>
                )}
              </g>
            );
          })}

          <g filter={`url(#${svgId}-drill-shadow)`}>
            <circle cx={centerX} cy={centerY} r={canvasWidth < 520 ? 31 : 42} fill="#ffffff" stroke="#e5e7eb" />
            <rect
              x={centerX - (canvasWidth < 520 ? 16 : 21)}
              y={centerY - (canvasWidth < 520 ? 25 : 34)}
              width={canvasWidth < 520 ? 32 : 42}
              height={canvasWidth < 520 ? 32 : 42}
              rx={canvasWidth < 520 ? 10 : 13}
              fill={definition.color}
            />
            <text
              x={centerX}
              y={centerY - (canvasWidth < 520 ? 5 : 9)}
              textAnchor="middle"
              className={`${canvasWidth < 520 ? 'text-[12px]' : 'text-[15px]'} font-bold`}
              fill="#ffffff"
            >
              {definition.short}
            </text>
            {!compact && (
              <text x={centerX} y={centerY + 27} textAnchor="middle" className="fill-slate-950 text-[13px] font-semibold">
                {definition.tabLabel}
              </text>
            )}
          </g>

          {selectedCloudNode && !compact && (
            <g transform={`translate(${Math.min(canvasWidth - 210, Math.max(18, selectedCloudNode.x + 18))}, ${Math.max(24, selectedCloudNode.y - 42)})`}>
              <rect width="192" height="56" rx="10" fill="rgba(255,255,255,0.96)" stroke="#e5e7eb" />
              <text x="12" y="22" className="fill-slate-950 text-[12px] font-semibold">
                {truncateLabel(selectedCloudNode.node.label, 24)}
              </text>
              <text x="12" y="41" className="fill-slate-500 text-[11px]">
                {formatTypeLabel(selectedCloudNode.node.type)} · {(selectedCloudNode.node.confidence * 100).toFixed(0)}%
              </text>
            </g>
          )}
        </svg>
      </div>
    );
  };

  const renderCanvas = () => (
    !compact && activeTab !== 'overview'
      ? renderDrilldownCanvas(inspectedLayout)
      : (
    <div ref={containerRef} className="min-w-0 overflow-hidden rounded-xl border border-hairline bg-white">
      <svg viewBox={`0 0 ${canvasWidth} ${canvasHeight}`} className="block w-full">
        <defs>
          <pattern id={`${svgId}-grid`} width="32" height="32" patternUnits="userSpaceOnUse">
            <path d="M32 0H0V32" fill="none" stroke="rgba(10,10,10,0.035)" strokeWidth="1" />
          </pattern>
          <filter id={`${svgId}-soft-shadow`} x="-30%" y="-30%" width="160%" height="160%">
            <feDropShadow dx="0" dy="12" stdDeviation="14" floodColor="#0a0a0a" floodOpacity="0.10" />
          </filter>
          <filter id={`${svgId}-node-shadow`} x="-35%" y="-35%" width="170%" height="170%">
            <feDropShadow dx="0" dy="7" stdDeviation="8" floodColor="#0a0a0a" floodOpacity="0.10" />
          </filter>
          {CLUSTERS.map((cluster) => (
            <radialGradient key={cluster.key} id={`${svgId}-${cluster.key}-halo`} cx="50%" cy="50%" r="55%">
              <stop offset="0%" stopColor={cluster.softFill} stopOpacity="0.98" />
              <stop offset="100%" stopColor={cluster.color} stopOpacity="0.10" />
            </radialGradient>
          ))}
        </defs>

        <rect x="0" y="0" width={canvasWidth} height={canvasHeight} fill="#ffffff" />
        <rect x="0" y="0" width={canvasWidth} height={canvasHeight} fill={`url(#${svgId}-grid)`} />

        {clusterLayouts.map((cluster) => {
          const active = activeTab === 'overview' || activeTab === cluster.definition.key;
          const isInspected = inspectedCluster === cluster.definition.key;
          const edgeSelected = cluster.representativeEdge && effectiveSelectedEdgeId === makeEdgeId(cluster.representativeEdge);
          const opacity = active ? 1 : 0.22;
          const path = `M ${coreX} ${coreY} C ${(coreX + cluster.x) / 2} ${coreY}, ${(coreX + cluster.x) / 2} ${cluster.y}, ${cluster.x} ${cluster.y}`;

          return (
            <g key={`core-${cluster.definition.key}`} opacity={opacity}>
              <path
                d={path}
                fill="none"
                stroke={cluster.definition.color}
                strokeWidth={edgeSelected || isInspected ? 2.4 : 1.4}
                strokeOpacity={edgeSelected || isInspected ? 0.86 : 0.45}
                strokeDasharray={cluster.definition.key === 'ai' ? '0' : '6 8'}
                onClick={() => handleClusterSelect(cluster)}
                className="cursor-pointer"
              />
              {!compact && (
                <g transform={`translate(${(coreX + cluster.x) / 2}, ${(coreY + cluster.y) / 2})`}>
                  <rect
                    x={-46}
                    y={-11}
                    width={92}
                    height={22}
                    rx={7}
                    fill="rgba(255,255,255,0.92)"
                    stroke={cluster.definition.color}
                    strokeOpacity={0.28}
                  />
                  <text
                    x="0"
                    y="4"
                    textAnchor="middle"
                    fontFamily="var(--cg-font-mono)"
                    className="text-[10px] font-semibold"
                    fill={cluster.definition.textColor}
                  >
                    {cluster.definition.relationship}
                  </text>
                </g>
              )}
            </g>
          );
        })}

        {clusterLayouts.map((cluster) => {
          const active = activeTab === 'overview' || activeTab === cluster.definition.key;
          const isInspected = inspectedCluster === cluster.definition.key;
          const opacity = active ? 1 : 0.2;
          const definition = cluster.definition;

          return (
            <g key={definition.key} opacity={opacity}>
              <ellipse
                cx={cluster.x}
                cy={cluster.y}
                rx={cluster.radius * 1.17}
                ry={cluster.radius}
                fill={`url(#${svgId}-${definition.key}-halo)`}
                stroke={definition.color}
                strokeWidth={isInspected ? 1.8 : 1}
                strokeOpacity={isInspected ? 0.36 : 0.18}
                onClick={() => handleClusterSelect(cluster)}
                className="cursor-pointer"
              />
              <circle cx={cluster.x} cy={cluster.y} r="3.5" fill={definition.color} opacity="0.72" />
              {(overviewClouds.find((cloud) => cloud.key === definition.key)?.nodes || []).map((cloudNode) => {
                const selected = effectiveSelectedNodeId === cloudNode.node.id || selectedNodeSet.has(cloudNode.node.id);
                return (
                  <circle
                    key={cloudNode.node.id}
                    cx={cloudNode.x}
                    cy={cloudNode.y}
                    r={selected ? cloudNode.radius + 1.6 : cloudNode.radius}
                    fill={definition.color}
                    fillOpacity={selected ? 0.95 : compact ? 0.46 : 0.34}
                    stroke={selected ? '#0a0a0a' : 'none'}
                    strokeWidth={selected ? 1.2 : 0}
                    onClick={() => handleNodeSelect(cloudNode.node)}
                    className="cursor-pointer"
                  />
                );
              })}
              {cluster.categories.map((category) => {
                if (category.nodeCount === 0) return null;
                const selected =
                  inspectedCategoryId === category.id ||
                  effectiveSelectedNodeId === category.backingNode?.id ||
                  selectedNodeSet.has(category.backingNode?.id || category.id);
                const lineHighlighted = selectedEdgeIdSet.has(makePathEdgeId(category.backingNode?.id || category.id, definition.key));
                const nodeRadius = compact ? (selected ? 16 : 13) : (selected ? 25 : 21);
                const labelLines = splitLabel(category.shortLabel || category.label, compact ? 10 : 15);

                return (
                  <g key={category.id} onClick={() => handleCategorySelect(cluster, category)} className="cursor-pointer">
                    <line
                      x1={cluster.x}
                      y1={cluster.y}
                      x2={category.x}
                      y2={category.y}
                      stroke={definition.color}
                      strokeOpacity={selected || lineHighlighted ? 0.7 : 0.28}
                      strokeWidth={selected || lineHighlighted ? 1.7 : 1}
                      strokeDasharray="4 6"
                    />
                    <circle
                      cx={category.x}
                      cy={category.y}
                      r={nodeRadius}
                      fill="rgba(255,255,255,0.96)"
                      stroke={definition.color}
                      strokeWidth={selected ? 2.4 : 1.2}
                      filter={`url(#${svgId}-node-shadow)`}
                    />
                    <text
                      x={category.x}
                      y={category.y + (compact ? 4 : 5)}
                      textAnchor="middle"
                      className={`${compact ? 'text-[11px]' : 'text-[13px]'} font-bold`}
                      fill={definition.textColor}
                    >
                      {category.label
                        .split(/\s|&/)
                        .map((word) => word[0])
                        .join('')
                        .slice(0, 2)}
                    </text>
                    {!compact && (
                      <text
                        x={category.x}
                        y={category.y + nodeRadius + 18 - (labelLines.length - 1) * 6}
                        textAnchor="middle"
                        className="fill-slate-900 text-[11px] font-semibold"
                        stroke="#ffffff"
                        strokeWidth="4"
                        paintOrder="stroke"
                      >
                        {labelLines.map((line, index) => (
                          <tspan key={line} x={category.x} dy={index === 0 ? 0 : 13}>
                            {line}
                          </tspan>
                        ))}
                      </text>
                    )}
                  </g>
                );
              })}
              <g onClick={() => handleClusterSelect(cluster)} className="cursor-pointer">
                <circle
                  cx={cluster.x - cluster.radius * 0.55}
                  cy={cluster.y - cluster.radius * 0.88}
                  r={compact ? 15 : 19}
                  fill={definition.color}
                  filter={`url(#${svgId}-node-shadow)`}
                />
                <text
                  x={cluster.x - cluster.radius * 0.55}
                  y={cluster.y - cluster.radius * 0.88 + (definition.short === 'AI' ? 4 : 5)}
                  textAnchor="middle"
                  className={`${compact ? 'text-[10px]' : 'text-[13px]'} font-bold`}
                  fill="#ffffff"
                >
                  {definition.short}
                </text>
                <text
                  x={cluster.x - cluster.radius * 0.28}
                  y={cluster.y - cluster.radius * 0.88 - (compact ? 2 : 5)}
                  className={`${compact ? 'text-[11px]' : 'text-[16px]'} font-semibold`}
                  fill="#0a0a0a"
                >
                  {definition.label}
                </text>
                {!compact && (
                  <text
                    x={cluster.x - cluster.radius * 0.28}
                    y={cluster.y - cluster.radius * 0.88 + 14}
                    className="fill-slate-500 text-[11px]"
                  >
                    {cluster.nodeCount} nodes · {cluster.edgeCount} edges
                  </text>
                )}
              </g>
            </g>
          );
        })}

        <g filter={`url(#${svgId}-soft-shadow)`}>
          <circle cx={coreX} cy={coreY} r={coreRadius} fill="#ffffff" stroke="#e5e7eb" strokeWidth="1.2" />
          <rect
            x={coreX - (compact ? 17 : 22)}
            y={coreY - (compact ? 33 : 44)}
            width={compact ? 34 : 44}
            height={compact ? 34 : 44}
            rx={compact ? 10 : 13}
            fill="#0a0a0a"
          />
          <text
            x={coreX}
            y={coreY - (compact ? 12 : 17)}
            textAnchor="middle"
            className={`${compact ? 'text-[13px]' : 'text-[16px]'} font-bold`}
            fill="#ffffff"
          >
            cg
          </text>
          {!compact && (
            <>
              <text x={coreX} y={coreY + 18} textAnchor="middle" className="fill-slate-950 text-[16px] font-semibold">
                {truncateLabel(coreLabel, 28)}
              </text>
              <text x={coreX} y={coreY + 39} textAnchor="middle" className="fill-slate-500 text-[12px]">
                {compactNumber(stats.nodes)} nodes · {compactNumber(stats.edges)} edges
              </text>
            </>
          )}
        </g>

        {!compact && (
          <g transform={`translate(${Math.max(18, canvasWidth - 172)}, ${canvasHeight - 38})`}>
            <rect x="0" y="0" width="154" height="24" rx="8" fill="rgba(255,255,255,0.92)" stroke="#e5e7eb" />
            <text x="12" y="16" className="fill-slate-500 text-[10px] font-semibold">
              Edge types:
            </text>
            <line x1="72" y1="12" x2="96" y2="12" stroke="#1ba673" strokeWidth="2" />
            <line x1="104" y1="12" x2="128" y2="12" stroke="#1456f0" strokeWidth="2" strokeDasharray="4 4" />
            <line x1="136" y1="12" x2="148" y2="12" stroke="#8b5cf6" strokeWidth="2" />
          </g>
        )}
      </svg>
    </div>
      )
  );

  if (compact) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45 }}
        className="min-w-0 space-y-2"
      >
        {renderCanvas()}
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45 }}
      className="min-w-0 space-y-4"
    >
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <span className="cg-eyebrow block text-ink-steel">Knowledge graph</span>
          <h4 className="font-display text-[20px] font-semibold leading-[1.25] tracking-normal text-ink">
            ESG/AI cluster map
          </h4>
          <p className="mt-1 max-w-2xl text-[13px] leading-[1.55] text-ink-steel">
            Four semantic clusters organize the real extracted nodes returned by the backend graph.
          </p>
        </div>
        <div className="grid grid-cols-1 gap-2 text-right sm:flex sm:items-center sm:gap-3">
          {[
            ['Nodes', compactNumber(stats.nodes)],
            ['Edges', compactNumber(stats.edges)],
            ['Clusters', stats.categories],
          ].map(([label, value]) => (
            <div key={label} className="rounded-lg border border-hairline bg-white px-3 py-2 shadow-sm">
              <div className="text-[11px] font-medium text-ink-stone">{label}</div>
              <div className="mt-0.5 font-mono text-[13px] font-semibold text-ink">{value}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="flex flex-wrap gap-2 rounded-xl border border-hairline bg-surface-soft p-2">
        {(['overview', ...CLUSTERS.map((cluster) => cluster.key)] as ClusterTab[]).map((tab) => {
          const definition = tab === 'overview' ? null : CLUSTER_BY_KEY.get(tab);
          const active = activeTab === tab;
          return (
            <button
              key={tab}
              onClick={() => {
                setActiveTab(tab);
                if (definition) setInspectedCluster(definition.key);
              }}
              className={`inline-flex items-center gap-2 rounded-lg px-3 py-2 text-[13px] font-semibold transition ${
                active
                  ? 'bg-white text-ink shadow-sm'
                  : 'text-ink-steel hover:bg-white/80 hover:text-ink'
              }`}
            >
              {definition && (
                <span
                  className="flex h-5 min-w-5 items-center justify-center rounded-full px-1 text-[10px] font-bold text-white"
                  style={{ backgroundColor: definition.color }}
                >
                  {definition.short}
                </span>
              )}
              {definition?.tabLabel || 'Overview'}
            </button>
          );
        })}
      </div>

      <div className="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,1fr)_286px]">
        {renderCanvas()}

        <aside className="min-w-0 rounded-xl border border-hairline bg-white p-4 shadow-sm">
          <div className="flex items-start gap-3">
            <div
              className="flex h-11 min-w-11 items-center justify-center rounded-xl text-[14px] font-bold text-white"
              style={{ backgroundColor: inspectedLayout.definition.color }}
            >
              {inspectedLayout.definition.short}
            </div>
            <div className="min-w-0">
              <div className="text-[16px] font-semibold text-ink">{inspectedLayout.definition.label}</div>
              <p className="mt-1 text-[12px] leading-5 text-ink-steel">{inspectedLayout.definition.description}</p>
            </div>
          </div>

          {(selectedNode || selectedEdge) && (
            <div className="mt-4 rounded-xl border border-hairline bg-white p-3">
              <div className="text-[12px] font-semibold text-ink">
                {selectedNode ? 'Selected node' : 'Selected relationship'}
              </div>
              {selectedNode ? (
                <>
                  <div className="mt-2 text-[13px] font-semibold text-ink">{selectedNode.label}</div>
                  <div className="mt-1 text-[11px] text-ink-steel">
                    {formatTypeLabel(selectedNode.type)} · {(selectedNode.confidence * 100).toFixed(0)}% confidence
                  </div>
                  {selectedNode.description && (
                    <p className="mt-2 text-[12px] leading-5 text-ink-steel">{selectedNode.description}</p>
                  )}
                </>
              ) : selectedEdge ? (
                <>
                  <div className="mt-2 text-[13px] font-semibold text-ink">{formatTypeLabel(selectedEdge.relationship_type)}</div>
                  <div className="mt-1 text-[11px] text-ink-steel">
                    {(selectedEdge.confidence * 100).toFixed(0)}% confidence
                  </div>
                  <p className="mt-2 text-[12px] leading-5 text-ink-steel">{selectedEdge.evidence}</p>
                </>
              ) : null}
            </div>
          )}

          <div className="mt-5 rounded-xl border border-hairline bg-surface-soft p-3">
            <div className="mb-3 flex items-center justify-between">
              <div className="text-[12px] font-semibold text-ink">Child categories</div>
              <div className="font-mono text-[11px] text-ink-stone">
                {(inspectedLayout.confidence * 100).toFixed(0)}% avg
              </div>
            </div>
            <div className="space-y-2">
              {inspectedLayout.categories.filter((category) => category.nodeCount > 0).map((category) => {
                const active = inspectedCategoryId === category.id || effectiveSelectedNodeId === category.backingNode?.id;
                return (
                  <button
                    key={category.id}
                    onClick={() => handleCategorySelect(inspectedLayout, category)}
                    className={`flex w-full items-center justify-between gap-3 rounded-lg border px-3 py-2 text-left transition ${
                      active
                        ? 'border-ink bg-white'
                        : 'border-transparent bg-white/70 hover:border-hairline hover:bg-white'
                    }`}
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-[13px] font-semibold text-ink">{category.label}</span>
                      <span className="mt-0.5 block text-[11px] text-ink-stone">{category.nodeCount} real nodes</span>
                    </span>
                    <span className="font-mono text-[11px] text-ink-steel">
                      {(category.confidence * 100).toFixed(0)}%
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="mt-4 rounded-xl border border-hairline bg-white p-3">
            <div className="text-[12px] font-semibold text-ink">Real relationship sample</div>
            {inspectedLayout.representativeEdge ? (
              <div className="mt-3 space-y-3 text-[12px] leading-5">
                <div className="font-semibold text-ink">
                  {truncateLabel(graphNodeById.get(inspectedLayout.representativeEdge.source)?.label || inspectedLayout.representativeEdge.source, 34)}
                </div>
                <div className="font-mono text-[11px]" style={{ color: inspectedLayout.definition.textColor }}>
                  {formatTypeLabel(inspectedLayout.representativeEdge.relationship_type)}
                </div>
                <div className="font-semibold text-ink">
                  {truncateLabel(graphNodeById.get(inspectedLayout.representativeEdge.target)?.label || inspectedLayout.representativeEdge.target, 34)}
                </div>
                {inspectedLayout.representativeEdge.evidence && (
                  <p className="border-t border-hairline pt-3 text-[12px] leading-5 text-ink-steel">
                    {truncateLabel(inspectedLayout.representativeEdge.evidence, 140)}
                  </p>
                )}
              </div>
            ) : (
              <p className="mt-2 text-[12px] leading-5 text-ink-steel">No real relationship is available inside this cluster yet.</p>
            )}
          </div>
        </aside>
      </div>
    </motion.div>
  );
};

export default KnowledgeGraphView;
