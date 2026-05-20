import React, { useEffect, useId, useRef, useState } from 'react';
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

type PositionedNode = GraphNode & {
  x: number;
  y: number;
  degree: number;
  isFocus: boolean;
  ring: 'focus' | 'primary' | 'secondary';
  rank: number;
};

const DOMAIN_COLORS: Record<string, string> = {
  environmental: '#1ba673',
  social: '#1456f0',
  governance: '#ff5530',
  general: '#5f5f5f',
  ai: '#a855f7',
};

const CONF_LOW = '#a8aab2';
const CONF_MID = '#5f5f5f';
const CONF_HIGH = '#0a0a0a';
const HIGHLIGHT_STROKE = '#1456f0';

const edgeStrokeColor = (confidence: number) => {
  if (confidence >= 0.8) return CONF_HIGH;
  if (confidence >= 0.6) return CONF_MID;
  return CONF_LOW;
};

const edgeStrokeWidth = (confidence: number, isEmphasized: boolean) => {
  let base = 1;
  if (confidence >= 0.8) base = 2;
  else if (confidence >= 0.6) base = 1.5;
  return isEmphasized ? base + 1.4 : base;
};

const makeEdgeId = (edge: GraphEdge) => `${edge.source}|${edge.relationship_type}|${edge.target}`;
const makePathEdgeId = (source: string, target: string) => `${source}|${target}`;

const normalizeDomainKey = (value: string) => {
  const normalized = String(value || 'general').toLowerCase();
  if (normalized.includes('environment')) return 'environmental';
  if (normalized.includes('social')) return 'social';
  if (normalized.includes('govern')) return 'governance';
  if (normalized.includes('ai')) return 'ai';
  return 'general';
};

const truncateLabel = (value: string, limit = 26) => {
  if (value.length <= limit) return value;
  return `${value.slice(0, limit - 1)}...`;
};

const formatTypeLabel = (value: string) => value.replace(/_/g, ' ');

const getDegreeMap = (graph: GraphData) => {
  const degreeMap = new Map<string, number>();
  graph.nodes.forEach((node: GraphNode) => degreeMap.set(node.id, 0));
  graph.edges.forEach((edge: GraphEdge) => {
    degreeMap.set(edge.source, (degreeMap.get(edge.source) || 0) + 1);
    degreeMap.set(edge.target, (degreeMap.get(edge.target) || 0) + 1);
  });
  return degreeMap;
};

const getDefaultFocusNodeId = (graph: GraphData) => {
  const degreeMap = getDegreeMap(graph);
  const companyNode = graph.nodes
    .filter((node: GraphNode) => node.type.toLowerCase().includes('company'))
    .sort((a: GraphNode, b: GraphNode) => (degreeMap.get(b.id) || 0) - (degreeMap.get(a.id) || 0))[0];
  if (companyNode) return companyNode.id;

  return [...graph.nodes]
    .sort((a: GraphNode, b: GraphNode) => (degreeMap.get(b.id) || 0) - (degreeMap.get(a.id) || 0))[0]
    ?.id || null;
};

const getNodeRadius = (node: PositionedNode, isSelected: boolean) => {
  const baseByType = node.type.toLowerCase().includes('company')
    ? 22
    : node.type.toLowerCase().includes('metric') || node.type.toLowerCase().includes('initiative')
      ? 18
      : 16;
  const focusBoost = node.isFocus ? 8 : 0;
  const degreeBoost = Math.min(node.degree, 4) * 1.5;
  const selectedBoost = isSelected ? 4 : 0;
  return baseByType + focusBoost + degreeBoost + selectedBoost;
};

const getNodeBudget = (graph: GraphData) => {
  const total = graph.nodes.length;
  if (total <= 24) return total;
  if (total <= 60) return 24;
  if (total <= 140) return 32;
  return 40;
};

