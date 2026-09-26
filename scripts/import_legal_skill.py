"""Bring an external SKILL.md (e.g. from a GitHub skills repository) in as a draft review skill.

    python scripts/import_legal_skill.py --source path/to/SKILL.md --path plugins/x/SKILL.md \
        --repo https://github.com/owner/repo --commit <sha> --license Apache-2.0 [--id my-skill]

The skill is written to legal/skills/<id>/SKILL.md with status "draft" and no applies_to
rules, so reviews never use it until a lawyer has checked the content, condensed it to review
guidance, set applies_to and changed the status to "active". The source repository, commit,
path and license are recorded. Only permissive licenses are accepted; a skill without a
license file in its repository cannot be imported.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from legal import skill_registry as registry  # noqa: E402

LICENSES = ('Apache-2.0', 'MIT', 'BSD-2-Clause', 'BSD-3-Clause', 'CC-BY-4.0')


def slug(value: str) -> str:
    return re.sub(r'-{2,}', '-', re.sub(r'[^a-z0-9-]', '-', value.lower())).strip('-')[:62]


def build(source: Path, repo: str, commit: str, license_id: str, skill_id: str | None, repo_path: str | None = None) -> tuple[str, str]:
    """(skill id, SKILL.md text). Raises ValueError with the reason an import is refused."""
    if license_id not in LICENSES:
        raise ValueError(f'license {license_id!r} is not on the permissive list {LICENSES}')
    if not re.fullmatch(r'https://github\.com/[\w.-]+/[\w.-]+', repo) or not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('give the GitHub repository URL and the full 40-character commit SHA')
    raw = source.read_text(encoding='utf-8')
    meta, body = {}, raw
    if raw.startswith('---\n') and '\n---\n' in raw[4:]:
        head, _, body = raw[4:].partition('\n---\n')
        meta = yaml.safe_load(head) or {}
    body = body.strip()
    name = str(meta.get('name') or source.parent.name).strip()
    skill_id = slug(skill_id or name)
    if len(skill_id) < 2:
        raise ValueError('give --id: the source name does not make a usable id')
    if not body or len(body) > registry.MAX_GUIDANCE:
        raise ValueError(f'guidance must be 1-{registry.MAX_GUIDANCE} characters; condense the skill before importing')
    front = {'id': skill_id, 'name': name[:40], 'description': str(meta.get('description') or name).strip()[:300],
             'version': '0.1.0', 'status': 'draft', 'applies_to': {},
             'source': {'origin': 'imported', 'repo': repo, 'commit': commit, 'path': repo_path or f'{source.parent.name}/{source.name}',
                        'license': license_id}}
    text = '---\n' + yaml.safe_dump(front, allow_unicode=True, sort_keys=False) + '---\n' + body + '\n'
    return skill_id, text


def main(argv: list[str] | None = None, root: Path = registry.SKILLS_DIR) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--license', required=True, dest='license_id')
    parser.add_argument('--id', dest='skill_id')
    parser.add_argument('--path', dest='repo_path', help='path of the file inside the source repository')
    args = parser.parse_args(argv)
    try:
        skill_id, text = build(args.source, args.repo, args.commit, args.license_id, args.skill_id, args.repo_path)
    except (ValueError, OSError, yaml.YAMLError) as exc:
        print(f'not imported: {exc}', file=sys.stderr)
        return 1
    target = root / skill_id / 'SKILL.md'
    if target.exists():
        print(f'not imported: {target} already exists', file=sys.stderr)
        return 1
    target.parent.mkdir(parents=True)
    target.write_text(text, encoding='utf-8')
    registry.parse(target)  # the written file must load
    print(f'imported as draft: {target}\nNext: have a lawyer check it, set applies_to, then set status: active.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
