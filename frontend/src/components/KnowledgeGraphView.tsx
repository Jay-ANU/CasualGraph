import React, { useEffect, useMemo, useRef, useState } from 'react';
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
  description: string;
  color: string;
  textColor: string;
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

// Colours match the domain tokens in src/styles/cg-tokens.css.
const CLUSTERS: ClusterDefinition[] = [
  {
    key: 'environmental',
    tabLabel: 'Environmental',
    label: 'Environmental',
    description: 'Climate, energy, water, waste and other resource topics.',
    color: '#2F7D5B',
    textColor: '#24634A',
    ringFill: 'rgba(47, 125, 91, 0.06)',
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
    description: 'Workforce, suppliers, communities and human rights.',
    color: '#3D64C4',
    textColor: '#2F4F9E',
    ringFill: 'rgba(61, 100, 196, 0.06)',
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
    description: 'Board oversight, controls, ethics, compliance and risk.',
    color: '#B07A1E',
    textColor: '#86601A',
    ringFill: 'rgba(176, 122, 30, 0.07)',
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
    label: 'AI and data',
    description: 'Artificial intelligence, data and model topics mentioned in the reports.',
    color: '#7B5BC0',
    textColor: '#5F4599',
    ringFill: 'rgba(123, 91, 192, 0.06)',
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
const LINE_STRONG = '#D5D1C8';

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
  return `${value.slice(0, limit - 1)}…`;
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
  compact: boolean,
  narrow = false
): ClusterLayout[] => {
  const degreeMap = getDegreeMap(graph);
  const positions = clusterPositions(canvasWidth, canvasHeight, compact);
  const clusterRadius = Math.max(compact ? 54 : narrow ? 56 : 76, Math.min(canvasWidth, canvasHeight) * (compact ? 0.17 : 0.2));
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
});