const buildLayout = (graph: GraphData, canvasWidth: number, canvasHeight: number, focusNodeId?: string | null) => {
  const degreeMap = getDegreeMap(graph);
  const resolvedFocusId = focusNodeId || getDefaultFocusNodeId(graph);
  const focusNode = graph.nodes.find((node: GraphNode) => node.id === resolvedFocusId) || graph.nodes[0];
  const neighborIds = new Set(
    graph.edges.flatMap((edge: GraphEdge) => {
      if (edge.source === focusNode.id) return [edge.target];
      if (edge.target === focusNode.id) return [edge.source];
      return [];
    })
  );

  const primaryNodes = graph.nodes
    .filter((node: GraphNode) => node.id !== focusNode.id && neighborIds.has(node.id))
    .sort((a: GraphNode, b: GraphNode) => (degreeMap.get(b.id) || 0) - (degreeMap.get(a.id) || 0));
  const secondaryNodes = graph.nodes
    .filter((node: GraphNode) => node.id !== focusNode.id && !neighborIds.has(node.id))
    .sort((a: GraphNode, b: GraphNode) => (degreeMap.get(b.id) || 0) - (degreeMap.get(a.id) || 0));

  const nodeBudget = getNodeBudget(graph);
  const maxPrimary = Math.min(primaryNodes.length, Math.max(10, Math.floor((nodeBudget - 1) * 0.65)));
  const maxSecondary = Math.max(0, nodeBudget - 1 - maxPrimary);
  const visiblePrimaryNodes = primaryNodes.slice(0, maxPrimary);
  const visibleSecondaryNodes = secondaryNodes.slice(0, maxSecondary);

  const centerX = canvasWidth / 2;
  const centerY = canvasHeight / 2;
  const innerRadius = Math.min(canvasWidth, canvasHeight) * 0.3;
  const outerRadius = Math.min(canvasWidth, canvasHeight) * 0.44;

  const positioned = new Map<string, PositionedNode>();
  positioned.set(focusNode.id, {
    ...focusNode,
    x: centerX,
    y: centerY,
    degree: degreeMap.get(focusNode.id) || 0,
    isFocus: true,
    ring: 'focus',
    rank: 0,
  });

  const placeOnRing = (
    nodes: GraphNode[],
    radius: number,
    ring: 'primary' | 'secondary',
    startAngle = -Math.PI / 2
  ) => {
    if (nodes.length === 0) return;
    nodes.forEach((node: GraphNode, index: number) => {
      const angle = startAngle + (index / nodes.length) * Math.PI * 2;
      positioned.set(node.id, {
        ...node,
        x: centerX + Math.cos(angle) * radius,
        y: centerY + Math.sin(angle) * radius,
        degree: degreeMap.get(node.id) || 0,
        isFocus: false,
        ring,
        rank: index,
      });
    });
  };

  placeOnRing(visiblePrimaryNodes, innerRadius, 'primary');
  placeOnRing(visibleSecondaryNodes, outerRadius, 'secondary', -Math.PI / 3);

  return {
    focusNodeId: focusNode.id,
    visibleNodeCount: positioned.size,
    hiddenNodeCount: Math.max(0, graph.nodes.length - positioned.size),
    nodes: graph.nodes
      .map((node: GraphNode) => positioned.get(node.id))
      .filter((node): node is PositionedNode => Boolean(node)),
  };
};

