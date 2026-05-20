import networkx as nx
import json
from typing import List, Dict, Any, Optional
from collections import defaultdict
from causal_extractor import CausalRelationship
import re
from normalize import normalize_term, slugify, similar
from merge_utils import NodeStore
from knowledge_graph_builder_enhanced import KnowledgeGraphBuilderEnhanced

class KnowledgeGraphBuilder:
    def __init__(self):
        self.documents = {}
        self.graphs = {}
        self.node_store = NodeStore()
        
    def _normalize_node_name(self, name: str) -> str:
        """
        Enhanced node name normalization using advanced text processing
        """
        if not name or not name.strip():
            return "unknown"
        
        # Use enhanced normalization
        normalized = normalize_term(name)
        if not normalized:
            normalized = name.strip()
        
        # Create consistent ID
        slug = slugify(normalized)
        
        return slug
    
    def _merge_similar_nodes(self, graph: nx.DiGraph, similarity_threshold: float = 0.8) -> nx.DiGraph:
        """
        Merge similar nodes to reduce redundancy and improve graph quality
        """
        # Get all node labels
        node_labels = list(graph.nodes())
        
        # Use NodeStore for intelligent merging
        for i, label1 in enumerate(node_labels):
            for j, label2 in enumerate(node_labels[i+1:], i+1):
                if similar(label1, label2, similarity_threshold):
                    # Merge nodes
                    self._merge_nodes_in_graph(graph, label1, label2)
        
        return graph
    
    def _merge_nodes_in_graph(self, graph: nx.DiGraph, node1: str, node2: str):
        """
        Merge two nodes in the graph
        """
        if node1 == node2:
            return
            
        # Get all edges from node2
        edges_to_add = []
        for pred in graph.predecessors(node2):
            edges_to_add.append((pred, node1, graph.edges[pred, node2]))
        
        for succ in graph.successors(node2):
            edges_to_add.append((node1, succ, graph.edges[node2, succ]))
        
        # Add edges to node1
        for source, target, edge_data in edges_to_add:
            if not graph.has_edge(source, target):
                graph.add_edge(source, target, **edge_data)
            else:
                # Merge edge attributes
                existing_edge = graph.edges[source, target]
                merged_edge = self._merge_edge_attributes(existing_edge, edge_data)
                graph.edges[source, target].update(merged_edge)
        
        # Remove node2
        graph.remove_node(node2)
    
    def _merge_edge_attributes(self, edge1: Dict, edge2: Dict) -> Dict:
        """
        Merge edge attributes
        """
        merged = edge1.copy()
        
        # Merge confidence
        if 'confidence' in edge1 and 'confidence' in edge2:
            merged['confidence'] = (edge1['confidence'] + edge2['confidence']) / 2
        
        # Merge evidence
        if 'evidence' in edge1 and 'evidence' in edge2:
            evidence1 = edge1['evidence'] if isinstance(edge1['evidence'], list) else [edge1['evidence']]
            evidence2 = edge2['evidence'] if isinstance(edge2['evidence'], list) else [edge2['evidence']]
            merged['evidence'] = evidence1 + evidence2
        
        # Increment count
        merged['count'] = edge1.get('count', 1) + edge2.get('count', 1)
        
        return merged
    
    def build_graph(self, relationships: List[CausalRelationship], domain: str) -> Dict[str, Any]:
        """
        Build knowledge graph from causal relationships
        """
        graph = nx.DiGraph()
        
        # Add nodes and edges
        for rel in relationships:
            # Normalize node names
            cause_id = self._normalize_node_name(rel.cause)
            effect_id = self._normalize_node_name(rel.effect)
            
            # Add nodes
            if not graph.has_node(cause_id):
                graph.add_node(cause_id, 
                             label=rel.cause,
                             domain=domain,
                             type="concept",
                             confidence=rel.confidence,
                             aliases=[rel.cause])
            
            if not graph.has_node(effect_id):
                graph.add_node(effect_id,
                             label=rel.effect,
                             domain=domain,
                             type="concept", 
                             confidence=rel.confidence,
                             aliases=[rel.effect])
            
            # Add edges
            edge_data = {
                'relationship_type': rel.relationship_type,
                'confidence': rel.confidence,
                'evidence': rel.evidence,
                'domain': domain,
                'count': 1
            }
            
            # Add character span information
            if rel.cause_char_span:
                edge_data['cause_char_span'] = rel.cause_char_span
            if rel.effect_char_span:
                edge_data['effect_char_span'] = rel.effect_char_span
            
            graph.add_edge(cause_id, effect_id, **edge_data)
        
        # Merge similar nodes to improve graph quality
        graph = self._merge_similar_nodes(graph, similarity_threshold=0.8)
        
        # Convert to serializable format
        return self._graph_to_dict(graph)
    
    def build_enhanced_graph(self, relationships: List[CausalRelationship], domain: str) -> Dict[str, Any]:
        """
        Build a higher quality knowledge graph using the enhanced builder
        """
        # Use enhanced builder
        enhanced_builder = KnowledgeGraphBuilderEnhanced(sim_threshold=0.8)
        
        # Add all relationships
        for rel in relationships:
            enhanced_builder.add_relation(
                cause=rel.cause,
                effect=rel.effect,
                predicate=rel.relationship_type,
                confidence=rel.confidence,
                evidence=rel.evidence
            )
        
        # Build enhanced graph
        enhanced_graph = enhanced_builder.build()
        
        # Convert to standard format
        nodes = []
        for node in enhanced_graph.nodes:
            nodes.append({
                "id": node["id"],
                "label": node["label"],
                "domain": domain,
                "type": "concept",
                "confidence": node.get("confidence", 0.8),
                "aliases": node["aliases"]
            })
        
        edges = []
        for edge in enhanced_graph.edges:
            edge_data = {
                "source": edge["source"],
                "target": edge["target"],
                "relationship_type": edge["predicate"],
                "confidence": edge["weight"],
                "evidence": edge["evidence"][0] if edge["evidence"] else "",
                "domain": domain,
                "count": edge["count"]
            }
            
            # Add character span information
            if "cause_char_span" in edge:
                edge_data["cause_char_span"] = edge["cause_char_span"]
            if "effect_char_span" in edge:
                edge_data["effect_char_span"] = edge["effect_char_span"]
            
            edges.append(edge_data)
        
        return {
            "nodes": nodes,
            "edges": edges,
            "metadata": {
                "node_count": len(nodes),
                "edge_count": len(edges),
                "is_directed": True,
                "is_acyclic": True,  # Simplified handling
                "enhanced": True,
                "domain": domain,
                "relationship_types": list(set(edge["relationship_type"] for edge in edges)),
                "confidence_range": {
                    "min": min(edge["confidence"] for edge in edges) if edges else 0,
                    "max": max(edge["confidence"] for edge in edges) if edges else 0,
                    "mean": sum(edge["confidence"] for edge in edges) / len(edges) if edges else 0
                }
            }
        }
    
    def _check_acyclic(self, graph) -> bool:
        """
        Check if the graph is a directed acyclic graph
        """
        try:
            # Attempt topological sort
            list(nx.topological_sort(graph))
            return True
        except nx.NetworkXError:
            return False
    
    def _graph_to_dict(self, graph: nx.DiGraph) -> Dict[str, Any]:
        """
        Convert NetworkX graph to a serializable dictionary format
        """
        nodes = []
        for node_id, node_data in graph.nodes(data=True):
            node_info = {
                "id": node_id,
                "label": node_data.get("label", node_id),
                "domain": node_data.get("domain", "general"),
                "type": node_data.get("type", "concept"),
                "confidence": node_data.get("confidence", 0.5)
            }
            
            # Add aliases
            if "aliases" in node_data:
                node_info["aliases"] = node_data["aliases"]
            
            nodes.append(node_info)
        
        edges = []
        for source, target, edge_data in graph.edges(data=True):
            edge_info = {
                "source": source,
                "target": target,
                "relationship_type": edge_data.get("relationship_type", "causes"),
                "confidence": edge_data.get("confidence", 0.5),
                "evidence": edge_data.get("evidence", ""),
                "domain": edge_data.get("domain", "general"),
                "count": edge_data.get("count", 1)
            }
            
            # Add character span information
            if "cause_char_span" in edge_data:
                edge_info["cause_char_span"] = edge_data["cause_char_span"]
            if "effect_char_span" in edge_data:
                edge_info["effect_char_span"] = edge_data["effect_char_span"]
            
            edges.append(edge_info)
        
        return {
            "nodes": nodes,
            "edges": edges,
            "metadata": {
                "node_count": len(nodes),
                "edge_count": len(edges),
                "is_directed": True,
                "is_acyclic": self._check_acyclic(graph),
                "enhanced": False,
                "domain": nodes[0]["domain"] if nodes else "general"
            }
        }
    
    def get_graph_statistics(self, graph_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get graph statistics
        """
        nodes = graph_data.get("nodes", [])
        edges = graph_data.get("edges", [])
        
        # Relationship type distribution
        rel_types = {}
        for edge in edges:
            rel_type = edge.get("relationship_type", "causes")
            rel_types[rel_type] = rel_types.get(rel_type, 0) + 1
        
        # Confidence distribution
        confidences = [edge.get("confidence", 0.5) for edge in edges]
        
        # Evidence length distribution
        evidence_lengths = [len(edge.get("evidence", "")) for edge in edges]
        
        return {
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "relationship_types": rel_types,
            "confidence_stats": {
                "min": min(confidences) if confidences else 0,
                "max": max(confidences) if confidences else 0,
                "mean": sum(confidences) / len(confidences) if confidences else 0,
                "std": self._calculate_std(confidences)
            },
            "evidence_stats": {
                "min": min(evidence_lengths) if evidence_lengths else 0,
                "max": max(evidence_lengths) if evidence_lengths else 0,
                "mean": sum(evidence_lengths) / len(evidence_lengths) if evidence_lengths else 0
            }
        }
    
    def _calculate_std(self, values: List[float]) -> float:
        """
        Calculate standard deviation
        """
        if len(values) < 2:
            return 0.0
        
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
        return variance ** 0.5
    
    def query_graph(self, question: str, graph_id: str) -> str:
        """
        Query the knowledge graph with natural language questions
        """
        if graph_id not in self.documents:
            return "Graph not found."
        
        graph_data = self.documents[graph_id]["graph"]
        relationships = self.documents[graph_id]["relationships"]
        
        # Simple keyword-based querying for MVP
        question_lower = question.lower()
        
        if "what causes" in question_lower or "what leads to" in question_lower:
            # Extract the effect from the question
            effect = self._extract_entity_from_question(question, "causes")
            return self._find_causes(effect, relationships)
            
        elif "what happens if" in question_lower or "what results from" in question_lower:
            # Extract the cause from the question
            cause = self._extract_entity_from_question(question, "happens")
            return self._find_effects(cause, relationships)
            
        elif "how does" in question_lower and "affect" in question_lower:
            # Extract the cause and effect
            cause = self._extract_entity_from_question(question, "does")
            return self._find_relationship(cause, relationships)
            
        elif "what prevents" in question_lower:
            # Find preventive relationships
            effect = self._extract_entity_from_question(question, "prevents")
            return self._find_preventive_factors(effect, relationships)
            
        else:
            # General search
            return self._general_search(question, relationships)
    
    def _extract_entity_from_question(self, question: str, keyword: str) -> str:
        """
        Extract entity names from questions
        """
        # Simple extraction - in production, use more sophisticated NLP
        parts = question.split(keyword)
        if len(parts) > 1:
            entity = parts[1].strip()
            # Remove question words and punctuation
            entity = re.sub(r'^(what|how|why|when|where)\s+', '', entity)
            entity = re.sub(r'[?.,!]', '', entity)
            return entity
        return ""
    
    def _find_causes(self, effect: str, relationships: List[CausalRelationship]) -> str:
        """
        Find what causes a specific effect
        """
        causes = []
        for rel in relationships:
            if effect.lower() in rel.effect.lower() or rel.effect.lower() in effect.lower():
                causes.append(f"• {rel.cause} ({rel.relationship_type} {rel.effect})")
        
        if causes:
            return f"Factors that cause {effect}:\n" + "\n".join(causes)
        else:
            return f"No direct causes found for {effect}."
    
    def _find_effects(self, cause: str, relationships: List[CausalRelationship]) -> str:
        """
        Find what results from a specific cause
        """
        effects = []
        for rel in relationships:
            if cause.lower() in rel.cause.lower() or rel.cause.lower() in cause.lower():
                effects.append(f"• {rel.cause} {rel.relationship_type} {rel.effect}")
        
        if effects:
            return f"Effects of {cause}:\n" + "\n".join(effects)
        else:
            return f"No direct effects found for {cause}."
    
    def _find_relationship(self, entity: str, relationships: List[CausalRelationship]) -> str:
        """
        Find relationships involving a specific entity
        """
        related = []
        for rel in relationships:
            if (entity.lower() in rel.cause.lower() or 
                entity.lower() in rel.effect.lower() or
                rel.cause.lower() in entity.lower() or
                rel.effect.lower() in entity.lower()):
                related.append(f"• {rel.cause} {rel.relationship_type} {rel.effect}")
        
        if related:
            return f"Relationships involving {entity}:\n" + "\n".join(related)
        else:
            return f"No relationships found for {entity}."
    
    def _find_preventive_factors(self, effect: str, relationships: List[CausalRelationship]) -> str:
        """
        Find factors that prevent a specific effect
        """
        preventives = []
        for rel in relationships:
            if (effect.lower() in rel.effect.lower() or 
                rel.effect.lower() in effect.lower()) and "prevents" in rel.relationship_type.lower():
                preventives.append(f"• {rel.cause} prevents {rel.effect}")
        
        if preventives:
            return f"Factors that prevent {effect}:\n" + "\n".join(preventives)
        else:
            return f"No preventive factors found for {effect}."
    
    def _general_search(self, question: str, relationships: List[CausalRelationship]) -> str:
        """
        General search through relationships
        """
        # Extract key terms from the question
        words = re.findall(r'\b\w+\b', question.lower())
        
        relevant = []
        for rel in relationships:
            # Check if any question words appear in the relationship
            for word in words:
                if (word in rel.cause.lower() or 
                    word in rel.effect.lower() or
                    word in rel.relationship_type.lower()):
                    relevant.append(f"• {rel.cause} {rel.relationship_type} {rel.effect}")
                    break
        
        if relevant:
            return f"Relevant relationships:\n" + "\n".join(relevant[:5])  # Limit to 5 results
        else:
            return "No relevant relationships found. Try rephrasing your question."
    
    def merge_graphs(self, graph_ids: List[str]) -> Dict[str, Any]:
        """
        Merge multiple graphs into a combined knowledge graph
        """
        combined_graph = nx.DiGraph()
        
        for graph_id in graph_ids:
            if graph_id in self.documents:
                graph_data = self.documents[graph_id]["graph"]
                
                # Add nodes
                for node in graph_data["nodes"]:
                    combined_graph.add_node(node["id"], **node)
                
                # Add edges
                for edge in graph_data["edges"]:
                    combined_graph.add_edge(edge["source"], edge["target"], **edge)
        
        return self._graph_to_dict(combined_graph)
    
    def export_graph(self, graph_id: str, format: str = "json") -> str:
        """
        Export graph in various formats
        """
        if graph_id not in self.documents:
            return "Graph not found."
        
        graph_data = self.documents[graph_id]["graph"]
        
        if format == "json":
            return json.dumps(graph_data, indent=2)
        elif format == "gml":
            # Convert to GML format for external tools
            graph = nx.DiGraph()
            
            for node in graph_data["nodes"]:
                graph.add_node(node["id"], **{k: v for k, v in node.items() if k != "id"})
            
            for edge in graph_data["edges"]:
                graph.add_edge(edge["source"], edge["target"], **{k: v for k, v in edge.items() if k not in ["source", "target"]})
            
            return "\n".join(nx.generate_gml(graph))
        else:
            return "Unsupported format. Use 'json' or 'gml'."

# Example usage
if __name__ == "__main__":
    builder = KnowledgeGraphBuilder()
    
    # Test with sample relationships
    from causal_extractor import CausalRelationship
    
    sample_relationships = [
        CausalRelationship("smoking", "lung cancer", 0.9, "Research shows...", "healthcare"),
        CausalRelationship("exercise", "heart health", 0.8, "Studies indicate...", "healthcare"),
        CausalRelationship("interest rates", "stock prices", 0.7, "Market analysis...", "financial")
    ]
    
    graph = builder.build_graph(sample_relationships, "mixed")
    print(f"Built graph with {len(graph['nodes'])} nodes and {len(graph['edges'])} edges")
    
    # Test querying
    answer = builder.query_graph("What causes lung cancer?", "test")
    print(f"Query result: {answer}")
