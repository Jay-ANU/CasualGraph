# Private document parser for contract images and scanned PDF pages

This is an **optional, separate service**. The main CasualGraph API performs
native PDF layout/table extraction with pdfplumber and parses Word's original
structure. It does not import Docling, Torch, or an OCR model at startup.
Do not deploy this worker inside the API's 512 MB Fly machine.

The worker uses one pinned Docling pipeline with local layout/table models and
local Tesseract (`chi_sim`, `chi_tra`, `eng`). It is a structural/OCR service,
not a legal reviewer or a vision-model provider. No contract is sent to a
public parsing service. An unconfigured, unavailable, timed-out, or incomplete
worker leaves the source and its localized coverage issues intact. A wholly
scanned upload can therefore have **zero reviewable blocks** until OCR works;
such an upload must not be described as reviewed.

## Build and provision

Run the build from the repository root:

```sh
docker build -f services/document_parser/Dockerfile -t casualgraph-document-parser .
```

The image pins Docling `2.137.0`, Docling Core `2.98.0`, and CPU Torch/Torchvision. Its build downloads
only the chosen layout and TableFormer model bundles; Tesseract language data
is installed by the OS package manager. Contract files are not available during
the build. `prefetch.py` is also usable for preparing a dedicated model volume.
Keep the models associated with this tested SDK version when updating images.

At runtime, `DOCLING_ARTIFACTS_PATH` must point to this already populated bundle.
`HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, and
`HF_HUB_DISABLE_TELEMETRY=1` are enabled. Docling's
`enable_remote_services` and `allow_external_plugins` are explicitly false;
picture description, picture classification, formula/code enrichment and
generated page-image exports are disabled. Runtime network egress should also
be denied by the deployment's network policy. Restrict inbound traffic to the
CasualGraph API and the operator's health checks.

Provision the worker independently. A starting test allocation is 2 CPU cores
and 4 GB RAM, with one server worker and one conversion process; this is a
deployment starting point, **not a measured memory or latency guarantee**.
Measure it with representative Chinese contracts before setting production
limits. Container memory/CPU limits apply to the parser and its child process.

For a local trial, publish port 8090 only on loopback and inject a random secret
through a secret store or a permission-restricted environment file. The file
must contain `LEGAL_DOCUMENT_PARSER_TOKEN` with at least 32 ASCII characters:

```sh
docker run --rm --name casualgraph-parser \
  --env-file /secure/path/parser.env \
  --memory 4g --cpus 2 --pids-limit 128 \
  --read-only --tmpfs /tmp:rw,noexec,nosuid,size=256m \
  -p 127.0.0.1:8090:8090 casualgraph-document-parser
```

Do not expose this port publicly. Non-loopback deployment requires TLS on a
private address, normally through the operator's private reverse proxy. Use a
certificate whose SAN matches that address, and provide its private CA bundle
to the API when necessary. An internal container network can provide egress
isolation; the exact network/TLS configuration depends on the operator's host.

The worker starts its child and loads both PDF and image pipelines before
readiness succeeds. Missing models fail readiness rather than triggering a
download on a user's first request. Only one request may hold an input body at
a time. A hard conversion timeout terminates the model process and starts a
replacement in the background; readiness remains false while it prewarms.
On Linux, termination also kills the process group so Tesseract subprocesses
cannot survive a timeout as orphaned work.

## API application configuration

| Environment variable | Meaning |
| --- | --- |
| `LEGAL_DOCUMENT_PARSER_URL` | Fixed operator-controlled base URL, e.g. `http://127.0.0.1:8090` or `https://parser.internal`. No path, query, userinfo or fragment. |
| `LEGAL_DOCUMENT_PARSER_TOKEN` | Same secret as the worker. Missing, short or malformed secrets disable requests. |
| `LEGAL_DOCUMENT_PARSER_CA_FILE` | Optional local CA PEM file for private HTTPS; certificate verification stays enabled. |
| `LEGAL_DOCUMENT_PARSER_TIMEOUT_SECONDS` | One upload's shared OCR budget; default 20 seconds, clamped to 1–60. |

The client accepts only loopback hosts, RFC1918 private IPv4 addresses, ULA
IPv6 addresses, and `.internal` hostnames. HTTP is permitted only on loopback;
other accepted hosts require HTTPS. Redirects and environment HTTP proxies are
disabled. There is no user-supplied URL, URL-fetch endpoint, public fallback, or
automatic forwarding to Anthropic/YData. This service runs before contract
text redaction, so it belongs to the operator's trusted processing boundary.
OCR text still passes through the normal redaction and user confirmation flow.
Original pixels are never passed to the legal review model by this adapter.

`ocr_status()` reports configuration, not a claim that a remote worker is
currently ready. `/healthz` requires the same Bearer token as conversion and
returns only protocol version/readiness. Neither endpoint logs source bytes,
original filenames, OCR text, authorization headers or backend tracebacks.
The worker command disables access logging, and the child suppresses SDK and
native subprocess stdout/stderr to keep extracted snippets out of logs.

## Protocol version 1

`POST /v1/parse` accepts a bounded **binary body**, never a URL or filesystem
path. Set `Authorization: Bearer …`, `X-Parser-Protocol: 1`, and one of:
`application/pdf`, `image/png`, `image/jpeg`, `image/tiff`, `image/webp`.
Compressed request bodies are rejected. A successful response looks like:

