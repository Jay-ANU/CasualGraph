"""Text cleaning for ESG reports without aggressive information loss."""

from __future__ import annotations

from collections import Counter
import re


def clean_text(text: str) -> str:
    """Remove repeated boilerplate and normalize whitespace."""
    if not text:
        return ""

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.strip() for line in normalized.split("\n")]

    non_empty_lines = [line for line in lines if line]
    counts = Counter(non_empty_lines)

    cleaned_lines = []
    for line in lines:
        if not line:
            cleaned_lines.append("")
            continue

        # Drop short repeated headers/footers that occur many times.
        if counts[line] >= 3 and len(line) < 80:
            continue

        # Keep lines containing numerics, percentages, years, or common ESG markers.
        cleaned_lines.append(line)

    cleaned = "\n".join(cleaned_lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    return cleaned.strip()
