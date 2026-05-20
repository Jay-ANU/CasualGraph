"""PDF parsing helpers for ESG reports."""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader


def parse_pdf(pdf_path: str) -> str:
    """Extract plain text from a PDF, preserving page breaks as newlines."""
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")

    try:
        reader = PdfReader(str(path))
    except Exception as exc:
        raise RuntimeError(f"Failed to open PDF {path}: {exc}") from exc

    pages = []
    try:
        for page in reader.pages:
            pages.append((page.extract_text() or "").strip())
    except Exception as exc:
        raise RuntimeError(f"Failed to extract text from PDF {path}: {exc}") from exc

    text = "\n\n".join(page for page in pages if page).strip()
    if not text:
        raise RuntimeError(f"No extractable text found in PDF: {path}")
    return text
