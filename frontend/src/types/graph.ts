export interface GraphNode {
  id: string;
  label: string;
  domain: string;
  type: string;
  confidence: number;
  description?: string;
  company?: string;
  year?: string;
  normalizedName?: string;
  metadata?: Record<string, unknown>;
}

export interface GraphEdge {
  source: string;
  target: string;
  relationship_type: string;
  confidence: number;
  evidence: string;
  domain: string;
  relationship_action?: string;
  relationship_nature?: string;
  documentId?: string;
  chunkId?: string;
  metadata?: Record<string, unknown>;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  metadata: {
    node_count: number;
    edge_count: number;
    is_directed: boolean;
    is_acyclic: boolean;
  };
}

export interface GraphHighlightPath {
  nodes: string[];
  edges: Array<[string, string]>;
}