```json
{
  "version": 1,
  "status": "complete",
  "pages": [{
    "number": 1,
    "width": 600,
    "height": 800,
    "items": [
      {"type": "paragraph", "text": "Payment clause", "bbox": [40, 50, 400, 75]},
      {"type": "table", "bbox": [40, 100, 500, 180], "cells": [
        {"row": 0, "col": 0, "row_span": 1, "col_span": 2,
         "header": true, "text": "Merged heading", "bbox": [40, 100, 500, 130]}
      ]}
    ]
  }],
  "issues": []
}
```

Coordinates are top-left-origin PDF canvas units (normally points), or original
image pixels for image input. Docling's bottom-left coordinates and image DPI
are normalized by the adapter. Rows/columns are zero based; spans are positive.
Table cells are emitted once, without duplicating table-owned text references.
Body and furniture are retained: headers and footnotes are not discarded by a
Markdown export filter. An incomplete conversion or missing source reference
produces `partial`. `complete` means the conversion completed; it is **not a
guarantee of OCR accuracy or that seals/signatures were understood**.

Client helpers:

- `OCRBudget()`: create once for the entire upload, then share it across every
  image/page request. Maximum 4 requests; subsequent regions retain pending
  coverage issues. Do not create a new budget for every Word image.
- `recognize_pdf_pages(data, pages, budget=...)`: one request contains only the
  selected visible pages, at most 4. It remaps results to original page numbers
  and normalized, rotated MediaBox coordinates, including CropBox offsets.
- `recognize_image(data, media_type, budget=...)`: returns individual text/cell
  blocks in original image pixels. Table metadata contains image-local IDs,
  cell IDs, row/column/spans and header flags. Prefix those IDs with the image
  node's ID before attaching to a larger document.
- `parse_pdf(data)`: native PDF text and conservative aligned/ruled tables are
  parsed first. Scans use selected-page OCR; mixed pages use selected image
  crops. Small/decorative images retain explicit unreviewed-image issues.
- `render_pdf_asset(data, asset)`: source crops are lazy; no raster is stored
  in asset metadata. Bitmap allocation is capped at 4 million pixels and 3000
  pixels per side. PDFium rendering is serialized within each API process.

PDF originals remain immutable. Native text does not need to be rasterized
just because a page contains a table. Ambiguous borderless layouts retain text
and a `pdf_table_uncertain` issue. OCR/image blocks are attached once to the
image's `block_ids`; they must not also be rendered as duplicate body nodes.
The normalized structure supports review and locating edits. It does not
promise a reconstructed Word file is a lossless revision of an original PDF.

## Limits and failure behavior

| Boundary | Current limit |
| --- | --- |
| Client and worker binary request | 10 MB |
| Client worker response | 4 MB |
| Selected PDF pages per worker request | 4 |
| Worker image input / estimated per-page OCR raster | 12 million pixels |
| Worker estimated total PDF OCR raster | 24 million pixels |
| Worker output | 1500 items/cells and 120,000 characters |
| Native ruled-table geometry | 1000 raw edges and at most 20,000 possible horizontal/vertical intersections per page |
| Input body upload | 10 seconds, one active request |
| `PARSER_DOCUMENT_TIMEOUT_SECONDS` | Default 18, maximum 55 seconds |
| `PARSER_HARD_TIMEOUT_SECONDS` | Default 20, maximum 60 seconds; kills child |

The API retains every original PDF page even when OCR exceeds its page budget.
Do not silently mark omitted pages as covered. Review and export authorization
remain user decisions; parser warnings are coverage information, not a second
model veto. Source export and preview remain usable when no OCR worker exists.

## Verification and rollout

Regular tests require only the repository's development dependencies:

```sh
python -m pytest -q tests/test_pdf_structure.py tests/test_document_ocr.py tests/test_document_parser_worker.py
```

They exercise real PDF geometry/raster fixtures, merged and borderless tables,
native/scan mixtures, rotation/CropBox mapping, original-byte preservation,
mock HTTP requests/responses, server authentication, parser invocation and the
Docling JSON reference adapter. They do not download or run ML models. When
`docling-core` is installed, the suite also constructs a real `DoclingDocument`
and passes its actual `export_to_dict()` result through the adapter, without
loading Torch or OCR weights.

The `RUN_PRIVATE_DOCLING_SMOKE=1` opt-in test in
`tests/test_document_parser_worker.py` executes the **real pinned SDK** on a
synthetic image. Run it inside the provisioned worker environment with pytest
and that test module available, before enabling the API's worker URL:

```sh
RUN_PRIVATE_DOCLING_SMOKE=1 python -m pytest -q tests/test_document_parser_worker.py -k real_prewarmed
```

This smoke must use the preloaded model bundle and offline flags. A passing
protocol/unit suite alone does not establish OCR readiness or production
accuracy. Evaluate Chinese contract samples with merged cells, mixed native
text/scans, stamps, rotated pages and faint text, then set the worker allocation
and OCR budget from those results.

Upstream contracts used for this adapter:

- [Docling conversion limits, binary streams and offline models](https://docling-project.github.io/docling/usage/advanced_options/)
- [Full-page OCR options](https://docling-project.github.io/docling/_generated/examples/full_page_ocr/)
- [Typed document / table / provenance fields](https://docling-project.github.io/docling/reference/docling_document/)
- [Converter and initialize_pipeline API](https://docling-project.github.io/docling/reference/document_converter/)
- [Docling MIT code license; separate model licenses](https://github.com/docling-project/docling)

Review the licenses and redistribution terms of the exact model bundle along
with the code dependency pins when publishing or updating worker images.
