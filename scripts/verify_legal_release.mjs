import { pathToFileURL } from 'node:url';

/** Preview is independent; production must never outrun its required backend. */
export async function verifyLegalRelease(environment, fetcher = fetch) {
  if (environment !== 'production') return { skipped: true };
  const response = await fetcher('https://casualgraph.fly.dev/legal/version', {
    signal: AbortSignal.timeout(12000), redirect: 'error',
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) throw new Error(`Contract backend not ready (HTTP ${response.status}).`);
  const version = await response.json();
  if (version.product !== 'contract-review' || version.version !== '1.0.0') {
    throw new Error('Contract backend version is incompatible with this frontend.');
  }
  return { ready: true, version: version.version };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    console.log('Legal release gate:', await verifyLegalRelease(process.env.VERCEL_ENV));
  } catch (error) {
    console.error('Production release stopped; the existing website is not replaced.');
    console.error(error instanceof Error ? error.message : 'Backend verification failed.');
    console.error('Complete the authorized Fly backend deployment, then redeploy this Vercel commit.');
    process.exitCode = 1;
  }
}
