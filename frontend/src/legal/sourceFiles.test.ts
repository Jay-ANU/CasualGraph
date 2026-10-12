import { afterEach, describe, expect, it, vi } from 'vitest';
import { sourceBlob } from './sourceFiles';

afterEach(() => vi.unstubAllGlobals());

describe('authenticated local original assets', () => {
  it('sends the bearer in headers and returns bytes without a credential-bearing URL', async () => {
    vi.stubGlobal('localStorage', { getItem: () => 'synthetic-token' });
    const fetch = vi.fn().mockResolvedValue(new Response(new Uint8Array([137, 80, 78, 71]), { headers: { 'Content-Type': 'image/png' } }));
    vi.stubGlobal('fetch', fetch);
    expect((await sourceBlob('/legal/contracts/c1/assets/a1', 'image')).type).toBe('image/png');
    const [url, init] = fetch.mock.calls[0];
    expect(url).not.toContain('synthetic-token');
    expect(new Headers(init.headers).get('Authorization')).toBe('Bearer synthetic-token');
  });
  it.each(['text/html', 'image/svg+xml', 'application/xml'])('does not embed an active %s response as an image', async type => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('<script>test</script>', { headers: { 'Content-Type': type } })));
    await expect(sourceBlob('/legal/contracts/c1/assets/a1', 'image')).rejects.toThrow('unsupported');
  });
  it('rejects failed or wrong-type originals and passes abort signals through', async () => {
    const signal = new AbortController().signal;
    const fetch = vi.fn().mockResolvedValueOnce(new Response('denied', { status: 403 }))
      .mockResolvedValueOnce(new Response('html', { headers: { 'Content-Type': 'text/html' } }))
      .mockResolvedValueOnce(new Response('%PDF-1.4', { headers: { 'Content-Type': 'application/pdf' } }));
    vi.stubGlobal('fetch', fetch);
    await expect(sourceBlob('/legal/contracts/c1/original', 'pdf', signal)).rejects.toThrow('unavailable');
    await expect(sourceBlob('/legal/contracts/c1/original', 'pdf')).rejects.toThrow('unsupported');
    expect((await sourceBlob('/legal/contracts/c1/original', 'pdf')).type).toBe('application/pdf');
    expect(fetch.mock.calls[0][1].signal).toBe(signal);
  });
});
