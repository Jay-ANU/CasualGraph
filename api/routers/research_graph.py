"""Read existing research graphs without reopening the former unscoped public API."""
from __future__ import annotations
import json
from pathlib import Path
from fastapi import APIRouter, Depends, Query
from api.deps import get_current_user
from configs.settings import GRAPH_DIR
from services import document_access as access

router = APIRouter(prefix='/graph', tags=['research-graph'])


def graph_for(user: dict | None, limit: int, edge_limit: int) -> dict:
    nodes, edges, warnings = [], [], []
    shared = access._MatterDocumentIndex(user) if user else None
    root = Path(GRAPH_DIR).resolve()
    for entry in access._collect_document_entries():
        public = access._is_global_entry(entry)
        if not public and (not user or not access._can_access_entry(user, entry, matter_document_ids=shared)):
            continue
        path = str((entry.get('paths') or {}).get('graph') or '')
        if not path:
            continue
        candidate = Path(path).resolve()
        if not candidate.is_relative_to(root) or candidate.suffix != '.json':
            continue
        try:
            if candidate.stat().st_size > 20 * 1024 * 1024:
                warnings.append('An available graph exceeds the display size limit.')
                continue
            data = json.loads(candidate.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            warnings.append('An available graph could not be read.')
            continue
        if not isinstance(data, dict):
            continue
        docid = str(entry['document_id'])
        ids = set()
        for node in data.get('nodes', []):
            if not isinstance(node, dict) or len(nodes) >= limit:
                continue
            key = str(node.get('id') or '')
            if not key or key in ids:
                continue
            ids.add(key)
            nodes.append({'id': f'{docid}:{key}', 'label': str(node.get('label') or node.get('name') or key),
                          'type': str(node.get('type') or 'Entity'), 'domain': str(node.get('domain') or 'general'),
                          'description': str(node.get('description') or '')})
        for edge in data.get('edges', data.get('links', [])):
            if not isinstance(edge, dict) or len(edges) >= edge_limit:
                continue
            source, target = str(edge.get('source') or ''), str(edge.get('target') or '')
            if source in ids and target in ids:
                edges.append({'source': f'{docid}:{source}', 'target': f'{docid}:{target}',
                              'relationship_type': str(edge.get('relationship_type') or edge.get('relation') or 'RELATED_TO'),
                              'evidence': str(edge.get('evidence') or ''), 'documentId': docid})
        if len(nodes) >= limit:
            break
    return {'nodes': nodes, 'edges': edges, 'metadata': {'node_count': len(nodes), 'edge_count': len(edges),
            'is_directed': True, 'is_acyclic': False}, 'warnings': sorted(set(warnings)),
            'notice': 'Existing research graphs only. Private contract-review data is not indexed here.'}


@router.get('/public')
def public_graph(limit: int = Query(1500, ge=1, le=25000), edge_limit: int = Query(3000, ge=1, le=30000)):
    return graph_for(None, limit, edge_limit)


@router.get('/workspace')
def workspace_graph(limit: int = Query(1500, ge=1, le=25000), edge_limit: int = Query(3000, ge=1, le=30000), user: dict = Depends(get_current_user)):
    return graph_for(user, limit, edge_limit)
