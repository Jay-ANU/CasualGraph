import assert from 'node:assert/strict';
import test from 'node:test';
import { verifyLegalRelease } from './verify_legal_release.mjs';
const current={product:'contract-review',version:'1.0.0',max_only:true,model_gateway:'ydata',model_selection_version:1,review_engine_version:2,followup_questions:true,collaboration_version:1};
test('preview does not depend on production backend',async()=>assert.deepEqual(await verifyLegalRelease('preview',()=>assert.fail('unexpected network request')),{skipped:true}));
test('production rejects unavailable backend',async()=>assert.rejects(verifyLegalRelease('production',async()=>new Response('{}',{status:404})),/not ready/));
test('production rejects HTML',async()=>assert.rejects(verifyLegalRelease('production',async()=>new Response('<html>not an API</html>'))));
test('production proceeds with full v2 contract',async()=>assert.deepEqual(await verifyLegalRelease('production',async()=>Response.json(current)),{ready:true,version:'1.0.0'}));
for(const field of ['max_only','model_gateway','model_selection_version','review_engine_version','followup_questions','collaboration_version']) {
  test(`production requires ${field}`,async()=>{const stale={...current};delete stale[field];await assert.rejects(verifyLegalRelease('production',async()=>Response.json(stale)),/incompatible/);});
}
test('production rejects legacy engine',async()=>assert.rejects(verifyLegalRelease('production',async()=>Response.json({...current,review_engine_version:1})),/incompatible/));
