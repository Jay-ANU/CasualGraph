# Structured contract documents

The legal desk preserves document structure from intake through redaction,
review, preview and export. The immutable, encrypted upload remains the source
of truth. Existing text-only contracts stay readable without migration.

## User behavior

- Word tables retain their rows, columns, merged cells and nested tables.
  Automatic numbering is shown separately from editable paragraph text.
  Pictures remain at their source locations. Headers, footers and text boxes
  appear as separate, read-only source sections.
- PDFs retain page numbers and source coordinates. Native text, ruled tables
  and conservative aligned tables are extracted without rasterizing every page.
  Scans and substantial image regions can use the optional private OCR worker.
  Ambiguous layouts and unrecognized regions are reported at their locations.
- The redacted reading view and the authenticated original view are separate.
  Opening an original or an image requires current editing access to the matter;
  the browser loads these bytes only on request and releases its Blob URLs on
  close. Original bytes and source paths never enter the review model payload.
- Review inputs include table structure and stable block IDs. A repeated amount
  in different cells cannot be relocated by text similarity. OCR text enters
  the same redaction and user confirmation flow as native text. Enclosing table
  fields are retained for redaction even when an image contains its own table.
- Word export applies supported edits as tracked revisions inside the original
  package. Table layout, images, headers, footers and unrelated package parts
  are preserved. Changes to unsupported objects are included in a clearly
  labelled appendix with their complete original and proposed text; the source
  object stays intact. Incorrect source anchors remain a file-integrity error.
- PDF export creates an annotated copy of the original pages with a complete
  change appendix. It does not overwrite PDF page text or claim to produce an
  editable Word reconstruction. The highlight itself contains the full comment,
  so comment icons do not obscure short amounts or cell values.
- Export remains controlled by the user. With no pending findings, download
  starts directly. Otherwise, one confirmation shows the pending count and
  exports the current selection. Parsing issues and appendix counts are notices;
  neither triggers model approval or an extra review loop.

## Data shape and compatibility

`document_structure_version: 1` is advertised by `/legal/version` and checked
by the production frontend build and backend deployment verification. Contract
responses contain `document`, `assets`, `parsing_status`, `reviewable`, and
`original_available` alongside the existing `blocks`.

`document` contains reference-only paragraph, table and image nodes, page
geometry and localized issues. All text lives in `blocks`, so redaction has one
canonical copy to transform. Private XML anchors, image package paths, source
bytes and nested-cell redaction ancestry are omitted from public/model views.
Model requests use compact structural references to avoid duplicating text or
verbose geometry. Stable IDs, source hashes and document structure participate
in the export fingerprint.

Authenticated source endpoints:

- `GET /legal/contracts/{id}/original`: the unchanged uploaded bytes.
- `GET /legal/contracts/{id}/assets/{asset_id}`: a bounded PNG raster preview.
- `GET /legal/contracts/{id}/original-text`: source text for the original view.

These endpoints use the same matter permission checks, `no-store` responses
and audit trail as other original-data access. Image previews strip embedded
metadata and active formats; source images themselves remain unchanged.

## OCR deployment and practical limits

See [the private parser guide](../../services/document_parser/README.md) for
the separate pinned Docling/Tesseract image, prefetch step, authenticated
protocol, private TLS/CA settings, time budget and deployment commands.
The main API does not load OCR models on its 512 MB machine.

Native Word and PDF structure work without the worker. Image text and scans
need the worker configured and ready. If recognition is unavailable or exceeds
the per-upload budget, the original stays viewable with a localized notice.
An upload with no recognized text cannot start an empty model review. OCR does
not certify seals, handwriting, diagrams or the completeness of a scanned page.

Uploads retain the existing 10 MB, 60,000-character and 500-block limits, now
including table cells and OCR text. Exceeding the limits reports an error rather
than silently truncating the contract. PDF geometry, image decode sizes and OCR
requests have additional resource bounds described in the parser guide.

## Verification

Regression fixtures are synthetic; they include native and legacy Word merges,
nested tables, numbering, repeated images, mixed text/image paragraphs, private
image metadata, read-only objects, rotated/cropped PDFs and targeted OCR errors.
API tests cover encrypted intake, cross-cell redaction, source permissions,
structured prompts, stable edit identity and user-controlled export. Browser
smoke tests exercise real parser/writer output through the built React UI.

Word revisions and appendices, plus Chinese annotated PDFs, were rendered for
visual verification. Actual OCR inference requires the separately provisioned
model image; the standard suite explicitly skips that warm-model smoke test
when its dependencies and model bundles are absent.
