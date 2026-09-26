"""Team review: parallel specialists, an independent critic and a whole-contract arbiter.

The team runs on the shared parallel pipeline in review_v2. Specialists never edit the
document and cannot emit another specialist's finding kind; the critic verifies every
task; the arbiter looks for cross-clause conflicts and omissions and checks that the
proposed edits can be adopted together. Models and their outputs confer no permissions.
"""
from __future__ import annotations
import hashlib
import json
from typing import Callable
from legal import review_v2 as v2

COLLABORATION_VERSION = 1
MAX_CALLS_PER_ATTEMPT = 40
MAX_PARALLEL_AGENTS = 3
# The arbiter's compatibility pass over every proposed edit (compact input, no re-review).
ARBITRATE = v2.CROSS_CHECK


def task_topics(task: dict) -> str:
    """Rule titles without the specialist prefix, for progress notes only."""
    return '、'.join(rule['title'].split(' / ', 1)[-1] for rule in task['rules'])


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def block_conflicting_edits(findings: list[dict]) -> None:
    targets: dict[str, set[str]] = {}
    for f in findings:
        if f.get('block_id') and f.get('suggested_text') and f.get('verification_status') == 'supported':
            targets.setdefault(f['block_id'], set()).add(f['suggested_text'])
    for f in findings:
        if len(targets.get(f.get('block_id'), set())) > 1:
            f.update(revision_allowed=False, needs_confirmation=True, conflict_group=f['block_id'],
                     cross_edit_status='conflict', cross_edit_note='多个 Agent 对同一段提出不同修改，请人工合并后重新审查。')


def run_review(rid: str, *, model: Callable | None = None, retrieve: Callable | None = None,
               authorize: Callable | None = None) -> None:
    return v2.run_review(rid, model=model, retrieve=retrieve, authorize=authorize, team=True)
