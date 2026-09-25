# Preserve the site; add Legal independently

## Routes

The historical homepage is restored from d3ea3fb. `/agent` opens the existing research agent directly; `/research` is an alias. Legal is a separate `/legal` workspace, linked from desktop/mobile navigation and the homepage footer. It does not redirect the original research route. Company, Desktop, Graph and Offer pages retain their original routes and presentation. Authentication and the current API client remain in place.

Recruitment endpoints retain admin authorization and candidate-token checks. Their original additive schema is initialized using the current authentication database. Existing research graphs are read through `/graph/public` (explicitly shared reports only) or authenticated `/graph/workspace` (current document access checks). The former unscoped graph and server-path APIs are not restored. No new contract-review data is published into the graph. The diagnostic ESG page explains that its obsolete standalone extraction endpoint remains disabled; report upload and querying use the research desk.

## Word export contract

- A `.docx` input defaults to `.docx` export. An explicitly requested JSON review report is separate. It cannot silently become a TXT reconstruction.
- Select suggestions in the workspace, then export **Word（含修订痕迹）**. Selected suggestions become pending native Word revisions, not accepted clean text.
- `legal/docx_redlines.py` applies insert/delete changes to the original document package. Unchanged text and run formatting are retained; insertions/deletions include reviewer and date, and Word revision display/tracking is enabled.
- Rejecting all generated revisions reconstructs the original paragraph text; accepting all reconstructs the chosen revised text. Unchanged package parts, including headers/footers, are preserved byte-for-byte.
- Plain body and table-cell paragraphs are supported. Edited paragraphs containing fields, bookmarks, comments, drawings or other complex inline objects fail closed rather than being flattened. Existing unresolved revisions and signed documents must be resolved/copied before intake; they are never silently accepted.
- No selected edits means no revision export. Report export remains available. Original-identity downloads still require edit permission.
- Revision documents contain original identifying information and deleted text. They are **not sanitized sharing copies**.

## Verification

`tests/test_word_redlines.py` checks accept/reject reconstruction, local run properties, table cells, tabs/breaks, whitespace, unchanged package parts, missing settings, stale anchors and existing revisions. `tests/test_restored_routes.py` exercises export defaults, native XML markers, permissions, additive offer initialization and graph privacy. Existing security assertions remain in place except the explicitly restored offer routes, which now have dedicated authorization tests.

Browser tests run against the built frontend with synthetic API responses. These are integration/interaction checks, not live legal-model accuracy tests. The one-time branch-local restoration builder is removed from the final tree.

## Deployment

Frontend restoration and the enhanced Word exporter have separate deployments. A successful Vercel build is not evidence that the Fly backend has updated. Fly needs the existing deployment authorization, model secret and stable encryption secret. Do not disable encryption or replace its key to make an upload pass. Verify backend deployment independently before claiming the enhanced exporter is live.
