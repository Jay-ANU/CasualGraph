import type { RagStreamEvent } from '../types/api';
import { openEventStream, readSseEvents } from './sse';

const streamOf = (...chunks: string[]) =>
  new Response(
    new ReadableStream<Uint8Array>({
      start(controller) {
        const encoder = new TextEncoder();
        chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)));
        controller.close();
      },
    }),
  );

describe('readSseEvents', () => {
  it('reads frames split across chunks and skips heartbeat comments', async () => {
    const events: RagStreamEvent[] = [];
    await readSseEvents(
      streamOf(
        'data: {"type":"token","te',
        'xt":"Hel"}\n\n: heartbeat\n\n',
        'data: {"type":"done","payload":{"answer":"Hello","sources":[],"backend":"test"}}\n\n',
      ),
      (event) => events.push(event),
    );
    expect(events).toEqual([
      { type: 'token', text: 'Hel' },
      { type: 'done', payload: { answer: 'Hello', sources: [], backend: 'test' } },
    ]);
  });
});

describe('openEventStream', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('posts the JSON body and throws an ApiError before reading a failed stream', async () => {
    const fetchMock = vi.fn<typeof fetch>(async () =>
      new Response(JSON.stringify({ detail: 'Daily limit reached' }), { status: 429 }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await expect(openEventStream('/rag/ask/stream', { question: 'q' })).rejects.toMatchObject({
      status: 429,
      message: 'Daily limit reached',
    });
    const init = fetchMock.mock.calls[0][1];
    expect(init?.method).toBe('POST');
    expect(init?.body).toBe('{"question":"q"}');
  });
});
