"""Review skills: maintained review guidance that steers what the model checks.

A skill is a folder under legal/skills/ holding a SKILL.md: YAML front matter that says when
the skill applies and where its text came from, then a Markdown body of review guidance
(what to check, common pitfalls, how to word a fix). Skills are guidance, not legal
authority: statutes still go through law_refs and official-text matching, and the contract
text and the rules of the review prevail over a skill.

Only skills with status "active" are ever used. Imported or rewritten skills start as
"draft" until a lawyer approves them. Selection is deterministic (always-on skills, the
contract scenario, words in the redacted contract) and bounded per review tier, and each
review stores the exact skills it used (id, version, content hash, reason) so every result
can be traced to the guidance that shaped it.
"""
from __future__ import annotations

import hashlib
import logging
import re
from functools import lru_cache
from pathlib import Path

import yaml

SKILLS_DIR = Path(__file__).resolve().parent / 'skills'
VERSION = 1
TIERS = ('ultra_fast', 'fast', 'standard', 'deep')
STATUSES = ('active', 'draft')
ORIGINS = ('in-house', 'adapted', 'imported')
# Characters of guidance a review may carry: faster tiers keep prompts short.
BUDGET = {'ultra_fast': 4000, 'fast': 6000, 'standard': 9000, 'deep': 12000}
MAX_SKILLS = 4
MAX_GUIDANCE = 6000
NOTICE = '审查技能是经维护的审查方法与检查清单，用于提示检查要点，不是法律依据；法律依据仍以官方原文核对为准。'
_ID = re.compile(r'^[a-z0-9][a-z0-9-]{1,62}$')
log = logging.getLogger(__name__)


class SkillError(ValueError):
    pass


def _strings(value, field: str, limit: int = 40) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
        raise SkillError(f'{field} must be a list of non-empty strings')
    return list(dict.fromkeys(v.strip() for v in value))[:limit]


def parse(path: Path) -> dict:
    """One SKILL.md, validated. Raises SkillError with the first problem found."""
    raw = path.read_text(encoding='utf-8')
    if not raw.startswith('---\n'):
        raise SkillError('missing front matter')
    head, sep, body = raw[4:].partition('\n---\n')
    if not sep:
        raise SkillError('unterminated front matter')
    try:
        meta = yaml.safe_load(head)
    except yaml.YAMLError as exc:
        raise SkillError(f'front matter is not valid YAML: {exc}') from None
    if not isinstance(meta, dict):
        raise SkillError('front matter must be a mapping')
    skill_id = str(meta.get('id') or '')
    if not _ID.match(skill_id) or skill_id != path.parent.name:
        raise SkillError('id must be a lowercase slug equal to the folder name')
    name, description = str(meta.get('name') or '').strip(), str(meta.get('description') or '').strip()
    if not name or not description or len(name) > 40 or len(description) > 300:
        raise SkillError('name (40) and description (300) are required')
    status = meta.get('status', 'draft')
    if status not in STATUSES:
        raise SkillError(f'status must be one of {STATUSES}')
    applies = meta.get('applies_to') or {}
    if not isinstance(applies, dict):
        raise SkillError('applies_to must be a mapping')
    tiers = _strings(meta.get('tiers'), 'tiers') or list(TIERS)
    if any(t not in TIERS for t in tiers):
        raise SkillError(f'tiers must be among {TIERS}')
    min_hits = applies.get('min_keyword_hits', 1)
    if not isinstance(min_hits, int) or min_hits < 1:
        raise SkillError('applies_to.min_keyword_hits must be a positive integer')
    source = meta.get('source') or {}
    if not isinstance(source, dict) or source.get('origin') not in ORIGINS:
        raise SkillError(f'source.origin must be one of {ORIGINS}')
    if source['origin'] != 'in-house' and not (source.get('repo') and source.get('license')):
        raise SkillError('adapted or imported skills must name their source repo and license')
    guidance = body.strip()
    if not guidance or len(guidance) > MAX_GUIDANCE:
        raise SkillError(f'guidance must be 1-{MAX_GUIDANCE} characters')
    reviewed = meta.get('reviewed') or {}
    return {'id': skill_id, 'name': name, 'description': description, 'version': str(meta.get('version') or '1.0.0'),
            'status': status, 'tiers': tiers, 'always': applies.get('always') is True,
            'scenarios': _strings(applies.get('scenarios'), 'applies_to.scenarios'),
            'keywords': _strings(applies.get('keywords'), 'applies_to.keywords'), 'min_keyword_hits': min_hits,
            'source': {k: str(v) for k, v in source.items() if k in ('origin', 'repo', 'commit', 'path', 'license', 'note')},
            'reviewed': {k: str(v) for k, v in reviewed.items() if k in ('by', 'date')} if isinstance(reviewed, dict) else {},
            'guidance': guidance, 'sha256': hashlib.sha256(raw.encode()).hexdigest()}