const isEdgeConnectedToNode = (edge: GraphEdge, nodeId?: string | null) => {
  if (!nodeId) return false;
  return edge.source === nodeId || edge.target === nodeId;
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
  const canvasWidth = Math.max(320, Math.floor(containerWidth || width));
  const canvasHeight = compact ? Math.min(height, 300) : height;
  const markerLowId = `${svgId}-graph-arrow-low`;
  const markerMidId = `${svgId}-graph-arrow-mid`;
  const markerHighId = `${svgId}-graph-arrow-high`;
  const markerHighlightId = `${svgId}-graph-arrow-highlight`;
  const nodeShadowId = `${svgId}-node-shadow`;

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

  if (!graph.nodes.length) {
    return (
      <div className="cg-empty-state py-16 text-center">
        <span className="cg-eyebrow block text-ink-stone">No graph available</span>
        <p className="mt-2 text-sm text-ink-steel">No graph data available for this report.</p>
      </div>
    );
  }

  const layout = buildLayout(graph, canvasWidth, canvasHeight, focusNodeId);
  const nodeById = new Map(layout.nodes.map((node: PositionedNode) => [node.id, node]));
  const highlightedNodeId = selectedNodeId || layout.focusNodeId;
  const highlightNodeSet = new Set(highlightPath?.nodes || []);
  const highlightEdgeSet = new Set(
    (highlightPath?.edges || []).flatMap(([source, target]) => [
      makePathEdgeId(source, target),
      makePathEdgeId(target, source),
    ])
  );
  const hasPathHighlight = highlightNodeSet.size > 0 || highlightEdgeSet.size > 0;
  const visibleEdgeCount = graph.edges.filter((edge: GraphEdge) => nodeById.has(edge.source) && nodeById.has(edge.target)).length;

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45 }} className={compact ? 'space-y-2' : 'space-y-4'}>
      {!compact && (
        <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <span className="cg-eyebrow block text-ink-steel">Knowledge graph</span>
            <h4 className="font-display text-[18px] font-semibold leading-[1.35] tracking-normal text-ink">Focused view</h4>
            <p className="mt-1 text-[13px] leading-[1.55] text-ink-steel">
              Centered on{' '}
              <span className="font-mono text-[12px] text-ink-charcoal">
                {nodeById.get(layout.focusNodeId)?.label || 'the strongest entity'}
              </span>
              .
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-ink-steel">
            <span>Nodes <span className="font-mono text-[12px] text-ink-charcoal">{layout.visibleNodeCount}/{graph.metadata.node_count}</span></span>
            <span className="text-ink-faint">·</span>
            <span>Edges <span className="font-mono text-[12px] text-ink-charcoal">{visibleEdgeCount}/{graph.metadata.edge_count}</span></span>
            <span className="text-ink-faint">·</span>
            <span className="font-mono text-[12px] text-ink-steel">
              {layout.hiddenNodeCount > 0 ? 'focused' : layout.nodes.length <= 12 ? 'detail' : 'condensed'}
            </span>
          </div>
        </div>
      )}

      {!compact && layout.hiddenNodeCount > 0 && (
        <div className="cg-tool-panel-soft px-3 py-2 text-xs text-ink-steel">
          Showing the most connected entities around the current focus. Select a node to refocus and reveal a different neighborhood.
        </div>
      )}

      <div ref={containerRef} className="cg-grid overflow-hidden rounded-xl border border-hairline bg-white">
        <svg viewBox={`0 0 ${canvasWidth} ${canvasHeight}`} className="block w-full">
          <defs>
            <filter id={nodeShadowId} x="-20%" y="-20%" width="140%" height="140%">
              <feDropShadow dx="0" dy="6" stdDeviation="8" floodColor="#0f172a" floodOpacity="0.10" />
            </filter>
            <marker id={markerLowId} viewBox="0 -5 10 10" refX="9" refY="0" markerWidth="6" markerHeight="6" orient="auto">
              <path d="M0,-4L10,0L0,4" fill={CONF_LOW} />
            </marker>
            <marker id={markerMidId} viewBox="0 -5 10 10" refX="9" refY="0" markerWidth="6" markerHeight="6" orient="auto">
              <path d="M0,-4L10,0L0,4" fill={CONF_MID} />
            </marker>
            <marker id={markerHighId} viewBox="0 -5 10 10" refX="9" refY="0" markerWidth="6" markerHeight="6" orient="auto">
              <path d="M0,-4L10,0L0,4" fill={CONF_HIGH} />
            </marker>
            <marker id={markerHighlightId} viewBox="0 -5 10 10" refX="9" refY="0" markerWidth="6" markerHeight="6" orient="auto">
              <path d="M0,-4L10,0L0,4" fill={HIGHLIGHT_STROKE} />
            </marker>
          </defs>

          <rect x="0" y="0" width={canvasWidth} height={canvasHeight} fill="rgba(255,255,255,0.72)" />
          <circle cx={canvasWidth / 2} cy={canvasHeight / 2} r={Math.min(canvasWidth, canvasHeight) * 0.28} fill="rgba(10,10,10,0.018)" />
          <circle cx={canvasWidth / 2} cy={canvasHeight / 2} r={Math.min(canvasWidth, canvasHeight) * 0.41} fill="rgba(10,10,10,0.012)" />

          {graph.edges.map((edge: GraphEdge) => {
            const source = nodeById.get(edge.source);
            const target = nodeById.get(edge.target);
            if (!source || !target) return null;

            const edgeId = makeEdgeId(edge);
            const isSelected = selectedEdgeId === edgeId;
            const relatesToSelection = isEdgeConnectedToNode(edge, highlightedNodeId);
            const isPathHighlighted = highlightEdgeSet.has(makePathEdgeId(edge.source, edge.target));
            const mutedByPath = hasPathHighlight && !isPathHighlighted;
            const stroke = isPathHighlighted ? HIGHLIGHT_STROKE : edgeStrokeColor(edge.confidence);
            const markerId = isPathHighlighted
              ? markerHighlightId
              : edge.confidence >= 0.8
                ? markerHighId
                : edge.confidence >= 0.6
                  ? markerMidId
                  : markerLowId;
            const midX = (source.x + target.x) / 2;
            const midY = (source.y + target.y) / 2;
            const dx = target.x - source.x;
            const dy = target.y - source.y;
            const edgeLength = Math.sqrt(dx * dx + dy * dy) || 1;
            const normalX = -dy / edgeLength;
            const normalY = dx / edgeLength;
            const labelX = midX + normalX * 18;
            const labelY = midY + normalY * 18;
            const shouldShowLabel = !compact && (isSelected || (graph.nodes.length <= 18 && relatesToSelection));

            return (
              <g key={edgeId} onClick={() => onEdgeSelect?.(edge)} className="cursor-pointer">
                <line
                  x1={source.x}
                  y1={source.y}
                  x2={target.x}
                  y2={target.y}
                  stroke={stroke}
                  strokeWidth={edgeStrokeWidth(edge.confidence, isSelected || isPathHighlighted || relatesToSelection)}
                  strokeOpacity={mutedByPath ? 0.18 : isPathHighlighted ? 1 : isSelected ? 0.95 : relatesToSelection ? 0.72 : 0.32}
                  markerEnd={`url(#${markerId})`}
                />
                {shouldShowLabel && (
                  <g transform={`translate(${labelX}, ${labelY})`}>
                    <rect
                      x={-54}
                      y={-11}
                      width={108}
                      height={22}
                      rx={6}
                      fill="rgba(255,255,255,0.92)"
                      stroke={isSelected ? stroke : '#e5e7eb'}
                    />
                    <text
                      x="0"
                      y="4"
                      textAnchor="middle"
                      fontFamily="var(--cg-font-mono)"
                      className="fill-slate-700 text-[10px] font-medium"
                    >
                      {truncateLabel(formatTypeLabel(edge.relationship_type), 18)}
                    </text>
                  </g>
                )}
              </g>
            );
          })}

          {layout.nodes.map((node: PositionedNode) => {
            const isSelected = selectedNodeId === node.id;
            const isRelatedToSelection = node.id === highlightedNodeId || graph.edges.some(edge => isEdgeConnectedToNode(edge, highlightedNodeId) && (edge.source === node.id || edge.target === node.id));
            const isPathHighlighted = highlightNodeSet.has(node.id);
            const mutedByPath = hasPathHighlight && !isPathHighlighted;
            const radius = compact ? Math.max(10, getNodeRadius(node, isSelected) - 8) : getNodeRadius(node, isSelected);
            const fill = isPathHighlighted
              ? HIGHLIGHT_STROKE
              : DOMAIN_COLORS[normalizeDomainKey(node.domain)] || DOMAIN_COLORS.general;
            const labelY = node.y - radius - 14;
            const typeY = node.y + radius + 18;
            const shouldShowNodeLabel = compact
              ? layout.nodes.length <= 8 && (node.isFocus || isSelected || isPathHighlighted)
              : (
              node.isFocus ||
              isSelected ||
              isPathHighlighted ||
              (isRelatedToSelection && layout.nodes.length <= 18) ||
              (node.ring === 'primary' && node.rank < 4 && layout.nodes.length <= 16)
            );
            const shouldShowTypeLabel = !compact && shouldShowNodeLabel && (node.isFocus || isSelected || node.rank < 3);

            return (
              <g key={node.id} onClick={() => onNodeSelect?.(node)} className="cursor-pointer">
                <circle
                  cx={node.x}
                  cy={node.y}
                  r={radius}
                  fill={fill}
                  fillOpacity={node.isFocus ? 0.9 : 0.82}
                  stroke={isPathHighlighted || isSelected ? '#0a0a0a' : '#ffffff'}
                  strokeWidth={isPathHighlighted ? 4 : isSelected ? 3 : 2}
                  filter={`url(#${nodeShadowId})`}
                  opacity={mutedByPath ? 0.3 : isPathHighlighted || isRelatedToSelection ? 1 : 0.72}
                />
                <circle
                  cx={node.x}
                  cy={node.y}
                  r={Math.max(6, radius * 0.34)}
                  fill="rgba(255,255,255,0.16)"
                  stroke="rgba(255,255,255,0.5)"
                  strokeWidth="1"
                />
                {shouldShowNodeLabel && (
                  <text
                    x={node.x}
                    y={labelY}
                    textAnchor="middle"
                    className="fill-slate-900 text-[12px] font-semibold"
                    stroke="#ffffff"
                    strokeWidth="4"
                    paintOrder="stroke"
                  >
                    {truncateLabel(node.label, node.isFocus ? 28 : 22)}
                  </text>
                )}
                {shouldShowTypeLabel && (
                  <g transform={`translate(${node.x}, ${typeY})`}>
                    <rect x={-38} y={-10} width={76} height={20} rx={6} fill="rgba(255,255,255,0.95)" stroke="#e5e7eb" />
                    <text x="0" y="4" textAnchor="middle" fontFamily="var(--cg-font-mono)" className="fill-slate-500 text-[9px] font-semibold uppercase tracking-[0.12em]">
                      {truncateLabel(formatTypeLabel(node.type), 12)}
                    </text>
                  </g>
                )}
              </g>
            );
          })}
        </svg>
      </div>

      {!compact && (
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-wrap gap-2">
            {Object.entries(DOMAIN_COLORS).map(([domain, color]) => (
              <div key={domain} className="inline-flex items-center gap-1.5 rounded-md border border-hairline bg-white px-2 py-1 text-[11px] font-medium text-ink-steel shadow-sm">
                <span className="h-2 w-2 rounded-full" style={{ backgroundColor: color }} />
                <span className="capitalize">{domain}</span>
              </div>
            ))}
          </div>
          <div className="flex items-center gap-2 font-mono text-[11px] text-ink-steel">
            <span>confidence</span>
            <span className="inline-flex items-center gap-1">
              <span className="h-[2px] w-3 rounded-full" style={{ backgroundColor: CONF_LOW }} />
              <span>low</span>
            </span>
            <span className="inline-flex items-center gap-1">
              <span className="h-[2px] w-4 rounded-full" style={{ backgroundColor: CONF_MID }} />
              <span>mid</span>
            </span>
            <span className="inline-flex items-center gap-1">
              <span className="h-[2px] w-5 rounded-full" style={{ backgroundColor: CONF_HIGH }} />
              <span>high</span>
            </span>
          </div>
        </div>
      )}
    </motion.div>
  );
};

export default KnowledgeGraphView;
