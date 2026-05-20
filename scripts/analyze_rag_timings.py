"""Analyze `[rag.timing]` log lines and summarize latency by strategy."""

from __future__ import annotations

import argparse
import ast
from collections import defaultdict
from datetime import datetime
from pathlib import Path
import math
import re
from typing import Dict, Iterable, List, Optional, Tuple

_TIMING_LINE_PATTERN = re.compile(
    r"\[rag\.timing\]\s+mode=(?P<mode>\S+)\s+strategy=(?P<strategy>\S+)\s+timings_ms=(?P<timings>\{.*\})"
)
_TIMESTAMP_PATTERNS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d %H:%M:%S,%f",
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S.%f",
)
_STAGES = ("rewrite", "route", "retrieval", "graph", "generate", "total")


def parse_log(path: Path, *, strategy: str = "", since: Optional[datetime] = None) -> Tuple[List[Dict], bool]:
    entries: List[Dict] = []
    since_applied = False
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        parsed = _parse_timing_line(raw_line)
        if parsed is None:
            continue
        if strategy and parsed["strategy"] != strategy:
            continue
        timestamp = parsed.get("timestamp")
        if since is not None:
            if timestamp is not None:
                since_applied = True
                if timestamp < since:
                    continue
        entries.append(parsed)
    return entries, since_applied


def build_report(entries: List[Dict], *, selected_strategy: str = "") -> str:
    if not entries:
        suffix = f" (strategy={selected_strategy})" if selected_strategy else ""
        return f"No timing entries found{suffix}"

    grouped: Dict[str, List[Dict]] = defaultdict(list)
    for entry in entries:
        grouped[str(entry["strategy"])].append(entry)

    sections = []
    for strategy_name in sorted(grouped):
        rows = grouped[strategy_name]
        sections.append(_render_strategy_table(strategy_name=strategy_name, entries=rows))
    return "\n\n".join(sections)


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze `[rag.timing]` log lines by retrieval strategy.")
    parser.add_argument("logfile", help="Path to the backend log file.")
    parser.add_argument("--strategy", default="", help="Only include one retrieval strategy.")
    parser.add_argument(
        "--since",
        default="",
        help="Optional lower-bound timestamp, e.g. '2026-05-15 10:00'. Applied only when log lines carry timestamps.",
    )
    args = parser.parse_args()

    log_path = Path(args.logfile)
    if not log_path.exists():
        print(f"Log file not found: {log_path}")
        return 1

    since_dt = _parse_since_arg(args.since) if args.since else None
    entries, since_applied = parse_log(log_path, strategy=args.strategy.strip(), since=since_dt)
    if since_dt is not None and not since_applied:
        print(f"Note: no parseable timestamps found in {log_path}; --since filter was not applied.\n")
    print(build_report(entries, selected_strategy=args.strategy.strip()))
    return 0


def _parse_timing_line(line: str) -> Optional[Dict]:
    match = _TIMING_LINE_PATTERN.search(line)
    if match is None:
        return None
    try:
        timings = ast.literal_eval(match.group("timings"))
    except Exception:
        return None
    if not isinstance(timings, dict):
        return None
    normalized = {}
    for stage in _STAGES:
        value = timings.get(stage)
        if value is None:
            continue
        normalized[stage] = float(value)
    if "total" not in normalized:
        return None
    return {
        "mode": match.group("mode"),
        "strategy": match.group("strategy"),
        "timings_ms": normalized,
        "timestamp": _extract_timestamp(line),
    }


def _extract_timestamp(line: str) -> Optional[datetime]:
    stripped = line.strip()
    candidates = []
    if len(stripped) >= 19:
        candidates.append(stripped[:19])
    if len(stripped) >= 23:
        candidates.append(stripped[:23])
    if len(stripped) >= 26:
        candidates.append(stripped[:26])
    seen = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        for fmt in _TIMESTAMP_PATTERNS:
            try:
                return datetime.strptime(candidate, fmt)
            except ValueError:
                continue
    return None


def _parse_since_arg(raw: str) -> datetime:
    cleaned = str(raw or "").strip()
    for fmt in _TIMESTAMP_PATTERNS:
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    raise SystemExit(f"Invalid --since value: {raw!r}")


def _render_strategy_table(*, strategy_name: str, entries: List[Dict]) -> str:
    lines = [f"## Timing breakdown (strategy={strategy_name}, n={len(entries)})"]
    lines.append("| stage | count | p50 | p90 | p99 | mean | max | % of total |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    totals = [float(item["timings_ms"].get("total") or 0.0) for item in entries]
    for stage in _STAGES:
        values = [float(item["timings_ms"].get(stage) or 0.0) for item in entries if stage in item["timings_ms"]]
        if not values:
            continue
        pct_value = "-"
        if stage != "total":
            ratios = []
            for item in entries:
                total = float(item["timings_ms"].get("total") or 0.0)
                stage_value = float(item["timings_ms"].get(stage) or 0.0)
                if total > 0.0:
                    ratios.append((stage_value / total) * 100.0)
            pct_value = _fmt_number(sum(ratios) / len(ratios)) + "%"
        lines.append(
            "| {stage} | {count} | {p50} | {p90} | {p99} | {mean} | {max_value} | {pct} |".format(
                stage=stage,
                count=len(values),
                p50=_fmt_number(_percentile(values, 50)),
                p90=_fmt_number(_percentile(values, 90)),
                p99=_fmt_number(_percentile(values, 99)),
                mean=_fmt_number(sum(values) / len(values)),
                max_value=_fmt_number(max(values)),
                pct=pct_value,
            )
        )
    if totals:
        lines.append("")
        lines.append(f"Total samples: {len(totals)}")
    return "\n".join(lines)


def _percentile(values: Iterable[float], percentile: int) -> float:
    ordered = sorted(float(item) for item in values)
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return ordered[0]
    rank = math.ceil((percentile / 100.0) * len(ordered))
    index = min(max(rank - 1, 0), len(ordered) - 1)
    return ordered[index]


def _fmt_number(value: float) -> str:
    rounded = round(float(value), 2)
    if rounded.is_integer():
        return str(int(rounded))
    return f"{rounded:.2f}".rstrip("0").rstrip(".")


if __name__ == "__main__":
    raise SystemExit(main())
