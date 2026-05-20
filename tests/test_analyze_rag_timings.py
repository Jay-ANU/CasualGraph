from __future__ import annotations

from pathlib import Path

import scripts.analyze_rag_timings as timings_script


def test_parse_log_and_group_by_strategy(tmp_path):
    log_path = tmp_path / "rag.log"
    log_path.write_text(
        "\n".join(
            [
                "2026-05-15 10:00:00 [rag.timing] mode=ask strategy=hybrid timings_ms={'rewrite': 10, 'route': 5, 'retrieval': 100, 'graph': 20, 'generate': 40, 'total': 175}",
                "2026-05-15 10:01:00 [rag.timing] mode=ask strategy=hybrid timings_ms={'rewrite': 12, 'route': 6, 'retrieval': 120, 'graph': 25, 'generate': 45, 'total': 208}",
                "2026-05-15 10:02:00 [rag.timing] subq=0 took_ms=1234",
                "2026-05-15 10:03:00 [rag.timing] mode=ask strategy=layered timings_ms={'rewrite': 9, 'route': 4, 'retrieval': 300, 'graph': 30, 'generate': 60, 'total': 403}",
            ]
        ),
        encoding="utf-8",
    )

    entries, since_applied = timings_script.parse_log(log_path)
    report = timings_script.build_report(entries)

    assert since_applied is False
    assert len(entries) == 3
    assert "## Timing breakdown (strategy=hybrid, n=2)" in report
    assert "## Timing breakdown (strategy=layered, n=1)" in report
    assert "| retrieval | 2 | 100 | 120 | 120 | 110 | 120 |" in report


def test_since_filter_is_applied_when_timestamps_exist(tmp_path):
    log_path = tmp_path / "rag.log"
    log_path.write_text(
        "\n".join(
            [
                "2026-05-15 09:59:00 [rag.timing] mode=ask strategy=hybrid timings_ms={'rewrite': 10, 'route': 5, 'retrieval': 100, 'graph': 20, 'generate': 40, 'total': 175}",
                "2026-05-15 10:01:00 [rag.timing] mode=ask strategy=hybrid timings_ms={'rewrite': 12, 'route': 6, 'retrieval': 120, 'graph': 25, 'generate': 45, 'total': 208}",
            ]
        ),
        encoding="utf-8",
    )

    since = timings_script._parse_since_arg("2026-05-15 10:00")
    entries, since_applied = timings_script.parse_log(log_path, since=since)

    assert since_applied is True
    assert len(entries) == 1
    assert entries[0]["timings_ms"]["total"] == 208.0


def test_main_prints_note_when_since_cannot_be_applied(tmp_path, monkeypatch, capsys):
    log_path = tmp_path / "rag.log"
    log_path.write_text(
        "[rag.timing] mode=ask strategy=hybrid timings_ms={'rewrite': 10, 'route': 5, 'retrieval': 100, 'graph': 20, 'generate': 40, 'total': 175}\n",
        encoding="utf-8",
    )

    monkeypatch.setattr("sys.argv", ["analyze_rag_timings.py", str(log_path), "--since", "2026-05-15 10:00"])

    assert timings_script.main() == 0
    output = capsys.readouterr().out
    assert "no parseable timestamps found" in output
    assert "## Timing breakdown (strategy=hybrid, n=1)" in output
