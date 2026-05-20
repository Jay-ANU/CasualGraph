# CausalGraphAI Agile Document

## Project Overview
This project extracts ESG-related information from sustainability reports, validates the extracted triples, normalizes entities, and visualizes the result as an interactive knowledge graph.

## Project Backlog

### Core Pipeline (✅ Implemented)
1. PDF ingestion and text extraction from sustainability reports.
2. LLM-based ESG triple extraction with evidence text.
3. Schema validation and ontology mapping.
4. Character-level entity normalization and deduplication.
5. Semantic entity clustering for near-duplicate concepts.
6. Credibility scoring and verification tagging.

### Visualization (✅ Implemented / 🟡 In Progress)
7. Summary graph view with 4 ESG clusters.
8. Full detail view with node-edge filtering by company, year, domain.
9. Drill-down from cluster to concepts (🟡 In Progress).
10. Optional Neo4j loading for graph storage and querying.

### User & Data Management (🔲 Planned)
11. User authentication and login system.
12. User-level data persistence (save/restore extractions).
13. Multi-user workspace support.
14. Report upload and history tracking.
15. Export results (JSON, CSV, graph formats).

### Enhancement Features (💡 Brainstorm / Future)
16. Advanced graph analytics (path finding, centrality measures).
17. Comparison across multiple reports.
18. Real-time collaboration mode.
19. Automated report scheduling and updates.
20. Integration with financial data APIs for validation.

## User Stories

### User Story 1 — ESG analyst reading reports
**User:** ESG analyst at an investment firm

**Situation:** The analyst reviews a company’s sustainability report to understand environmental performance, workforce metrics, and governance statements.

**Assumption about behaviour:** The analyst does not read the entire report line by line. Instead, they skim for key numbers, statements, and evidence-backed ESG claims.

**User value:** The analyst wants to quickly locate relevant ESG facts to support investment analysis.

### User Story 2 — Investor comparing companies
**User:** Investor evaluating multiple companies

**Situation:** The investor compares ESG performance across several companies’ sustainability reports.

**Assumption about behaviour:** The investor looks for comparable metrics such as emissions, workforce diversity, energy use, and employee turnover.

**User value:** The investor wants to identify consistent ESG indicators to compare companies more efficiently.

### User Story 3 — Researcher analysing ESG trends
**User:** Academic or policy researcher studying ESG trends

**Situation:** The researcher collects sustainability reports from multiple companies and industries.

**Assumption about behaviour:** Instead of reading each report manually, the researcher uses the extracted graph to identify patterns, recurring topics, and cross-company relationships.

**User value:** The researcher wants to analyse ESG trends across companies and sectors.

### User Story 4 — Reader navigating long reports
**User:** General reader trying to understand a company’s sustainability report

**Situation:** The report is very long, often hundreds of pages, and difficult to navigate manually.

**Assumption about behaviour:** The reader searches for sections that contain concrete metrics, summary tables, or direct claims rather than reading the full report.

**User value:** The reader wants to quickly find the most important sustainability information.

## Scenarios and Acceptance Criteria

### Scenario 1 — Summary graph view
**Status: ✅ Implemented**

Given a user opens the visualization page,
when the graph loads,
then the system shows the four summary clusters: Environmental, Social, Governance, and AI.

**Acceptance Criteria:**
- The summary view loads automatically with all configured data files.
- Each cluster displays its triple count and concept count.
- Cluster nodes show edge weights (triple counts between clusters).
- The view remains readable when the dataset grows.

### Scenario 2 — Drill-down from a cluster
**Status: 🟡 In Progress**

Given a user clicks one cluster,
when the cluster is selected,
then the system shows the detailed concepts inside that cluster.

**Acceptance Criteria:**
- Clicking a cluster must update the displayed graph.
- The user must be able to return to the summary view.
- The drill-down must preserve the selected company and year filters.
 - Detail view should load within 3 seconds for typical cluster sizes (≤50 nodes).

### Scenario 3 — Full detail exploration
**Status: ✅ Implemented**

Given a user wants to inspect all extracted triples,
when they switch to detail mode,
then the system shows the full node-edge graph with individual relationships.

