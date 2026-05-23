"""Flask API server for ESG Knowledge Graph visualization.

Supports two modes:
- Neo4j mode: when NEO4J_URI is configured in .env
- File mode: reads directly from normalized JSONL files (no database needed)
"""

import json
import sys
from pathlib import Path
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

app = Flask(__name__)
CORS(app)

_PROJECT_ROOT = Path(__file__).parent.parent
_VALID_DOMAINS = set(config.ESG_DOMAINS)
_VALID_TYPES = set(config.ENTITY_TYPES)
_VALID_REL_TYPES = set(config.RELATIONSHIP_TYPES)


def _candidate_data_dirs() -> list[Path]:
    """Return candidate data directories in priority order.

    Priority:
    1. data/normalized/ (fresh local outputs)
    2. Any committed sample outputs under data/extracted/*/
    """
    normalized = _PROJECT_ROOT / "data" / "normalized"
    extracted_root = _PROJECT_ROOT / "data" / "extracted"

    candidates = [normalized]
    if extracted_root.exists():
        extracted_dirs = sorted(
            [d for d in extracted_root.iterdir() if d.is_dir()],
            key=lambda p: p.name,
            reverse=True,
        )
        candidates.extend(extracted_dirs)

    return candidates


def _get_data_dir() -> Path:
    for d in _candidate_data_dirs():
        if d.exists() and any(d.glob("*.jsonl")):
            return d
    return _PROJECT_ROOT / "data" / "normalized"


DATA_DIR = _get_data_dir()

# ---------- File-based backend (no Neo4j needed) ----------

_cache = {"mtime": 0, "triples": []}

# Louvain results cache: (domain, companies_key, years_key) → _build_louvain() result
# Invalidated whenever the underlying triples cache reloads (data files change).
_louvain_cache: dict = {}
_louvain_cache_generation: int = 0  # bumped on every triple-cache reload

# Ontology-concept grouping cache (same key schema as _louvain_cache)
_ontology_cache: dict = {}


def _sanitize_record(record: dict) -> dict | None:
    """Skip malformed or schema-drifted records when reading JSONL files."""
    e1 = record.get("entity_1")
    e2 = record.get("entity_2")
    rel = record.get("relationship_type")

    if not isinstance(e1, dict) or not isinstance(e2, dict):
        return None
    if rel not in _VALID_REL_TYPES:
        return None

    for entity in (e1, e2):
        domain = (entity.get("esg_domain") or "").lower()
        etype = entity.get("type") or ""
        if domain not in _VALID_DOMAINS:
            return None
        if etype not in _VALID_TYPES:
            return None
        entity["esg_domain"] = domain

    return record


def _load_all_triples() -> list[dict]:
    """Load all normalized JSONL files with mtime-based caching."""
    data_dir = _get_data_dir()
    normalized_paths = sorted(data_dir.glob("*_normalized.jsonl"))
    paths = normalized_paths or sorted(data_dir.glob("*.jsonl"))
    if not paths:
        return []
    latest = max(p.stat().st_mtime for p in paths)
    if latest > _cache["mtime"]:
        global _louvain_cache, _louvain_cache_generation, _ontology_cache
        triples = []
        for path in paths:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        record = json.loads(line)
                        record = _sanitize_record(record)
                        if record is not None:
                            triples.append(record)
        _cache["mtime"] = latest
        _cache["triples"] = triples
        _louvain_cache = {}          # invalidate on data reload
        _ontology_cache = {}
        _louvain_cache_generation += 1
    return _cache["triples"]


