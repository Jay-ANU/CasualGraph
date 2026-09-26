export type Block = { id: string; text: string; page: number | null };
export type Policy = { our_roles?: string[]; id: string; title: string; text: string; version: number; contract_type: string };
export type Workspace = { matter_id: string; org_id: string };
export type Matter = { id: string; org_id: string; name: string; role?: string };
export type ContractSummary = { id: string; name: string; status: string; revision: number; created_at?: number };
export type Contract = ContractSummary & Workspace & { redaction_version?: number; format: string; blocks: Block[]; warnings: string[]; replacement_count: number; reviews: { id: string; status: string }[] };
export type Source = { id: string; title: string; url: string; retrieved_at: string; text: string; version_status: string; source_kind?: string; discovery?: string; effective_date_candidates?: { date: string; quote: string }[] };
export type Citation = { source_id: string; supporting_quote: string };
/** A statute the reviewing model cited; status says whether official text was attached. */
export type LawRef = { law: string; article: string; point: string; status: string };
export type ResearchIssue = { key: string; issue: string; laws: { name: string; articles: string[] }[]; queries: string[] };
export type Finding = { version_status?: string; agent_id?: string; agent_title?: string; id: string; rule_id?: string; block_id: string | null; original_quote: string; title: string; kind: string; severity: string; impact: string; reason: string; suggested_text: string; evidence_status: string; missing_facts: string[]; citations: Citation[]; law_refs?: LawRef[]; policy_ids: string[]; revision_allowed?: boolean; verification_status?: string; verification_note?: string; validation_warnings?: string[]; conflict_group?: string; requires_legal_confirmation?: boolean; cross_edit_status?: string; cross_edit_note?: string };
export type Decision = { decision: string; text: string; version: number; legal_basis_confirmed?: boolean };
export type TransactionContext = { performance_stage: string; attachments_status: string; business_priority: string; deal_value?: string | number | null; currency: string };
/** How much of the review harness runs: ultra_fast (one round, unverified) up to deep (specialist agents). */
export type ReviewTier = 'ultra_fast' | 'fast' | 'standard' | 'deep';
/** A review skill the backend loaded for this review, and why. The guidance text stays server-side. */
export type SkillUse = { id: string; name: string; version: string; reason: string; source?: { origin: string; license?: string; repo?: string } };
export type Profile = { review_tier?: ReviewTier; scenario?: ContractScenario; our_party?: { block_id: string; quote: string }; transaction_context?: TransactionContext; review_mode?: 'standard' | 'multi_agent'; transaction_date?: string; model?: { id: string; provider: string }; our_role?: string; contract_type?: string; instructions?: string };
export type Coverage = { rule_id: string; title: string; status: string; note: string; verification_note?: string };
export type Fact = { name: string; value: string; block_id: string; quote: string };
export type Review = { review_tier?: ReviewTier; skills?: SkillUse[]; transaction_brief?: TransactionBrief | null; evidence_health?: EvidenceHealth; retrieval?: { rule_id: string; status: string; provider: string; warnings: string[]; issue?: string }[]; research?: { status: string; issues: ResearchIssue[]; rejected_queries?: number } | null; draft_check?: DraftCheck; draft_approval?: { fingerprint: string; final_hash: string; user_id: string }; collaboration?: Collaboration; metrics?: { model_calls?: number; agent_model_calls?: Record<string, number> }; id: string; contract_id?: string; created_at?: number; status: string; stage: string; resumable: boolean; error?: string; findings: Finding[]; coverage: Coverage[]; sources: Source[]; decisions: Record<string, Decision>; policies: Policy[]; notice: string; profile?: Profile; engine_version?: number; intake?: { facts: Fact[] }; summary?: { high: number; medium: number; low: number; checked_rules: number; total_rules: number; needs_confirmation: number }; progress?: { phase: string; completed: number; total: number }; batch_errors?: Record<string, string> };
export type Capabilities = { review_tiers?: ReviewTier[]; skills_version?: number; scenario_catalog_version?: number; scenario_catalog?: ScenarioCatalog; audit_foundation_version?: number; draft_release_version?: number; upload_disclosure?: { version: string; notice: string; storage_region: string }; collaboration_version?: number; model_configured: boolean; encryption_configured: boolean; review_engine_version?: number; followup_questions?: boolean; law_search: { provider: string; notice: string } };
export type Model = { id: string; family: string };
export type Catalog = { available_families?: string[]; unavailable_families?: string[]; catalog_source?: string; models: Model[]; families: string[]; default_model: string; notice: string };
export type Answer = { id: string; question: string; answer: string; status?: string; uncertain?: boolean; block_refs?: { block_id: string; quote: string }[]; citations?: Citation[]; law_refs?: LawRef[]; notice?: string; model?: string };
export type User = { id?: string; username?: string; email?: string; role?: string };
export type Api = <T>(path: string, init?: RequestInit) => Promise<T>;
export type Collaboration = { version: number; max_parallel: number; call_budget: number; agents: { id: string; title: string; status: string; completed: number; total: number; note: string }[] };

export type DraftCheck = { id: string; fingerprint: string; final_hash: string; status: string; checks: { finding_id: string; status: string; reason: string }[]; whole_contract: { status: string; reason: string }; missing_facts: string[] };

export type TransactionBrief = { version: number; context: Partial<TransactionContext>; context_source: string; material_references: { block_id: string; quote: string; source: string }[]; gaps: { code: string; message: string; source: string }[]; notice: string };
export type EvidenceHealth = { queried_topics: number; topics_with_sources: number; failed_or_empty_topics: number; source_count: number; non_authoritative_sources: number; version_pending: number; status: string; notice: string };

export type ContractScenario = { id: string; label: string; group: string; roles: { value: string; focus: string }[];
  materials: string[]; limits: string; checks: { id: string; title: string }[]; catalog_version: number;
  catalog_revision: string; role_focus?: string };
export type ScenarioCatalog = { version: number; revision: string; notice: string; scenarios: ContractScenario[] };