@lru_cache(maxsize=4)
def _load(root: str) -> tuple[dict, ...]:
    skills = []
    for path in sorted(Path(root).glob('*/SKILL.md')):
        try:
            skills.append(parse(path))
        except (SkillError, OSError, UnicodeDecodeError) as exc:
            # A broken skill is left out, never allowed to stop a review.
            log.warning('legal skill %s skipped: %s', path.parent.name, exc)
    return tuple(skills)


def load(root: Path = SKILLS_DIR) -> list[dict]:
    return list(_load(str(root)))


def reload() -> None:
    _load.cache_clear()


def select(profile: dict, blocks: list[dict], tier: str, *, root: Path = SKILLS_DIR) -> list[dict]:
    """Active skills for this review, strongest match first, within the tier's budget."""
    tier = tier if tier in TIERS else 'standard'
    scenario = (profile.get('scenario') or {}).get('id') or ''
    label = (profile.get('scenario') or {}).get('label') or ''
    text = '\n'.join(b.get('text', '') for b in blocks)
    ranked = []
    for skill in load(root):
        if skill['status'] != 'active' or tier not in skill['tiers']:
            continue
        hits = [k for k in skill['keywords'] if k in text]
        reasons, score = [], 0
        if skill['always']:
            score, reasons = score + 100, reasons + ['通用审查方法']
        if scenario and scenario in skill['scenarios']:
            score, reasons = score + 50, reasons + [f'合同场景：{label or scenario}']
        if len(hits) >= skill['min_keyword_hits']:
            score, reasons = score + min(40, 10 * len(hits)), reasons + ['合同涉及：' + '、'.join(hits[:5])]
        if score:
            ranked.append((score, skill['id'], skill, '；'.join(reasons)))
    ranked.sort(key=lambda row: (-row[0], row[1]))
    budget, chosen = BUDGET[tier], []
    for _, _, skill, reason in ranked:
        if len(chosen) >= MAX_SKILLS:
            break
        if len(skill['guidance']) > budget:
            continue
        budget -= len(skill['guidance'])
        chosen.append({'id': skill['id'], 'name': skill['name'], 'version': skill['version'], 'sha256': skill['sha256'],
                       'reason': reason, 'guidance': skill['guidance'],
                       'source': {k: skill['source'][k] for k in ('origin', 'license', 'repo') if k in skill['source']}})
    return chosen


def prompt_items(selected: list[dict] | None) -> list[dict]:
    """What the model sees: name and guidance only."""
    return [{'name': s['name'], 'guidance': s['guidance']} for s in selected or [] if s.get('guidance')]


def public(selected: list[dict] | None) -> list[dict]:
    """What the review API shows: provenance without the guidance text."""
    return [{k: s[k] for k in ('id', 'name', 'version', 'reason', 'source') if k in s} for s in selected or []]


def catalog(root: Path = SKILLS_DIR) -> dict:
    skills = load(root)
    return {'version': VERSION, 'notice': NOTICE,
            'skills': [{k: s[k] for k in ('id', 'name', 'description', 'version', 'status', 'scenarios', 'tiers', 'source', 'reviewed')}
                       | {'always': s['always']} for s in skills if s['status'] == 'active'],
            'drafts': sum(s['status'] == 'draft' for s in skills)}