def _triples_to_graph(triples: list[dict], domains: list = None,
                      companies: list = None, years: list = None,
                      limit: int = 500) -> dict:
    """Convert triples to {nodes, edges} format for D3.js."""
    nodes_map = {}
    edges = []

    for triple in triples:
        e1 = triple["entity_1"]
        e2 = triple["entity_2"]

        # Infer company and year from triple ID (ESG_NVIDIA_2025_001)
        parts = triple["id"].split("_")
        company = parts[1] if len(parts) >= 3 else "Unknown"
        year = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else 0

        # Apply company/year filters (triple-level)
        if companies and company not in companies:
            continue
        if years and year not in years:
            continue

        e1_canon = e1.get("canonical_name", e1["normalized_name"])
        e2_canon = e2.get("canonical_name", e2["normalized_name"])
        e1_id = f"{company}_{year}_{e1_canon}"
        e2_id = f"{company}_{year}_{e2_canon}"

        # Apply domain filter (node-level): only add nodes whose domain matches
        e1_ok = not domains or e1["esg_domain"] in domains
        e2_ok = not domains or e2["esg_domain"] in domains

        if e1_ok and e1_id not in nodes_map:
            nodes_map[e1_id] = {
                "id": e1_id, "label": e1_canon, "text": e1["text"],
                "type": e1["type"], "esg_domain": e1["esg_domain"],
                "year": year, "company": company,
            }
        if e2_ok and e2_id not in nodes_map:
            nodes_map[e2_id] = {
                "id": e2_id, "label": e2_canon, "text": e2["text"],
                "type": e2["type"], "esg_domain": e2["esg_domain"],
                "year": year, "company": company,
            }

        # Only add edge if both nodes passed domain filter
        if not (e1_ok and e2_ok):
            continue

        edges.append({
            "id": triple["id"],
            "source": e1_id,
            "target": e2_id,
            "type": triple["relationship_type"],
            "action": triple["relationship_action"],
            "category": triple["relationship_category"],
            "nature": triple["relationship_nature"],
            "evidence": triple.get("evidence", ""),
            "direction": triple.get("direction", ""),
            "credibility_score": triple.get("credibility_score", 0),
            "sentiment": triple.get("sentiment", "neutral"),
        })

    # Apply limit
    nodes = list(nodes_map.values())[:limit]
    node_ids = {n["id"] for n in nodes}
    edges = [e for e in edges if e["source"] in node_ids and e["target"] in node_ids]

    return {"nodes": nodes, "edges": edges}


# ---------- Neo4j backend ----------

def _has_neo4j() -> bool:
    return bool(config.NEO4J_URI and config.NEO4J_PASSWORD)


def _get_driver():
    from neo4j import GraphDatabase
    return GraphDatabase.driver(
        config.NEO4J_URI, auth=(config.NEO4J_USER, config.NEO4J_PASSWORD)
    )


# ---------- Routes ----------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/graph")
def get_graph():
    years_raw = request.args.getlist("years")
    years = [int(y) for y in years_raw if y.isdigit()] or None
    companies = request.args.getlist("companies") or None
    domains = request.args.getlist("domains") or None
    limit = max(10, min(request.args.get("limit", 500, type=int), 5000))

    if _has_neo4j():
        driver = _get_driver()
        try:
            with driver.session() as session:
                conditions = []
                params = {"limit": limit}
                if years:
                    conditions.append("n.year IN $years")
                    params["years"] = years
                if companies:
                    conditions.append("n.company IN $companies")
                    params["companies"] = companies
                if domains:
                    conditions.append("n.esg_domain IN $domains")
                    params["domains"] = domains

                where = "WHERE " + " AND ".join(conditions) if conditions else ""
                node_query = f"""
                    MATCH (n:Entity) {where}
                    RETURN n.id AS id, n.name AS label, n.text AS text,
                           n.type AS type, n.esg_domain AS esg_domain,
                           n.year AS year, n.company AS company
                    LIMIT $limit
                """
                nodes = session.run(node_query, params).data()
                node_ids = [n["id"] for n in nodes]
                if not node_ids:
                    return jsonify({"nodes": [], "edges": []})

                # Note: conditions list contains only hardcoded strings, not user input
                edge_query = """
                    MATCH (n1:Entity)-[r:RELATIONSHIP]->(n2:Entity)
                    WHERE n1.id IN $node_ids AND n2.id IN $node_ids
                    RETURN r.id AS id, n1.id AS source, n2.id AS target,
                           r.type AS type, r.action AS action,
                           r.category AS category, r.nature AS nature,
                           r.evidence AS evidence, r.direction AS direction,
                           r.credibility_score AS credibility_score,
                           r.sentiment AS sentiment
                """
                edges = session.run(edge_query, node_ids=node_ids).data()
                return jsonify({"nodes": nodes, "edges": edges})
        finally:
            driver.close()
    else:
        # File-based mode
        triples = _load_all_triples()
        data = _triples_to_graph(triples, domains, companies, years, limit)
        return jsonify(data)


@app.route("/api/filters")
def get_filters():
    """Return all filter options + which ones are available for selected companies."""
    selected_companies = request.args.getlist("companies") or None

    triples = _load_all_triples()
    all_companies = set()
    all_years = set()
    all_domains = set()
    active_years = set()
    active_domains = set()

    for t in triples:
        parts = t["id"].split("_")
        company = parts[1] if len(parts) >= 3 else "Unknown"
        year = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else 0

        all_companies.add(company)
        if year:
            all_years.add(year)
        all_domains.add(t["entity_1"]["esg_domain"])
        all_domains.add(t["entity_2"]["esg_domain"])

        # Track which years/domains are available for selected companies
        if selected_companies and company in selected_companies:
            if year:
                active_years.add(year)
            active_domains.add(t["entity_1"]["esg_domain"])
            active_domains.add(t["entity_2"]["esg_domain"])

    return jsonify({
        "companies": sorted(all_companies),
        "years": sorted(all_years),
        "domains": sorted(all_domains),
        "active_years": sorted(active_years) if selected_companies else sorted(all_years),
        "active_domains": sorted(active_domains) if selected_companies else sorted(all_domains),
    })