const formatCount = (value: number) => value.toLocaleString();

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
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(width);
  const initialTab = useMemo(() => compact ? 'overview' : getInitialClusterTab(), [compact]);
  const [activeTab, setActiveTab] = useState<ClusterTab>(initialTab);
  const [inspectedCluster, setInspectedCluster] = useState<DomainKey>(initialTab === 'overview' ? 'environmental' : initialTab);
  const [inspectedCategoryId, setInspectedCategoryId] = useState<string | null>(null);
  const [internalSelectedNodeId, setInternalSelectedNodeId] = useState<string | null>(null);
  const [internalSelectedEdgeId, setInternalSelectedEdgeId] = useState<string | null>(null);

  const hasNodes = graph.nodes.length > 0;
  const canvasWidth = Math.max(compact ? 260 : 300, Math.floor(containerWidth || width));
  const narrow = canvasWidth < 560;
  // On narrow screens the clusters sit closer together, so the canvas is
  // shortened to keep them readable instead of floating in empty space.
  const canvasHeight = compact
    ? Math.min(height, 340)
    : narrow
      ? Math.min(height, Math.max(420, Math.round(canvasWidth * 1.3)))
      : height;
  const stats = summarizeGraph(graph);
  const effectiveSelectedNodeId = selectedNodeId ?? internalSelectedNodeId;
  const effectiveSelectedEdgeId = selectedEdgeId ?? internalSelectedEdgeId;
  const clusterLayouts = useMemo(
    () => buildClusterLayouts(graph, canvasWidth, canvasHeight, compact, narrow),
    [graph, canvasWidth, canvasHeight, compact, narrow]
  );
  const graphNodeById = useMemo(() => new Map(graph.nodes.map((node) => [node.id, node])), [graph.nodes]);
  const inspectedLayout = clusterLayouts.find((cluster) => cluster.definition.key === inspectedCluster) || clusterLayouts[0];
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
  }, [width, hasNodes]);

  useEffect(() => {
    if (!effectiveSelectedNodeId) return;
    const node = graph.nodes.find((item) => item.id === effectiveSelectedNodeId);
    const domain = node ? inferNodeDomain(node) : 'general';
    if (domain !== 'general') {
      setInspectedCluster(domain);
      setActiveTab(domain);
    }
  }, [effectiveSelectedNodeId, graph.nodes]);

  if (!hasNodes) {
    return (
      <div className="rounded-xl border border-dashed border-line-strong px-6 py-14 text-center">
        <p className="font-medium text-ink">No graph data</p>
        <p className="mt-1 text-sm text-ink-3">No extracted entities were returned for this view.</p>
      </div>
    );
  }

  const focusNode = focusNodeId ? graph.nodes.find((node) => node.id === focusNodeId) : null;
  const coreLabel = focusNode?.label || 'All reports';
  const coreX = canvasWidth / 2;
  const coreY = canvasHeight * (compact ? 0.51 : 0.52);
  const coreRadius = compact ? 34 : narrow ? 38 : 50;

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
    const centerY = canvasHeight * 0.5;
    const radius = Math.min(canvasWidth, canvasHeight) * (narrow ? 0.3 : 0.36);
    const categoryCenters = definition.categories.map((category, index) => {
      const angle = -Math.PI / 2 + (index / definition.categories.length) * Math.PI * 2;
      return {
        category,
        x: centerX + Math.cos(angle) * radius * 0.62,
        y: centerY + Math.sin(angle) * radius * 0.52,
      };
    });
    const cloudNodes = buildCloudNodes(
      graph,
      definition,
      categoryCenters.map((category) => ({ x: category.x, y: category.y })),
      Math.max(10, radius * 0.18),
      narrow ? 1.25 : 1.55
    );
    const cloudNodeById = new Map(cloudNodes.map((node) => [node.node.id, node]));
    const visibleEdges = graph.edges
      .filter((edge) => inferEdgeDomain(edge) === definition.key)
      .filter((edge) => cloudNodeById.has(edge.source) && cloudNodeById.has(edge.target))
      .slice(0, narrow ? 80 : 260);
    const selectedCloudNode = effectiveSelectedNodeId ? cloudNodeById.get(effectiveSelectedNodeId) : null;

    return (
      <div className="min-w-0 overflow-hidden rounded-xl border border-line bg-white">
        <svg viewBox={`0 0 ${canvasWidth} ${canvasHeight}`} className="block w-full" role="img" aria-label={`${definition.label} entities and relationships`}>
          <rect x="0" y="0" width={canvasWidth} height={canvasHeight} fill="#FFFFFF" />

          <ellipse
            cx={centerX}
            cy={centerY}
            rx={radius * 1.55}
            ry={radius * 1.1}
            fill={definition.ringFill}
            stroke={definition.color}
            strokeOpacity={0.16}
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
                stroke={selected ? definition.color : '#1A1915'}
                strokeOpacity={selected ? 0.8 : 0.07}
                strokeWidth={selected ? 1.6 : 0.7}
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
                fillOpacity={selected || highlighted ? 1 : 0.5}
                stroke={selected || highlighted ? '#1A1915' : 'none'}
                strokeWidth={selected || highlighted ? 1.2 : 0}
                onClick={() => handleNodeSelect(cloudNode.node)}
                className="cursor-pointer"
              />
            );
          })}

          {categoryCenters.map((item, index) => {
            const count = cloudNodes.filter((node) => node.categoryIndex === index).length;
            if (count === 0) return null;
            const lines = splitLabel(item.category.label, narrow ? 10 : 16);
            return (
              <g
                key={item.category.label}
                onClick={() => {
                  const firstNode = cloudNodes.find((node) => node.categoryIndex === index);
                  if (firstNode) handleNodeSelect(firstNode.node);
                  setInspectedCategoryId(firstNode?.node.id || null);
                }}
                className="cursor-pointer"
              >
                <text
                  x={item.x}
                  y={item.y - (narrow ? 22 : 28) - (lines.length - 1) * 13}
                  textAnchor="middle"
                  className="fill-ink text-[12px] font-medium"
                  stroke="#FFFFFF"
                  strokeWidth="4"
                  paintOrder="stroke"
                >
                  {lines.map((line, lineIndex) => (
                    <tspan key={line} x={item.x} dy={lineIndex === 0 ? 0 : 13}>
                      {line}
                    </tspan>
                  ))}
                  <tspan x={item.x} dy={14} className="fill-ink-4 text-[11px] font-normal">
                    {count} {count === 1 ? 'entity' : 'entities'}
                  </tspan>
                </text>
              </g>
            );
          })}

          {selectedCloudNode && !compact && (
            <g transform={`translate(${Math.min(canvasWidth - 214, Math.max(14, selectedCloudNode.x + 16))}, ${Math.max(14, selectedCloudNode.y - 44)})`}>
              <rect width="200" height="50" rx="8" fill="#FFFFFF" stroke={LINE_STRONG} />
              <text x="12" y="21" className="fill-ink text-[12px] font-medium">
                {truncateLabel(selectedCloudNode.node.label, 26)}
              </text>
              <text x="12" y="38" className="fill-ink-4 text-[11px]">
                {formatTypeLabel(selectedCloudNode.node.type)} · {(selectedCloudNode.node.confidence * 100).toFixed(0)}% confidence
              </text>
            </g>
          )}
        </svg>
      </div>
    );
  };

  const renderOverviewCanvas = () => (
    <div className="min-w-0 overflow-hidden rounded-xl border border-line bg-white">
      <svg viewBox={`0 0 ${canvasWidth} ${canvasHeight}`} className="block w-full" role="img" aria-label="Entities grouped by ESG domain">
        <rect x="0" y="0" width={canvasWidth} height={canvasHeight} fill="#FFFFFF" />

        {clusterLayouts.map((cluster) => {
          const active = activeTab === 'overview' || activeTab === cluster.definition.key;
          const isInspected = !compact && inspectedCluster === cluster.definition.key;
          const edgeSelected = cluster.representativeEdge && effectiveSelectedEdgeId === makeEdgeId(cluster.representativeEdge);
          const emphasised = Boolean(edgeSelected || isInspected);
          const path = `M ${coreX} ${coreY} C ${(coreX + cluster.x) / 2} ${coreY}, ${(coreX + cluster.x) / 2} ${cluster.y}, ${cluster.x} ${cluster.y}`;

          return (
            <path
              key={`core-${cluster.definition.key}`}
              d={path}
              fill="none"
              stroke={emphasised ? cluster.definition.color : LINE_STRONG}
              strokeWidth={emphasised ? 1.5 : 1}
              strokeOpacity={active ? (emphasised ? 0.7 : 1) : 0.3}
              strokeDasharray={emphasised ? undefined : '3 5'}
              onClick={() => handleClusterSelect(cluster)}
              className="cursor-pointer"
            />
          );
        })}

        {/* Drawn before the clusters so cluster labels stay readable where they overlap it. */}
        <g>
          <circle cx={coreX} cy={coreY} r={coreRadius} fill="#FFFFFF" stroke={LINE_STRONG} />
          <circle cx={coreX} cy={coreY - (compact ? 10 : 14)} r={compact ? 3 : 3.5} fill="#1A1915" />
          <text
            x={coreX}
            y={coreY + (compact ? 6 : 6)}
            textAnchor="middle"
            className={`fill-ink font-medium ${compact ? 'text-[10px]' : 'text-[12px]'}`}
          >
            {truncateLabel(coreLabel, compact || narrow ? 12 : 16)}
          </text>
          {!compact && (
            <text x={coreX} y={coreY + 22} textAnchor="middle" className="fill-ink-4 text-[10px]">
              {formatCount(stats.nodes)} entities
            </text>
          )}
        </g>

        {clusterLayouts.map((cluster) => {
          const active = activeTab === 'overview' || activeTab === cluster.definition.key;
          const isInspected = !compact && inspectedCluster === cluster.definition.key;
          const definition = cluster.definition;
          const labelX = cluster.x - cluster.radius * 1.05;
          const labelY = cluster.y - cluster.radius * 0.98;

          return (
            <g key={definition.key} opacity={active ? 1 : 0.25}>
              <ellipse
                cx={cluster.x}
                cy={cluster.y}
                rx={cluster.radius * 1.17}
                ry={cluster.radius}
                fill={definition.ringFill}
                stroke={definition.color}
                strokeOpacity={isInspected ? 0.4 : 0.16}
                onClick={() => handleClusterSelect(cluster)}
                className="cursor-pointer"
              />
              {(overviewClouds.find((cloud) => cloud.key === definition.key)?.nodes || []).map((cloudNode) => {
                const selected = effectiveSelectedNodeId === cloudNode.node.id || selectedNodeSet.has(cloudNode.node.id);
                return (
                  <circle
                    key={cloudNode.node.id}
                    cx={cloudNode.x}
                    cy={cloudNode.y}
                    r={selected ? cloudNode.radius + 1.6 : cloudNode.radius}
                    fill={definition.color}
                    fillOpacity={selected ? 1 : compact ? 0.45 : 0.35}
                    stroke={selected ? '#1A1915' : 'none'}
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
                const nodeRadius = compact ? (selected ? 6 : 4.5) : (selected ? 7 : 5.5);
                const labelLines = splitLabel(category.shortLabel || category.label, compact ? 10 : 15);

                return (
                  <g key={category.id} onClick={() => handleCategorySelect(cluster, category)} className="cursor-pointer">
                    <line
                      x1={cluster.x}
                      y1={cluster.y}
                      x2={category.x}
                      y2={category.y}
                      stroke={definition.color}
                      strokeOpacity={selected || lineHighlighted ? 0.6 : 0.22}
                      strokeWidth={selected || lineHighlighted ? 1.4 : 1}
                    />
                    <circle
                      cx={category.x}
                      cy={category.y}
                      r={nodeRadius}
                      fill={selected ? definition.color : '#FFFFFF'}
                      stroke={definition.color}
                      strokeWidth={1.5}
                    />
                    {!compact && !narrow && (
                      <text
                        x={category.x}
                        y={category.y + nodeRadius + 15 - (labelLines.length - 1) * 6}
                        textAnchor="middle"
                        className={`text-[11px] ${selected ? 'fill-ink font-medium' : 'fill-ink-3'}`}
                        stroke="#FFFFFF"
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
                <circle cx={Math.max(10, labelX)} cy={labelY - (compact ? 4 : 5)} r={compact ? 3.5 : 4} fill={definition.color} />
                <text
                  x={Math.max(10, labelX) + 10}
                  y={labelY}
                  className={`fill-ink font-medium ${compact ? 'text-[11px]' : 'text-[14px]'}`}
                  stroke="#FFFFFF"
                  strokeWidth="4"
                  paintOrder="stroke"
                >
                  {definition.label}
                </text>
                {!compact && (
                  <text
                    x={Math.max(10, labelX) + 10}
                    y={labelY + 16}
                    className="fill-ink-4 text-[11px]"
                    stroke="#FFFFFF"
                    strokeWidth="4"
                    paintOrder="stroke"
                  >
                    {formatCount(cluster.nodeCount)} entities{narrow ? '' : ` · ${formatCount(cluster.edgeCount)} relationships`}
                  </text>
                )}
              </g>
            </g>
          );
        })}

      </svg>
    </div>
  );

  const renderCanvas = () => (
    !compact && activeTab !== 'overview'
      ? renderDrilldownCanvas(inspectedLayout)
      : renderOverviewCanvas()
  );

  if (compact) {
    return (
      <div ref={containerRef} className="min-w-0">
        {renderCanvas()}
      </div>
    );
  }

  const tabs: ClusterTab[] = ['overview', ...CLUSTERS.map((cluster) => cluster.key)];
  const activeDefinition = activeTab === 'overview' ? null : CLUSTER_BY_KEY.get(activeTab);
  const activeLayout = activeDefinition ? clusterLayouts.find((cluster) => cluster.definition.key === activeDefinition.key) : null;
  const inspected = inspectedLayout.definition;

  return (
    <div className="min-w-0 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <div className="max-w-full overflow-x-auto">
          <div className="segmented" role="tablist" aria-label="Graph view">
            {tabs.map((tab) => {
              const definition = tab === 'overview' ? null : CLUSTER_BY_KEY.get(tab);
              return (
                <button
                  key={tab}
                  type="button"
                  role="tab"
                  aria-selected={activeTab === tab}
                  onClick={() => {
                    setActiveTab(tab);
                    if (definition) setInspectedCluster(definition.key);
                  }}
                  className="shrink-0"
                >
                  {definition && <span className="status-dot" style={{ backgroundColor: definition.color }} />}
                  {definition?.tabLabel || 'Overview'}
                </button>
              );
            })}
          </div>
        </div>
        <p className="text-xs tabular-nums text-ink-4">
          {activeLayout
            ? `${formatCount(activeLayout.nodeCount)} entities · ${formatCount(activeLayout.edgeCount)} relationships`
            : `${formatCount(stats.nodes)} entities · ${formatCount(stats.edges)} relationships`}
        </p>
      </div>

      <div className="grid min-w-0 gap-3 xl:grid-cols-[minmax(0,1fr)_280px]">
        <div ref={containerRef} className="min-w-0">
          {renderCanvas()}
        </div>

        <aside className="min-w-0 rounded-xl border border-line bg-white text-sm">
          <div className="border-b border-line p-4">
            <div className="flex items-center gap-2">
              <span className="status-dot h-2 w-2" style={{ backgroundColor: inspected.color }} />
              <span className="font-medium text-ink">{inspected.label}</span>
            </div>
            <p className="mt-1 text-xs leading-5 text-ink-3">{inspected.description}</p>
            <p className="mt-2 text-xs tabular-nums text-ink-4">
              {formatCount(inspectedLayout.nodeCount)} entities · {formatCount(inspectedLayout.edgeCount)} relationships
              {inspectedLayout.nodeCount > 0 && ` · ${(inspectedLayout.confidence * 100).toFixed(0)}% avg. confidence`}
            </p>
          </div>

          {(selectedNode || selectedEdge) && (
            <div className="border-b border-line p-4">
              <div className="section-label mb-1">{selectedNode ? 'Selected entity' : 'Selected relationship'}</div>
              {selectedNode ? (
                <>
                  <p className="font-medium text-ink">{selectedNode.label}</p>
                  <p className="mt-0.5 text-xs text-ink-4">
                    {formatTypeLabel(selectedNode.type)} · {(selectedNode.confidence * 100).toFixed(0)}% confidence
                  </p>
                  {selectedNode.description && (
                    <p className="mt-2 text-xs leading-5 text-ink-3">{selectedNode.description}</p>
                  )}
                </>
              ) : selectedEdge ? (
                <>
                  <p className="text-[13px] leading-5">
                    <span className="font-medium text-ink">
                      {truncateLabel(graphNodeById.get(selectedEdge.source)?.label || selectedEdge.source, 34)}
                    </span>{' '}
                    <span className="font-mono text-[11px] text-ink-4">{formatTypeLabel(selectedEdge.relationship_type)}</span>{' '}
                    <span className="font-medium text-ink">
                      {truncateLabel(graphNodeById.get(selectedEdge.target)?.label || selectedEdge.target, 34)}
                    </span>
                  </p>
                  <p className="mt-0.5 text-xs text-ink-4">{(selectedEdge.confidence * 100).toFixed(0)}% confidence</p>
                  {selectedEdge.evidence && (
                    <p className="mt-2 text-xs leading-5 text-ink-3">{truncateLabel(selectedEdge.evidence, 220)}</p>
                  )}
                </>
              ) : null}
            </div>
          )}

          <div className="border-b border-line p-4">
            <div className="section-label mb-1">Categories</div>
            {inspectedLayout.categories.some((category) => category.nodeCount > 0) ? (
              <ul>
                {inspectedLayout.categories.filter((category) => category.nodeCount > 0).map((category) => {
                  const active = inspectedCategoryId === category.id || effectiveSelectedNodeId === category.backingNode?.id;
                  return (
                    <li key={category.id}>
                      <button
                        type="button"
                        onClick={() => handleCategorySelect(inspectedLayout, category)}
                        className="flex w-full items-baseline justify-between gap-3 py-1.5 text-left text-[13px] transition-colors hover:text-ink"
                      >
                        <span className={`truncate ${active ? 'font-medium text-ink' : 'text-ink-2'}`}>{category.label}</span>
                        <span className="shrink-0 font-mono text-[11px] text-ink-4">{formatCount(category.nodeCount)}</span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="text-xs text-ink-4">No entities in this domain yet.</p>
            )}
          </div>

          <div className="p-4">
            <div className="section-label mb-1.5">Example relationship</div>
            {inspectedLayout.representativeEdge ? (
              <>
                <p className="text-[13px] leading-5">
                  <span className="font-medium text-ink">
                    {truncateLabel(graphNodeById.get(inspectedLayout.representativeEdge.source)?.label || inspectedLayout.representativeEdge.source, 34)}
                  </span>{' '}
                  <span className="font-mono text-[11px]" style={{ color: inspected.textColor }}>
                    {formatTypeLabel(inspectedLayout.representativeEdge.relationship_type)}
                  </span>{' '}
                  <span className="font-medium text-ink">
                    {truncateLabel(graphNodeById.get(inspectedLayout.representativeEdge.target)?.label || inspectedLayout.representativeEdge.target, 34)}
                  </span>
                </p>
                {inspectedLayout.representativeEdge.evidence && (
                  <p className="mt-2 text-xs leading-5 text-ink-3">
                    {truncateLabel(inspectedLayout.representativeEdge.evidence, 160)}
                  </p>
                )}
              </>
            ) : (
              <p className="text-xs text-ink-4">No relationships in this domain yet.</p>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
};

export default KnowledgeGraphView;
