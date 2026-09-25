import assert from 'node:assert/strict';
import test from 'node:test';
import { verifyLegalRelease } from './verify_legal_release.mjs';

test('preview does not depend on the production backend', async () => {
  assert.deepEqual(await verifyLegalRelease('preview', () => assert.fail('unexpected fetch')), { skipped: true });
});
test('production blocks an absent backend', async () => {
  await assert.rejects(verifyLegalRelease('production', async () => new Response('{}', { status: 404 })), /not ready/);
});
test('production blocks an incompatible or HTML response', async () => {
  await assert.rejects(verifyLegalRelease('production', async () => new Response('{}')), /incompatible/);
  await assert.rejects(verifyLegalRelease('production', async () => new Response('<html>not an API</html>')));
});
test('production proceeds only with the required product version', async () => {
  assert.deepEqual(await verifyLegalRelease('production', async () => Response.json({ product: 'contract-review', version: '1.0.0', max_only: true, model_gateway: 'ydata', model_selection_version: 1 })), { ready: true, version: '1.0.0' });
});

test('production blocks an old backend without Max enforcement', async () => {
  await assert.rejects(verifyLegalRelease('production', async () => Response.json({product:'contract-review',version:'1.0.0'})), /incompatible/);
});