**Acceptance Criteria:**
- Detail mode supports filtering by company, year, and ESG domain.
- Node dragging and zooming remain responsive.
- Edge tooltips show relationship type, evidence, and credibility score.
- Users can toggle between summary and detail mode.

### Scenario 4 — Pipeline execution
Given a sustainability PDF is available,
when the extraction pipeline runs,
then the system should produce normalized JSONL triples and, if configured, load them into Neo4j.

**Acceptance Criteria:**
- The pipeline must fail gracefully if the PDF cannot be parsed.
- Invalid triples must be removed during validation.
- Output files must be written to the expected data directory.

### Scenario 5 — Chatbot Q&A over the KG
**Status: 🟡 In Progress**

Given a user asks a natural-language question about a company’s ESG report (e.g., “What are this company’s Scope 1 emissions this year?”),
when the chatbot receives the question,
then the system should query the knowledge graph (or file-mode data), return a concise answer, and include provenance (evidence sentence + source).

**Acceptance Criteria:**
- Chatbot returns a short, factual answer with at least one evidence sentence and a link/reference to the source document.
- The chatbot preserves conversational context across at least 3 turns for follow-up questions.
- Out-of-scope questions trigger a graceful fallback with guidance (e.g., "I don't have that information; try asking about emissions or workforce metrics").

**Definition of Done:**
- Chatbot endpoint responds to sample queries with provenance.
- Integration tests for 10 representative questions pass (accuracy ≥75%).

### Scenario 6 — Daily user scenarios (quick, practical workflows)
These are short, realistic tasks that users will perform daily.

- Quick KPI check (ESG analyst):
	- Given the analyst wants the latest numeric KPI (e.g., "Scope 1 emissions 2024"), when they query or click the KPI card, then the system shows the metric, a one-line context sentence, and a link to the evidence.
	- Acceptance: KPI loads within 2s and evidence appears alongside the number.

- Weekly report preparation (team member):
	- Given a team member needs three illustrative examples for the weekly slides, when they select "Export examples", then the system provides 3 high-confidence triples with evidence and short summaries suitable for slides.
	- Acceptance: Export produces 3 examples and a short text summary in under 10s.

- Non-expert question (stakeholder):
	- Given a stakeholder asks "What are the biggest social risks for Company X?", when they ask via chatbot, then the system returns a one-paragraph plain-language summary with 2–3 supporting evidence sentences and confidence indicators.
	- Acceptance: Summary is concise (<150 words) and cites sources.

## Risks and Mitigations

| Risk | Why it matters | Mitigation |
|---|---|---|
| LLM hallucination or unsupported claims | The model may invent relationships that are not in the report, which would reduce trust in the knowledge graph. | Require evidence text for every triple, validate schema fields, and drop triples without sufficient support. |
| Overly dense graphs | A full graph can become unreadable when many reports or years are loaded together. | Use a 4-cluster summary view first, then support drill-down and node limits in detail mode. |
| Duplicate or near-duplicate entities | The same concept may appear with different wording, making the graph fragmented. | Apply character-level normalization and semantic deduplication before visualization or Neo4j load. |
| Incorrect entity typing | ESG concepts such as metrics, initiatives, and outcomes can be misclassified by the extractor. | Restrict allowed types, validate against the ontology, and use post-processing normalization for ambiguous cases. |
| Weak or inconsistent evidence | Some extracted triples may be based on vague language or incomplete context. | Score credibility, prioritize triples with numbers or third-party references, and flag low-confidence output for review. |
| Missing Neo4j configuration | The graph load step may fail if Neo4j credentials are not set. | Support file mode as the default and make Neo4j loading optional. |
| Performance issues on large reports | Very large reports can slow extraction, normalization, and rendering. | Chunk PDFs, cap node limits in the UI, and process data in stages instead of all at once. |
| Domain coverage gaps | New ESG topics or company-specific terminology may not fit the current ontology. | Extend the ontology incrementally and keep an instance layer for company-specific entities. |

## Notes
- The current design uses a summary + drill-down + detail approach so the graph stays understandable.
- The document can be extended with sprint-by-sprint tracking later if needed, but this version keeps the focus on backlog, stories, scenarios, and risks.