@app.route("/api/stats")
def get_stats():
    if _has_neo4j():
        driver = _get_driver()
        try:
            with driver.session() as session:
                domain_counts = session.run(
                    "MATCH (n:Entity) RETURN n.esg_domain AS domain, count(*) AS cnt").data()
                type_counts = session.run(
                    "MATCH (n:Entity) RETURN n.type AS type, count(*) AS cnt ORDER BY cnt DESC").data()
                rel_counts = session.run(
                    "MATCH ()-[r:RELATIONSHIP]->() RETURN r.type AS type, count(*) AS cnt "
                    "ORDER BY cnt DESC LIMIT 10").data()
                return jsonify({
                    "by_domain": {r["domain"]: r["cnt"] for r in domain_counts},
                    "by_type": {r["type"]: r["cnt"] for r in type_counts},
                    "by_relationship": {r["type"]: r["cnt"] for r in rel_counts},
                })
        finally:
            driver.close()
    else:
        from collections import Counter
        triples = _load_all_triples()
        domain_cnt = Counter()
        type_cnt = Counter()
        rel_cnt = Counter()
        for t in triples:
            domain_cnt[t["entity_1"]["esg_domain"]] += 1
            domain_cnt[t["entity_2"]["esg_domain"]] += 1
            type_cnt[t["entity_1"]["type"]] += 1
            type_cnt[t["entity_2"]["type"]] += 1
            rel_cnt[t["relationship_type"]] += 1
        return jsonify({
            "by_domain": dict(domain_cnt),
            "by_type": dict(type_cnt),
            "by_relationship": dict(rel_cnt.most_common(10)),
        })


@app.route("/api/total_count")
def get_total_count():
    """Return total unique node count for dynamic slider max."""
    triples = _load_all_triples()
    node_ids = set()
    for t in triples:
        parts = t["id"].split("_")
        company = parts[1] if len(parts) >= 3 else "Unknown"
        year = parts[2] if len(parts) >= 3 else "0"
        e1 = t["entity_1"].get("canonical_name", t["entity_1"]["normalized_name"])
        e2 = t["entity_2"].get("canonical_name", t["entity_2"]["normalized_name"])
        node_ids.add(f"{company}_{year}_{e1}")
        node_ids.add(f"{company}_{year}_{e2}")
    return jsonify({"total_nodes": len(node_ids)})


