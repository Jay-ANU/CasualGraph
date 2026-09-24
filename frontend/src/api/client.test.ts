import { ApiError, apiFetch, readApiError } from './client';

const jsonResponse = (status: number, body: unknown, statusText = '') =>
  new Response(JSON.stringify(body), { status, statusText, headers: { 'Content-Type': 'application/json' } });

describe('readApiError', () => {
  it('keeps the server message and its error code', async () => {
    const error = await readApiError(jsonResponse(503, { error: 'chat_memory_unavailable', message: 'chat session not found' }));
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 503, code: 'chat_memory_unavailable', message: 'chat session not found' });
  });

  it('reads FastAPI detail strings and detail objects', async () => {
    expect((await readApiError(jsonResponse(404, { detail: 'Chat session not found' }))).message).toBe('Chat session not found');
    expect(await readApiError(jsonResponse(400, { detail: { error: 'bad_scope', message: 'Too many documents' } })))
      .toMatchObject({ code: 'bad_scope', message: 'Too many documents' });
  });

  it('explains the no-documents error in plain language', async () => {
    const error = await readApiError(jsonResponse(404, { error: 'no_accessible_documents' }));
    expect(error.code).toBe('no_accessible_documents');
    expect(error.message).toMatch(/^No searchable documents/);
  });

  it('points at VITE_API_BASE for an HTML reply and falls back to the status line', async () => {
    const html = await readApiError(new Response('<!DOCTYPE html><html></html>', { status: 404, statusText: 'Not Found' }));
    expect(html.message).toContain('VITE_API_BASE');
    const empty = await readApiError(new Response('', { status: 500, statusText: 'Internal Server Error' }));
    expect(empty.message).toBe('The server returned 500 Internal Server Error.');
  });
});

describe('apiFetch', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  it('prefixes the API base, sends the stored token and parses JSON', async () => {
    vi.stubEnv('VITE_API_BASE', 'https://api.example.test/');
    vi.stubGlobal('localStorage', { getItem: (key: string) => (key === 'token' ? 'secret' : null) });
    const fetchMock = vi.fn<typeof fetch>(async () => jsonResponse(200, { documents: [] }));
    vi.stubGlobal('fetch', fetchMock);

    await expect(apiFetch('/documents')).resolves.toEqual({ documents: [] });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('https://api.example.test/documents');
    expect(new Headers(init?.headers).get('Authorization')).toBe('Bearer secret');
  });

  it('keeps an explicit Authorization header and sends none without a token', async () => {
    vi.stubGlobal('localStorage', { getItem: () => null });
    const fetchMock = vi.fn<typeof fetch>(async () => jsonResponse(200, {}));
    vi.stubGlobal('fetch', fetchMock);

    await apiFetch('/auth/me', { headers: { Authorization: 'Bearer explicit' } });
    await apiFetch('/models/status');
    expect(new Headers(fetchMock.mock.calls[0][1]?.headers).get('Authorization')).toBe('Bearer explicit');
    expect(new Headers(fetchMock.mock.calls[1][1]?.headers).has('Authorization')).toBe(false);
  });

  it('throws an ApiError carrying the status', async () => {
    vi.stubGlobal('fetch', vi.fn<typeof fetch>(async () => jsonResponse(409, { detail: 'Feedback already recorded' })));
    await expect(apiFetch('/feedback', { method: 'POST' })).rejects.toMatchObject({
      name: 'ApiError',
      status: 409,
      message: 'Feedback already recorded',
    });
  });
});
