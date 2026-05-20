import plotly.graph_objects as go
import plotly.express as px
import networkx as nx
import json
from typing import Dict, Any, List, Optional
import pandas as pd

class GraphVisualizer:
    def __init__(self):
        self.color_schemes = {
            "healthcare": {
                "primary": "#10B981",  # Green
                "secondary": "#059669",
                "accent": "#34D399"
            },
            "financial": {
                "primary": "#3B82F6",  # Blue
                "secondary": "#2563EB",
                "accent": "#60A5FA"
            },
            "general": {
                "primary": "#8B5CF6",  # Purple
                "secondary": "#7C3AED",
                "accent": "#A78BFA"
            }
        }
        
        self.relationship_colors = {
            "causes": "#EF4444",      # Red
            "prevents": "#10B981",    # Green
            "increases_risk": "#F59E0B",  # Yellow
            "influences": "#8B5CF6",  # Purple
            "affects": "#06B6D4"      # Cyan
        }
    
    def create_interactive_graph(self, graph_data: Dict[str, Any], 
                                domain: str = "general") -> Dict[str, Any]:
        """
        Create an interactive Plotly visualization of the knowledge graph
        """
        try:
            # Extract nodes and edges
            nodes = graph_data.get("nodes", [])
            edges = graph_data.get("edges", [])
            
            if not nodes:
                return {"error": "No nodes found in graph data"}
            
            # Create NetworkX graph for layout calculation
            G = nx.DiGraph()
            
            # Add nodes and edges
            for node in nodes:
                G.add_node(node["id"], **node)
            
            for edge in edges:
                G.add_edge(edge["source"], edge["target"], **edge)
            
            # Calculate layout
            pos = nx.spring_layout(G, k=1, iterations=50)
            
            # Prepare node positions
            node_x = []
            node_y = []
            node_text = []
            node_colors = []
            node_sizes = []
            
            for node in nodes:
                node_id = node["id"]
                if node_id in pos:
                    x, y = pos[node_id]
                    node_x.append(x)
                    node_y.append(y)
                    node_text.append(f"{node['label']}<br>Domain: {node['domain']}<br>Confidence: {node['confidence']:.2f}")
                    
                    # Color based on domain
                    domain_colors = self.color_schemes.get(node["domain"], self.color_schemes["general"])
                    node_colors.append(domain_colors["primary"])
                    
                    # Size based on confidence
                    node_sizes.append(max(10, node["confidence"] * 30))
            
            # Prepare edge positions
            edge_x = []
            edge_y = []
            edge_colors = []
            edge_text = []
            
            for edge in edges:
                source_id = edge["source"]
                target_id = edge["target"]
                
                if source_id in pos and target_id in pos:
                    x0, y0 = pos[source_id]
                    x1, y1 = pos[target_id]
                    
                    edge_x.extend([x0, x1, None])
                    edge_y.extend([y0, y1, None])
                    
                    # Color based on relationship type
                    rel_color = self.relationship_colors.get(
                        edge["relationship_type"], 
                        self.relationship_colors["causes"]
                    )
                    edge_colors.extend([rel_color, rel_color, None])
                    
                    edge_text.extend([
                        f"{edge['relationship_type']}<br>Confidence: {edge['confidence']:.2f}<br>Domain: {edge['domain']}",
                        f"{edge['relationship_type']}<br>Confidence: {edge['confidence']:.2f}<br>Domain: {edge['domain']}",
                        ""
                    ])
            
            # Create edge trace
            edge_trace = go.Scatter(
                x=edge_x, y=edge_y,
                line=dict(width=2, color=edge_colors),
                hoverinfo='text',
                text=edge_text,
                mode='lines',
                name='Relationships'
            )
            
            # Create node trace
            node_trace = go.Scatter(
                x=node_x, y=node_y,
                mode='markers+text',
                hoverinfo='text',
                text=[node["label"] for node in nodes],
                textposition="top center",
                marker=dict(
                    size=node_sizes,
                    color=node_colors,
                    line=dict(width=2, color='white'),
                    showscale=False
                ),
                name='Concepts'
            )
            
            # Create layout
            layout = go.Layout(
                title=f'Causal Knowledge Graph - {domain.title()} Domain',
                showlegend=True,
                hovermode='closest',
                margin=dict(b=20, l=5, r=5, t=40),
                annotations=[
                    dict(
                        text="Drag nodes to reposition<br>Hover for details",
                        showarrow=False,
                        xref="paper", yref="paper",
                        x=0.005, y=-0.002,
                        xanchor='left', yanchor='bottom',
                        font=dict(size=10)
                    )
                ],
                xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                plot_bgcolor='white',
                height=600
            )
            
            # Create figure
            fig = go.Figure(data=[edge_trace, node_trace], layout=layout)
            
            # Convert to JSON for frontend
            graph_json = fig.to_json()
            
            return {
                "success": True,
                "graph_json": graph_json,
                "node_count": len(nodes),
                "edge_count": len(edges),
                "domain": domain
            }
            
        except Exception as e:
            return {"error": f"Error creating visualization: {str(e)}"}
    
    def create_network_graph(self, graph_data: Dict[str, Any], 
                            domain: str = "general") -> Dict[str, Any]:
        """
        Create a network-style graph visualization
        """
        try:
            nodes = graph_data.get("nodes", [])
            edges = graph_data.get("edges", [])
            
            if not nodes:
                return {"error": "No nodes found in graph data"}
            
            # Create NetworkX graph
            G = nx.DiGraph()
            
            for node in nodes:
                G.add_node(node["id"], **node)
            
            for edge in edges:
                G.add_edge(edge["source"], edge["target"], **edge)
            
            # Calculate layout
            pos = nx.kamada_kawai_layout(G)
            
            # Prepare data for visualization
            node_positions = {node_id: pos[node_id] for node_id in pos}
            
            # Create node data
            node_data = []
            for node in nodes:
                if node["id"] in node_positions:
                    x, y = node_positions[node["id"]]
                    node_data.append({
                        "id": node["id"],
                        "label": node["label"],
                        "x": float(x),
                        "y": float(y),
                        "domain": node["domain"],
                        "confidence": node["confidence"],
                        "color": self.color_schemes.get(node["domain"], self.color_schemes["general"])["primary"]
                    })
            
            # Create edge data
            edge_data = []
            for edge in edges:
                if edge["source"] in node_positions and edge["target"] in node_positions:
                    edge_data.append({
                        "source": edge["source"],
                        "target": edge["target"],
                        "relationship_type": edge["relationship_type"],
                        "confidence": edge["confidence"],
                        "color": self.relationship_colors.get(edge["relationship_type"], "#666666")
                    })
            
            return {
                "success": True,
                "nodes": node_data,
                "edges": edge_data,
                "layout": "kamada_kawai",
                "domain": domain
            }
            
        except Exception as e:
            return {"error": f"Error creating network graph: {str(e)}"}
    
    def create_statistics_charts(self, graph_data: Dict[str, Any], 
                                domain: str = "general") -> Dict[str, Any]:
        """
        Create statistical charts for the knowledge graph
        """
        try:
            nodes = graph_data.get("nodes", [])
            edges = graph_data.get("edges", [])
            
            if not nodes:
                return {"error": "No nodes found in graph data"}
            
            # Domain distribution
            domain_counts = {}
            for node in nodes:
                node_domain = node["domain"]
                domain_counts[node_domain] = domain_counts.get(node_domain, 0) + 1
            
            domain_fig = px.pie(
                values=list(domain_counts.values()),
                names=list(domain_counts.keys()),
                title="Concept Distribution by Domain",
                color_discrete_map=self.color_schemes
            )
            
            # Confidence distribution
            confidence_ranges = {"High (0.8-1.0)": 0, "Medium (0.5-0.8)": 0, "Low (0.0-0.5)": 0}
            for node in nodes:
                conf = node["confidence"]
                if conf >= 0.8:
                    confidence_ranges["High (0.8-1.0)"] += 1
                elif conf >= 0.5:
                    confidence_ranges["Medium (0.5-0.8)"] += 1
                else:
                    confidence_ranges["Low (0.0-0.5)"] += 1
            
            conf_fig = px.bar(
                x=list(confidence_ranges.keys()),
                y=list(confidence_ranges.values()),
                title="Confidence Distribution",
                color=list(confidence_ranges.values()),
                color_continuous_scale="Viridis"
            )
            
            # Relationship types
            rel_counts = {}
            for edge in edges:
                rel_type = edge["relationship_type"]
                rel_counts[rel_type] = rel_counts.get(rel_type, 0) + 1
            
            rel_fig = px.bar(
                x=list(rel_counts.keys()),
                y=list(rel_counts.values()),
                title="Relationship Types Distribution",
                color=list(rel_counts.values()),
                color_continuous_scale="Plasma"
            )
            
            return {
                "success": True,
                "domain_chart": domain_fig.to_json(),
                "confidence_chart": conf_fig.to_json(),
                "relationship_chart": rel_fig.to_json(),
                "statistics": {
                    "total_nodes": len(nodes),
                    "total_edges": len(edges),
                    "domain_distribution": domain_counts,
                    "confidence_distribution": confidence_ranges,
                    "relationship_types": rel_counts
                }
            }
            
        except Exception as e:
            return {"error": f"Error creating statistics charts: {str(e)}"}
    
    def export_graph_data(self, graph_data: Dict[str, Any], 
                          format: str = "json") -> str:
        """
        Export graph data in various formats
        """
        try:
            if format == "json":
                return json.dumps(graph_data, indent=2)
            
            elif format == "csv":
                # Export nodes
                nodes_df = pd.DataFrame(graph_data.get("nodes", []))
                edges_df = pd.DataFrame(graph_data.get("edges", []))
                
                csv_data = {
                    "nodes": nodes_df.to_csv(index=False),
                    "edges": edges_df.to_csv(index=False)
                }
                
                return json.dumps(csv_data)
            
            elif format == "graphml":
                # Convert to GraphML format
                G = nx.DiGraph()
                
                for node in graph_data.get("nodes", []):
                    G.add_node(node["id"], **{k: v for k, v in node.items() if k != "id"})
                
                for edge in graph_data.get("edges", []):
                    G.add_edge(edge["source"], edge["target"], **{k: v for k, v in edge.items() if k not in ["source", "target"]})
                
                return "\n".join(nx.generate_graphml(G))
            
            else:
                return "Unsupported format. Use 'json', 'csv', or 'graphml'."
                
        except Exception as e:
            return f"Error exporting graph: {str(e)}"
    
    def create_simple_visualization(self, graph_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a simple text-based visualization for debugging
        """
        try:
            nodes = graph_data.get("nodes", [])
            edges = graph_data.get("edges", [])
            
            # Create simple text representation
            visualization = []
            visualization.append("Causal Knowledge Graph")
            visualization.append("=" * 50)
            visualization.append("")
            
            # Group edges by source
            edge_groups = {}
            for edge in edges:
                source = edge["source"]
                if source not in edge_groups:
                    edge_groups[source] = []
                edge_groups[source].append(edge)
            
            # Display relationships
            for source, source_edges in edge_groups.items():
                source_label = next((n["label"] for n in nodes if n["id"] == source), source)
                visualization.append(f"[NODE] {source_label}")
                
                for edge in source_edges:
                    target_label = next((n["label"] for n in nodes if n["id"] == edge["target"]), edge["target"])
                    rel_type = edge["relationship_type"]
                    confidence = edge["confidence"]
                    
                    visualization.append(f"  └─ {rel_type} → {target_label} (confidence: {confidence:.2f})")
                
                visualization.append("")
            
            return {
                "success": True,
                "text_visualization": "\n".join(visualization),
                "node_count": len(nodes),
                "edge_count": len(edges)
            }
            
        except Exception as e:
            return {"error": f"Error creating simple visualization: {str(e)}"}

# Example usage
if __name__ == "__main__":
    visualizer = GraphVisualizer()
    
    # Sample graph data
    sample_graph = {
        "nodes": [
            {"id": "smoking", "label": "Smoking", "domain": "healthcare", "confidence": 0.9},
            {"id": "lung_cancer", "label": "Lung Cancer", "domain": "healthcare", "confidence": 0.9},
            {"id": "exercise", "label": "Exercise", "domain": "healthcare", "confidence": 0.8}
        ],
        "edges": [
            {"source": "smoking", "target": "lung_cancer", "relationship_type": "causes", "confidence": 0.9, "domain": "healthcare"},
            {"source": "exercise", "target": "lung_cancer", "relationship_type": "prevents", "confidence": 0.7, "domain": "healthcare"}
        ]
    }
    
    # Test visualization
    result = visualizer.create_interactive_graph(sample_graph, "healthcare")
    print(f"Visualization created: {result.get('success', False)}")
    
    # Test simple visualization
    simple_result = visualizer.create_simple_visualization(sample_graph)
    if simple_result.get("success"):
        print("\nSimple visualization:")
        print(simple_result["text_visualization"])
