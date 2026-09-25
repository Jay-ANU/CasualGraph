# Consumer Legal workspace and bounded multi-agent collaboration

Scope: preserve the original homepage, `/agent`, `/research`, customer Max entitlements, fixed server-side YData gateway, external-law retrieval and original DOCX tracked-change exporter. This includes the prior local v2 candidate plus the explicitly requested collaboration.

## Application agent roles

A shared intake extracts only facts supported by exact contract spans. Legal-risk, commercial-interest and company-policy specialists then run concurrently in separate contexts. Each has disjoint namespaced rule coverage and cannot emit another specialist's finding kind. Company-policy work is explicitly not applicable when no snapshotted policy exists. An independent critic checks every candidate AND every coverage claim, including rules with no findings. A final coordinator checks omissions, cross-clause conflicts and compatibility of all proposed edits. There is no majority-vote acceptance.

All roles use the same user-approved model ID/provider frozen in the review profile. This is independent task execution, not statistically independent sources of truth. Same-model critics can share errors; only annotated real-contract evaluation can measure whether legal accuracy improved.

Specialists submit proposals only. The coordinator is the sole checkpoint writer under a process lock. Interim findings are not revision-eligible. The final deterministic guard rejects different replacements of the same paragraph even when the model says both are consistent. No auto-overwrite or automatic redline acceptance. Human legal-version/application confirmation and manual-edit confirmation remain required where appropriate.

## Bounds and recovery

Three specialist workers per review; four concurrent model calls per backend process across team reviews; forty model calls per attempt; explicit input-size guard and no silent contract truncation. Bounds are process-local, not a distributed rate limiter. Existing durable queue admission remains eight global/two per user. Every step rechecks Max entitlement, matter access, original version, consent and worker lease; cancelled or unauthorized late responses cannot publish. In-flight remote requests cannot be recalled.

Inputs are deep-copied. Each finished task includes a hash of its rule/profile/evidence input and retained source snapshot. Resume repeats failed or changed tasks, not intact independent agents. Changes invalidate arbitration. Missing tasks and unsupported coverage produce partial results, not a clean bill of health. No retries through another model/provider. Real latency and cost remain unmeasured.

`review_mode` can be `standard` or `multi_agent` and is frozen per new review; new UI defaults to collaboration. Existing jobs retain their original engine. The UI displays actual persisted agent progress, not simulated reasoning or percentages.

## Previous v2 improvements included

Consumer-style document composer and history sidebar, progressive redaction/role setup, in-place original-document panel, readable findings and text diffs, Markdown report, bounded encrypted per-user follow-ups, cancellation and checkpoint retry. Follow-ups use only the current review evidence and model; they never modify the contract. Company rules remain separate from legal sources. Search queries come from public server-side templates, not raw contract text. Native Word revisions remain the existing exporter.

## Validation and rollout

Offline unit/flow tests passed before integration; complete repository CI and real-built browser results must be checked on the final commit. Functional provider responses are synthetic. No claim of real YData inference, comprehensive legal accuracy, production-account E2E or desktop Word automation.

Deploy backend first. Production frontend requires `review_engine_version=2`, `followup_questions=true`, `collaboration_version=1`, `max_only=true`, `model_gateway=ydata` and `model_selection_version=1`. Do not bypass this gate. No credentials, existing encryption keys, membership records or unrelated site routes are changed. Any temporary hash-pinned integration files must be absent from the final net diff.
