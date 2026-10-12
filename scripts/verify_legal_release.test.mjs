import assert from 'node:assert/strict';
import test from 'node:test';
import { verifyLegalRelease } from './verify_legal_release.mjs';
const current={product:'contract-review',version:'1.0.0',max_only:true,model_gateway:'mixed',model_selection_version:2,review_engine_version:2,document_structure_version:1,followup_questions:true,collaboration_version:1,audit_foundation_version:1,draft_release_version:2,transaction_brief_version:1,evidence_screening_version:1,scenario_catalog_version:1};
test('preview does not depend on production backend',async()=>assert.deepEqual(await verifyLegalRelease('preview',()=>assert.fail('unexpected network request')),{skipped:true}));
test('production rejects unavailable backend',async()=>assert.rejects(verifyLegalRelease('production',async()=>new Response('{}',{status:404})),/not ready/));
test('production rejects HTML',async()=>assert.rejects(verifyLegalRelease('production',async()=>new Response('<html>not an API</html>'))));
test('production proceeds with full v2 contract',async()=>assert.deepEqual(await verifyLegalRelease('production',async()=>Response.json(current)),{ready:true,version:'1.0.0'}));
for(const field of ['max_only','model_gateway','model_selection_version','review_engine_version','document_structure_version','followup_questions','collaboration_version','audit_foundation_version','draft_release_version','transaction_brief_version','evidence_screening_version','scenario_catalog_version']) {
  test(`production requires ${field}`,async()=>{const stale={...current};delete stale[field];await assert.rejects(verifyLegalRelease('production',async()=>Response.json(stale)),/incompatible/);});
}
test('production rejects legacy engine',async()=>assert.rejects(verifyLegalRelease('production',async()=>Response.json({...current,review_engine_version:1})),/incompatible/));
test('production rejects YData-only consent routing',async()=>assert.rejects(verifyLegalRelease('production',async()=>Response.json({...current,model_gateway:'ydata',model_selection_version:1})),/incompatible/));
test('production rejects the former model-approved export gate',async()=>assert.rejects(verifyLegalRelease('production',async()=>Response.json({...current,draft_release_version:1})),/incompatible/));