@app.route("/api/cluster-graph")
def get_cluster_graph():
    """Return a high-level 4-cluster summary graph.

    Aggregates all triples into cluster-to-cluster edges:
    - Nodes: AI, Environmental, Social, Governance
    - Edges: weight = triple count, top_relations = most common rel types
    """
    companies = request.args.getlist("companies") or None
    years_raw = request.args.getlist("years")
    years = [int(y) for y in years_raw if y.isdigit()] or None
    domains = request.args.getlist("domains") or None

    triples = _load_all_triples()

    # Filter by company/year/domain
    filtered = []
    for t in triples:
        parts = t["id"].split("_")
        company = parts[1] if len(parts) >= 3 else "Unknown"
        year = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else 0
        if companies and company not in companies:
            continue
        if years and year not in years:
            continue
        # Domain filter: at least one entity must match
        if domains:
            d1 = t["entity_1"].get("esg_domain", "")
            d2 = t["entity_2"].get("esg_domain", "")
            if d1 not in domains and d2 not in domains:
                continue
        filtered.append(t)

    # Map domains to clusters
    CLUSTER_MAP = {
        "environmental": "Environmental",
        "social": "Social",
        "governance": "Governance",
        "ai": "AI",
    }
    CLUSTER_COLORS = {
        "Environmental": "#3fb950",
        "Social": "#58a6ff",
        "Governance": "#bc8cff",
        "AI": "#f0883e",
    }

    # Aggregate edges between clusters
    from collections import Counter, defaultdict
    edge_counts = Counter()
    edge_relations = defaultdict(Counter)
    cluster_triple_counts = Counter()
    cluster_concepts = defaultdict(set)

    for t in filtered:
        d1 = t["entity_1"].get("esg_domain", "")
        d2 = t["entity_2"].get("esg_domain", "")
        c1 = CLUSTER_MAP.get(d1, "")
        c2 = CLUSTER_MAP.get(d2, "")
        if not c1 or not c2:
            continue

        cluster_triple_counts[c1] += 1
        cluster_triple_counts[c2] += 1

        # Track concepts per cluster
        e1_name = t["entity_1"].get("canonical_name", t["entity_1"].get("normalized_name", ""))
        e2_name = t["entity_2"].get("canonical_name", t["entity_2"].get("normalized_name", ""))
        cluster_concepts[c1].add(e1_name)
        cluster_concepts[c2].add(e2_name)

        # Edge between clusters — use sorted pair so A→B and B→A merge into one
        rel_type = t.get("relationship_type", "ASSOCIATED_WITH")
        if c1 != c2:
            edge_key = (min(c1, c2), max(c1, c2))
            edge_counts[edge_key] += 1
            edge_relations[edge_key][rel_type] += 1
        else:
            # Self-loop (within same cluster)
            edge_key = (c1, c1)
            edge_counts[edge_key] += 1
            edge_relations[edge_key][rel_type] += 1

    # Build response
    nodes = []
    for cluster_name, color in CLUSTER_COLORS.items():
        nodes.append({
            "id": cluster_name,
            "label": cluster_name,
            "color": color,
            "triple_count": cluster_triple_counts.get(cluster_name, 0),
            "concept_count": len(cluster_concepts.get(cluster_name, set())),
            "size": 30 + min(cluster_triple_counts.get(cluster_name, 0) // 10, 40),
        })

    edges = []
    for (src, tgt), count in edge_counts.most_common():
        top_rels = edge_relations[(src, tgt)].most_common(3)
        edges.append({
            "source": src,
            "target": tgt,
            "weight": count,
            "top_relations": [{"type": r, "count": c} for r, c in top_rels],
            "width": max(2, min(count / 5, 15)),
        })

    return jsonify({
        "nodes": nodes,
        "edges": edges,
        "total_triples": len(filtered),
    })


def _get_louvain(domain: str, all_triples: list[dict],
                 companies: list | None, years: list | None) -> dict:
    """Return cached Louvain result for a domain+filter combination."""
    companies_key = tuple(sorted(companies)) if companies else ()
    years_key = tuple(sorted(years)) if years else ()
    cache_key = (domain, companies_key, years_key)

    if cache_key in _louvain_cache:
        return _louvain_cache[cache_key]

    relevant = []
    for t in all_triples:
        parts = t["id"].split("_")
        company = parts[1] if len(parts) >= 3 else "Unknown"
        year = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else 0
        if companies and company not in companies:
            continue
        if years and year not in years:
            continue
        if t["entity_1"].get("esg_domain") == domain and t["entity_2"].get("esg_domain") == domain:
            relevant.append(t)

    result = _build_louvain(relevant)
    _louvain_cache[cache_key] = result
    return result


def _build_louvain(relevant_triples: list[dict]) -> dict:
    """Run Louvain community detection on a filtered set of triples.

    Returns a dict with:
        partition  : {merged_nk -> community_id}  (-1 == Other)
        comm_members          : {community_id -> [merged_nk, ...]}
        comm_members_expanded : {community_id -> [raw_canonical, ...]}
        labels     : {community_id -> str}
        _canon     : callable(entity_dict) -> merged_nk
        G          : nx.Graph
        OTHER      : int (-1)
    """
    import re as _re
    from difflib import SequenceMatcher
    from collections import defaultdict

    try:
        import networkx as nx
        import community as community_louvain
    except ImportError:
        raise RuntimeError("python-louvain not installed. Run: pip install python-louvain")

    _THRESHOLD = 0.65
    _OTHER = -1
    _STOP = {"percent", "total", "data", "all", "other", "none",
             "number", "amount", "value", "rate", "level", "use", "used"}

    def _nk(s: str) -> str:
        s = s.lower().strip()
        for sfx in ("_inc", "_corp", "_ltd", "_limited"):
            if s.endswith(sfx):
                s = s[: -len(sfx)]
        return _re.sub(r"_+", "_", s).strip("_")

    nk_to_raw: dict[str, str] = {}
    for t in relevant_triples:
        for e in (t["entity_1"], t["entity_2"]):
            raw = e.get("canonical_name") or e.get("normalized_name", "")
            if raw:
                nk_to_raw.setdefault(_nk(raw), raw)

    names = sorted(nk_to_raw)
    mapping: dict[str, str] = {}
    for i, a in enumerate(names):
        if a in mapping:
            continue
        mapping[a] = a
        for b in names[i + 1:]:
            if b not in mapping and SequenceMatcher(None, a, b).ratio() >= _THRESHOLD:
                mapping[b] = a

    inv: dict[str, list[str]] = defaultdict(list)
    for nk, merged in mapping.items():
        inv[merged].append(nk_to_raw.get(nk, nk))

    def _canon(entity: dict) -> str:
        nk = _nk(entity.get("canonical_name") or entity.get("normalized_name", ""))
        return mapping.get(nk, nk)

    G = nx.Graph()
    for t in relevant_triples:
        n1, n2 = _canon(t["entity_1"]), _canon(t["entity_2"])
        if not n1 or not n2 or n1 == n2:
            continue
        if G.has_edge(n1, n2):
            G[n1][n2]["weight"] += 1
        else:
            G.add_edge(n1, n2, weight=1)

    _empty = {"partition": {}, "comm_members": defaultdict(list),
              "comm_members_expanded": {}, "labels": {}, "_canon": _canon,
              "G": G, "OTHER": _OTHER}
    if not G.nodes:
        return _empty

    raw_part = community_louvain.best_partition(G, resolution=0.3, random_state=42)

    by_comm: dict = defaultdict(list)
    for node, cid in raw_part.items():
        by_comm[cid].append(node)

    top_ids = sorted(by_comm, key=lambda c: len(by_comm[c]), reverse=True)[:8]
    top_set = {c for c in top_ids if len(by_comm[c]) >= 3}
    partition = {node: (cid if cid in top_set else _OTHER) for node, cid in raw_part.items()}

    comm_members: dict = defaultdict(list)
    for node, cid in partition.items():
        comm_members[cid].append(node)

    def _hub_score(node: str, sub) -> tuple:
        raw = node.replace("_", " ").strip()
        clean = _re.sub(r'^\d+[\s,]+', '', raw).strip()
        return (clean.lower() not in _STOP, len(clean) > 3,
                len(clean.split()) <= 7, sub.degree(node), G.degree(node))

    labels: dict[int, str] = {}
    for cid, members in comm_members.items():
        if cid == _OTHER:
            labels[cid] = "Other"
            continue
        sub = G.subgraph(members)
        best = max(sub.nodes, key=lambda n: _hub_score(n, sub)) if sub.nodes else members[0]
        clean = best.replace("_", " ").strip()
        stripped = _re.sub(r'^\d+[\s,]+', '', clean).strip()
        if len(stripped) >= 4:
            clean = stripped
        labels[cid] = clean[:45].strip().title() or f"Group {cid + 1}"

    def _expand(merged_members: list[str]) -> list[str]:
        result = []
        for m in merged_members:
            result.extend(inv.get(m, [nk_to_raw.get(m, m)]))
        return result

    return {
        "partition": partition,
        "comm_members": comm_members,
        "comm_members_expanded": {cid: _expand(ms) for cid, ms in comm_members.items()},
        "labels": labels,
        "_canon": _canon,
        "G": G,
        "OTHER": _OTHER,
    }


def _build_ontology_groups(relevant_triples: list[dict]) -> dict:
    """Group entities by their ontology_concept field.

    Returns the same dict structure as _build_louvain() so get_cluster_subgraph
    can use either backend without changes.
    """
    from collections import defaultdict
    from difflib import SequenceMatcher

    _OTHER = -1

    def _canon(entity: dict) -> str:
        return entity.get("canonical_name") or entity.get("normalized_name", "")

    # Collect per-entity ontology_concept (first-seen wins)
    entity_concept: dict[str, str] = {}
    all_entity_names: set[str] = set()
    for t in relevant_triples:
        for e in (t["entity_1"], t["entity_2"]):
            name = _canon(e)
            if not name:
                continue
            all_entity_names.add(name)
            concept = (e.get("ontology_concept") or "").strip()
            if concept and name not in entity_concept:
                entity_concept[name] = concept

    # Trust the pipeline's ontology_concept labels as-is.
    # Synonym merging was removed — string similarity caused false positives,
    # and a hardcoded table doesn't scale across companies or pipeline versions.
    raw_concepts = sorted(set(entity_concept.values()))
    concept_mapping: dict[str, str] = {c: c for c in raw_concepts}
    merged_concepts = raw_concepts
    concept_to_id: dict[str, int] = {c: i for i, c in enumerate(merged_concepts)}

    # First pass: assign raw community IDs
    raw_partition: dict[str, int] = {}
    for name in all_entity_names:
        concept = entity_concept.get(name, "")
        if concept:
            merged = concept_mapping.get(concept, concept)
            raw_partition[name] = concept_to_id.get(merged, _OTHER)
        else:
            raw_partition[name] = _OTHER

    # Drop communities with < 3 members into Other
    comm_counts: dict[int, int] = {}
    for cid in raw_partition.values():
        comm_counts[cid] = comm_counts.get(cid, 0) + 1

    partition: dict[str, int] = {
        name: (cid if cid != _OTHER and comm_counts.get(cid, 0) >= 3 else _OTHER)
        for name, cid in raw_partition.items()
    }

    comm_members: dict = defaultdict(list)
    for name, cid in partition.items():
        comm_members[cid].append(name)

    labels: dict[int, str] = {_OTHER: "Other"}
    for concept, cid in [(c, concept_to_id[c]) for c in merged_concepts]:
        labels[cid] = concept.replace("_", " ").title()

    # concept_to_cid: respects ≥3 threshold (matches visible communities in sub-cluster view)
    concept_to_cid: dict[str, int] = {}
    for raw_c, merged_c in concept_mapping.items():
        cid = concept_to_id.get(merged_c, _OTHER)
        concept_to_cid[raw_c] = cid if comm_counts.get(cid, 0) >= 3 else _OTHER

    # concept_to_cid_all: no threshold — used by cross-domain endpoint so sparse concepts
    # that don't form large same-domain communities can still be matched cross-domain.
    concept_to_cid_all: dict[str, int] = {
        raw_c: concept_to_id.get(concept_mapping.get(raw_c, raw_c), _OTHER)
        for raw_c in concept_mapping
    }

    return {
        "partition": partition,
        "comm_members": comm_members,
        "comm_members_expanded": {cid: ms for cid, ms in comm_members.items()},
        "labels": labels,
        "concept_to_cid": concept_to_cid,
        "concept_to_cid_all": concept_to_cid_all,
        "_canon": _canon,
        "G": None,
        "OTHER": _OTHER,
    }


def _get_ontology_groups(domain: str, all_triples: list[dict],
                         companies: list | None, years: list | None) -> dict:
    """Return cached ontology_concept grouping for a domain+filter combination."""
    companies_key = tuple(sorted(companies)) if companies else ()
    years_key = tuple(sorted(years)) if years else ()
    cache_key = (domain, companies_key, years_key)

    if cache_key in _ontology_cache:
        return _ontology_cache[cache_key]

    relevant = []
    for t in all_triples:
        parts = t["id"].split("_")
        company = parts[1] if len(parts) >= 3 else "Unknown"
        year = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else 0
        if companies and company not in companies:
            continue
        if years and year not in years:
            continue
        if t["entity_1"].get("esg_domain") == domain and t["entity_2"].get("esg_domain") == domain:
            relevant.append(t)

    result = _build_ontology_groups(relevant)
    _ontology_cache[cache_key] = result
    return result


@app.route("/api/cluster-detail")
def get_cluster_detail():
    """Return canonical concepts within a specific cluster.

    Used for drill-down from summary view.
    """
    cluster = request.args.get("cluster", "").lower()
    companies = request.args.getlist("companies") or None
    years_raw = request.args.getlist("years")
    years = [int(y) for y in years_raw if y.isdigit()] or None
    limit = max(10, min(request.args.get("limit", 200, type=int), 2000))

    if not cluster:
        return jsonify({"error": "cluster parameter required"}), 400

    triples = _load_all_triples()

    # Filter
    relevant = []
    for t in triples:
        parts = t["id"].split("_")
        company = parts[1] if len(parts) >= 3 else "Unknown"
        year = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else 0
        if companies and company not in companies:
            continue
        if years and year not in years:
            continue

        d1 = t["entity_1"].get("esg_domain", "")
        d2 = t["entity_2"].get("esg_domain", "")
        # Both entities must belong to the target cluster (strict containment)
        if d1 == cluster and d2 == cluster:
            relevant.append(t)

    # Build concept-level graph (no additional domain filter needed)
    data = _triples_to_graph(relevant, limit=limit)
    return jsonify(data)


@app.route("/api/cluster-subgraph")
def get_cluster_subgraph():
    """Ontology-concept community grouping within a domain cluster."""
    from collections import Counter, defaultdict

    cluster = request.args.get("cluster", "").lower()
    companies = request.args.getlist("companies") or None
    years_raw = request.args.getlist("years")
    years = [int(y) for y in years_raw if y.isdigit()] or None

    if not cluster:
        return jsonify({"error": "cluster parameter required"}), 400

    triples = _load_all_triples()

    lv = _get_ontology_groups(cluster, triples, companies, years)

    # Re-collect relevant triples for triple-count stats (cheap, already filtered in cache)
    relevant = [t for t in triples
                if t["entity_1"].get("esg_domain") == cluster
                and t["entity_2"].get("esg_domain") == cluster
                and (not companies or t["id"].split("_")[1] in companies)
                and (not years or (int(t["id"].split("_")[2]) if t["id"].split("_")[2].isdigit() else 0) in years)]

    if not lv["partition"] and not relevant:
        return jsonify({"nodes": [], "edges": [], "total_triples": 0})

    partition = lv["partition"]
    comm_members = lv["comm_members"]
    labels = lv["labels"]
    _canon = lv["_canon"]
    _OTHER = lv["OTHER"]

    COLORS = {"environmental": "#3fb950", "social": "#58a6ff",
              "governance": "#bc8cff", "ai": "#f0883e"}
    color = COLORS.get(cluster, "#8b949e")

    # Count triples and cross-community edges
    comm_triple_count: Counter = Counter()
    cross_edges: Counter = Counter()
    for t in relevant:
        n1 = _canon(t["entity_1"])
        n2 = _canon(t["entity_2"])
        c1 = partition.get(n1)
        c2 = partition.get(n2)
        if c1 is not None:
            comm_triple_count[c1] += 1
        if c2 is not None and c2 != c1:
            comm_triple_count[c2] += 1
            cross_edges[(min(c1, c2), max(c1, c2))] += 1

    def _cid(cid):
        return "comm_other" if cid == _OTHER else f"comm_{cid}"

    nodes = []
    for cid, members in comm_members.items():
        nodes.append({
            "id": _cid(cid),
            "label": labels.get(cid, "Other"),
            "color": color if cid != _OTHER else "#8b949e",
            "triple_count": comm_triple_count.get(cid, 0),
            "concept_count": len(members),
            "size": 20 + min(len(members) * 3, 45),
            "community_id": cid,
            "members": lv["comm_members_expanded"].get(cid, []),
            "is_other": cid == _OTHER,
        })
    nodes.sort(key=lambda n: n["concept_count"], reverse=True)

    edges = [
        {"source": _cid(c1), "target": _cid(c2),
         "weight": count, "width": max(1, min(count // 5, 12))}
        for (c1, c2), count in cross_edges.most_common()
    ]

    return jsonify({"nodes": nodes, "edges": edges,
                    "cluster": cluster, "total_triples": len(relevant)})


@app.route("/api/cross-domain-communities")
def get_cross_domain_communities():
    """Ontology-concept bipartite graph connecting two ESG domains.

    Uses ontology_concept field directly for community lookup so cross-domain
    entities are covered even if they only appear in cross-domain triples.
    """
    from collections import Counter

    domain1 = request.args.get("domain1", "").lower()
    domain2 = request.args.get("domain2", "").lower()
    companies = request.args.getlist("companies") or None
    years_raw = request.args.getlist("years")
    years = [int(y) for y in years_raw if y.isdigit()] or None

    if not domain1 or not domain2 or domain1 == domain2:
        return jsonify({"error": "domain1 and domain2 must be different and non-empty"}), 400

    triples = _load_all_triples()

    def _cy(t):
        parts = t["id"].split("_")
        return parts[1] if len(parts) >= 3 else "Unknown", \
               int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else 0

    filtered = [t for t in triples
                if (not companies or _cy(t)[0] in companies)
                and (not years or _cy(t)[1] in years)]

    cross = [t for t in filtered
             if {t["entity_1"].get("esg_domain"), t["entity_2"].get("esg_domain")} == {domain1, domain2}]

    if not cross:
        return jsonify({"nodes_d1": [], "nodes_d2": [], "edges": [],
                        "cross_triple_count": 0, "domain1": domain1, "domain2": domain2})

    og1 = _get_ontology_groups(domain1, triples, companies, years)
    og2 = _get_ontology_groups(domain2, triples, companies, years)
    # Use threshold-free lookup so sparse concepts still match cross-domain.
    c2c1 = og1["concept_to_cid_all"]
    c2c2 = og2["concept_to_cid_all"]

    # Map each cross-domain triple to its ontology community pair.
    # Track per-concept entity counts and actual entity names for drill-down.
    from collections import defaultdict as _dd
    edge_count: Counter = Counter()
    d1_entity_count: Counter = Counter()
    d2_entity_count: Counter = Counter()
    d1_cross_members: dict = _dd(set)
    d2_cross_members: dict = _dd(set)
    for t in cross:
        if t["entity_1"].get("esg_domain") == domain1:
            e1, e2 = t["entity_1"], t["entity_2"]
        else:
            e1, e2 = t["entity_2"], t["entity_1"]
        c1 = c2c1.get((e1.get("ontology_concept") or "").strip(), -1)
        c2 = c2c2.get((e2.get("ontology_concept") or "").strip(), -1)
        if c1 != -1 and c2 != -1:
            edge_count[(c1, c2)] += 1
            d1_entity_count[c1] += 1
            d2_entity_count[c2] += 1
            n1 = (e1.get("canonical_name") or e1.get("normalized_name", "")).strip()
            n2 = (e2.get("canonical_name") or e2.get("normalized_name", "")).strip()
            if n1: d1_cross_members[c1].add(n1)
            if n2: d2_cross_members[c2].add(n2)

    if not edge_count:
        return jsonify({"nodes_d1": [], "nodes_d2": [], "edges": [],
                        "cross_triple_count": len(cross), "domain1": domain1, "domain2": domain2})

    COLORS = {"environmental": "#3fb950", "social": "#58a6ff",
              "governance": "#bc8cff", "ai": "#f0883e"}

    involved_d1 = {c1 for c1, _ in edge_count}
    involved_d2 = {c2 for _, c2 in edge_count}

    def _make_node(cid, og, domain, xd_count, cross_members_map):
        return {
            "id": f"{domain}_{cid}",
            "label": og["labels"].get(cid, f"Concept {cid}"),
            "domain": domain,
            "color": COLORS.get(domain, "#8b949e"),
            "concept_count": xd_count,
            "same_domain_count": len(og["comm_members"].get(cid, [])),
            "members": og["comm_members_expanded"].get(cid, []),
            "cross_members": list(cross_members_map.get(cid, [])),
            "community_id": cid,
        }

    nodes_d1 = sorted([_make_node(c, og1, domain1, d1_entity_count[c], d1_cross_members) for c in involved_d1],
                      key=lambda n: -n["concept_count"])
    nodes_d2 = sorted([_make_node(c, og2, domain2, d2_entity_count[c], d2_cross_members) for c in involved_d2],
                      key=lambda n: -n["concept_count"])
    edges = [
        {"source": f"{domain1}_{c1}", "target": f"{domain2}_{c2}", "weight": w}
        for (c1, c2), w in edge_count.most_common()
    ]

    return jsonify({
        "domain1": domain1, "domain2": domain2,
        "nodes_d1": nodes_d1, "nodes_d2": nodes_d2,
        "edges": edges,
        "cross_triple_count": len(cross),
    })


@app.route("/api/cross-cluster-detail")
def get_cross_cluster_detail():
    """Return triples connecting two specific clusters.

    Used for drill-down when clicking an edge in summary view.
    """
    cluster1 = request.args.get("cluster1", "").lower()
    cluster2 = request.args.get("cluster2", "").lower()
    companies = request.args.getlist("companies") or None
    years_raw = request.args.getlist("years")
    years = [int(y) for y in years_raw if y.isdigit()] or None
    limit = max(10, min(request.args.get("limit", 300, type=int), 2000))

    if not cluster1 or not cluster2:
        return jsonify({"error": "cluster1 and cluster2 parameters required"}), 400

    triples = _load_all_triples()

    relevant = []
    for t in triples:
        parts = t["id"].split("_")
        company = parts[1] if len(parts) >= 3 else "Unknown"
        year = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else 0
        if companies and company not in companies:
            continue
        if years and year not in years:
            continue

        d1 = t["entity_1"].get("esg_domain", "")
        d2 = t["entity_2"].get("esg_domain", "")
        # Match triples that span between the two clusters (either direction)
        if (d1 == cluster1 and d2 == cluster2) or (d1 == cluster2 and d2 == cluster1):
            relevant.append(t)

    data = _triples_to_graph(relevant, limit=limit)
    return jsonify(data)


@app.route("/api/greenwashing")
def get_greenwashing():
    from pipeline.credibility import compute_greenwashing_index
    triples = _load_all_triples()

    company = request.args.get("company")
    if company:
        triples = [t for t in triples if t["id"].split("_")[1] == company]

    gw = compute_greenwashing_index(triples)
    if company:
        gw["company"] = company

    scores = [t.get("credibility_score", 0) for t in triples]
    if scores:
        gw["credibility_avg"] = round(sum(scores) / len(scores), 1)
        gw["credibility_high"] = sum(1 for s in scores if s >= 3)
        gw["credibility_low"] = sum(1 for s in scores if s < 2)

    return jsonify(gw)


@app.route("/api/chat", methods=["POST"])
def post_chat():
    """Chatbot endpoint with short-term memory.

    Request JSON:
        session_id  : str | null  — omit or null to start a new session
        message     : str         — user message
        graph_state : dict        — current graph view state from frontend

    Response JSON:
        reply       : str
        session_id  : str
    """
    from chat import chat as _chat

    body = request.get_json(force=True, silent=True) or {}
    user_message = (body.get("message") or "").strip()
    if not user_message:
        return jsonify({"error": "message is required"}), 400

    api_key = config.ANTHROPIC_API_KEY if hasattr(config, "ANTHROPIC_API_KEY") else ""
    if not api_key:
        import os
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return jsonify({"error": "ANTHROPIC_API_KEY not configured"}), 500

    try:
        reply, session_id = _chat(
            session_id=body.get("session_id") or "",
            user_message=user_message,
            graph_state=body.get("graph_state") or {},
            anthropic_api_key=api_key,
        )
        return jsonify({"reply": reply, "session_id": session_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def serve(port: int = 8080):
    mode = "Neo4j" if _has_neo4j() else "File"
    print(f"Starting ESG KG visualization ({mode} mode) at http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    serve()
