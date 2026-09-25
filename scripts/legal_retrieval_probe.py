"""Public-query live retrieval diagnostic; never uses a contract or model credential."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from legal.external_law import retrieve_law
result=retrieve_law('民法典 第五百零六条 第五百八十五条 免责 违约金', ['免责','违约金'])
summary={k:result.get(k) for k in ('provider','status','warnings','discovery_status','direct_official_fallback')}
summary['sources']=[{k:s.get(k) for k in ('url','title','retrieved_at','content_hash','source_status','version_status','source_kind','discovery')} for s in result['sources']]
Path('legal-retrieval-probe.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
print(json.dumps(summary,ensure_ascii=False,indent=2))
if not result['sources']:
    print('::warning::Live external search did not produce a readable official source. Legal findings remain unverified; configure an approved search provider and retry.')

# Release-time operators may explicitly require sources. CI remains an honest
# network diagnostic rather than declaring substantive legal correctness.
if '--require-source' in sys.argv and not result['sources']:
    raise SystemExit(1)
