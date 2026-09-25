import { apiBase as restoredApiBase } from '../api/config';
import { withAuth } from '../api/client';
import React, { useEffect, useMemo, useState } from 'react';
import { Loader2 } from 'lucide-react';
import type { RagResponse, RagStreamEvent } from '../types/api';
import useDocumentTitle from '../utils/useDocumentTitle';

type HealthState = {
  label: string;
  url: string;
  ok: boolean | null;
  detail: string;
};

const SAMPLE_TEXT = `NVIDIA's FY2025 sustainability update states that the company remains committed to reducing greenhouse gas emissions across operations and its value chain.

In 2024, NVIDIA reported a 14% reduction in scope 2 market-based emissions. The company also expanded renewable energy procurement and set a target to reach 100% renewable electricity for selected sites.

The board's governance policy requires quarterly oversight of climate risk and data center safety topics. Management identified transition risk associated with energy demand growth in data centers.`;

const SAMPLE_QUESTION = 'What renewable electricity target and emissions change did NVIDIA report?';

const readSseEvents = async (
  response: Response,
  onEvent: (event: RagStreamEvent) => void,
): Promise<void> => {
  if (!response.body) {
    throw new Error('Streaming response body is empty');
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    const frames = buffer.split('\n\n');
    buffer = frames.pop() || '';
    for (const frame of frames) {
      const trimmed = frame.trim();
      if (!trimmed || trimmed.startsWith(':')) continue;
      const dataLine = trimmed.split('\n').find((line) => line.startsWith('data:'));
      if (!dataLine) continue;
      const payload = dataLine.slice(5).trim();
      if (!payload) continue;
      onEvent(JSON.parse(payload) as RagStreamEvent);
    }
    if (done) break;
  }
};

const EsgDemo: React.FC = () => {
  const host = useMemo(() => window.location.hostname || '127.0.0.1', []);
  const localApiHost = host === 'localhost' || host === '127.0.0.1';
  const esgApiBase = restoredApiBase() || (localApiHost ? `http://${host}:8000` : '');
  const platformApiBase = esgApiBase;

  const [health, setHealth] = useState<HealthState[]>([
    { label: 'Evidence API', url: `${esgApiBase}/health`, ok: null, detail: 'Checking...' },
    { label: 'Application API', url: `${platformApiBase}/`, ok: null, detail: 'Checking...' },
  ]);

  const [extractText, setExtractText] = useState(SAMPLE_TEXT);
  const extractResult: { entities?: unknown[]; relations?: unknown[] } = {};

  const [question, setQuestion] = useState(SAMPLE_QUESTION);
  const [ragLoading, setRagLoading] = useState(false);
  const [ragResult, setRagResult] = useState<(Partial<RagResponse> & { error?: string; message?: string }) | null>(null);
  const [activeDemoTab, setActiveDemoTab] = useState<'ask' | 'extract'>('ask');
  useDocumentTitle('Pipeline check');

  const serviceTargets = useMemo(
    () => [
      { label: 'Evidence API', url: `${esgApiBase}/health`, ok: null, detail: 'Checking...' },
      { label: 'Application API', url: `${platformApiBase}/`, ok: null, detail: 'Checking...' },
    ],
    [esgApiBase, platformApiBase]
  );

  useEffect(() => {
    const check = async () => {
      const next = await Promise.all(
        serviceTargets.map(async (item) => {
          try {
            const response = await fetch(item.url);
            const payload = await response.json();
            return {
              ...item,
              ok: response.ok,
              detail: response.ok ? JSON.stringify(payload) : 'Request failed',
            };
          } catch (error) {
            return {
              ...item,
              ok: false,
              detail: error instanceof Error ? error.message : 'Network error',
            };
          }
        })
      );
      setHealth(next);
    };

    check();
  }, [serviceTargets]);

  const runRag = async () => {
    setRagLoading(true);
    setRagResult(null);
    try {
      const response = await fetch(`${esgApiBase}/rag/ask/stream`, {
        method: 'POST',
        headers: withAuth({ headers: { 'Content-Type': 'application/json' } }).headers,
        body: JSON.stringify({ question, top_k: 3 }),
      });
      if (!response.ok) {
        const payload = await response.json();
        throw new Error(payload?.message || payload?.error || 'Streaming request failed');
      }
      let partialAnswer = '';
      let latestPayload: Partial<RagResponse> = { answer: '', sources: [] };
      await readSseEvents(response, (event) => {
        if (event.type === 'meta') {
          latestPayload = {
            ...latestPayload,
            ...event.payload,
          };
          setRagResult({
            ...latestPayload,
            answer: partialAnswer,
          });
          return;
        }
        if (event.type === 'token') {
          partialAnswer += event.text;
          setRagResult({
            ...latestPayload,
            answer: partialAnswer,
          });
          return;
        }
        if (event.type === 'done') {
          latestPayload = event.payload;
          partialAnswer = typeof event.payload.answer === 'string' ? event.payload.answer : partialAnswer;
          setRagResult({
            ...event.payload,
            answer: partialAnswer,
          });
          return;
        }
        if (event.type === 'error') {
          throw new Error(event.message || 'Streaming request failed');
        }
      });
    } catch (error) {
      setRagResult({
        answer: '',
        sources: [],
        error: 'request_failed',
        message: error instanceof Error ? error.message : 'Network error',
      });
    } finally {
      setRagLoading(false);
    }
  };

  const statusDot = (ok: boolean | null) => (ok === null ? 'bg-line-strong' : ok ? 'bg-ok' : 'bg-err');
  const statusText = (ok: boolean | null) => (ok === null ? 'Checking' : ok ? 'Online' : 'Offline');

  return (
    <div className="mx-auto max-w-content px-5 pb-24 pt-10 sm:px-8 lg:pt-14">
      <header className="max-w-2xl">
        <h1 className="page-title">Pipeline check</h1>
        <p className="mt-1 text-sm leading-6 text-ink-3">
          Check that the services respond, open the research upload desk, and run an authenticated cited query
          against the active report index. Intended for development and demos.
        </p>
      </header>

      <section className="mt-8">
        <h2 className="text-base font-semibold text-ink">Services</h2>
        <ul className="mt-3 divide-y divide-line border-y border-line">
          {health.map((item) => (
            <li key={item.label} className="flex flex-wrap items-center justify-between gap-x-6 gap-y-1 py-3 text-sm">
              <div className="min-w-0">
                <div className="font-medium text-ink">{item.label}</div>
                <div className="truncate font-mono text-xs text-ink-4">{item.url}</div>
              </div>
              <span className="inline-flex items-center gap-1.5 text-ink-2">
                <span className={`status-dot ${statusDot(item.ok)}`} />
                {statusText(item.ok)}
              </span>
            </li>
          ))}
        </ul>
      </section>

      <section className="mt-12">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <h2 className="text-base font-semibold text-ink">Try the pipeline</h2>
          <div className="segmented" role="tablist" aria-label="Pipeline step">
            {[
              { id: 'ask', label: 'Ask a question' },
              { id: 'extract', label: 'Extract entities' },
            ].map((tab) => (
              <button
                key={tab.id}
                type="button"
                role="tab"
                aria-selected={activeDemoTab === tab.id}
                onClick={() => setActiveDemoTab(tab.id as 'ask' | 'extract')}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>

        <div className="mt-5 grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(320px,0.8fr)]">
          {activeDemoTab === 'extract' ? (
            <>
              <div>
                <label className="field-label" htmlFor="demo-extract-text">Passage</label>
                <textarea
                  id="demo-extract-text"
                  value={extractText}
                  onChange={(e) => setExtractText(e.target.value)}
                  className="input min-h-[260px] resize-y text-sm"
                />
                <p className="mt-4 text-sm text-ink-3">The old standalone extraction endpoint is no longer exposed. Use the authenticated research desk to upload and query reports.</p>
                <a href="/agent" className="btn btn-primary mt-4">Open research desk</a>
              </div>
              <div className="rounded-xl border border-line bg-white p-4">
                <h3 className="text-sm font-medium text-ink">Result</h3>
                <dl className="mt-3 grid grid-cols-2 gap-4">
                  <div>
                    <dt className="text-xs text-ink-4">Entities</dt>
                    <dd className="mt-0.5 text-2xl font-medium tabular-nums text-ink">{extractResult?.entities?.length || 0}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-ink-4">Relationships</dt>
                    <dd className="mt-0.5 text-2xl font-medium tabular-nums text-ink">{extractResult?.relations?.length || 0}</dd>
                  </div>
                </dl>
                <details className="mt-4 border-t border-line pt-3">
                  <summary className="cursor-pointer text-sm text-ink-3 hover:text-ink">Raw JSON</summary>
                  <pre className="mt-3 max-h-[340px] overflow-auto whitespace-pre-wrap rounded-lg bg-paper-sunken p-3 text-xs leading-5 text-ink-2">
                    {extractResult ? JSON.stringify(extractResult, null, 2) : 'Run the extraction to see the raw output.'}
                  </pre>
                </details>
              </div>
            </>
          ) : (
            <>
              <div>
                <label className="field-label" htmlFor="demo-question">Question</label>
                <textarea
                  id="demo-question"
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  className="input min-h-[140px] resize-y text-sm"
                />
                <button type="button" onClick={runRag} disabled={ragLoading} className="btn btn-primary mt-4">
                  {ragLoading && <Loader2 className="h-4 w-4 animate-spin" />}
                  {ragLoading ? 'Retrieving…' : 'Ask'}
                </button>
              </div>
              <div className="rounded-xl border border-line bg-white p-4">
                <div className="flex items-baseline justify-between gap-3">
                  <h3 className="text-sm font-medium text-ink">Answer</h3>
                  <span className="text-xs text-ink-4">
                    {Array.isArray(ragResult?.sources) ? ragResult.sources.length : 0} sources
                  </span>
                </div>
                <p className="mt-3 min-h-[120px] whitespace-pre-wrap text-sm leading-6 text-ink-2">
                  {ragResult?.message || ragResult?.answer || 'Ask the sample question to see a cited answer.'}
                </p>
                <details className="mt-4 border-t border-line pt-3">
                  <summary className="cursor-pointer text-sm text-ink-3 hover:text-ink">Raw JSON</summary>
                  <pre className="mt-3 max-h-[340px] overflow-auto whitespace-pre-wrap rounded-lg bg-paper-sunken p-3 text-xs leading-5 text-ink-2">
                    {ragResult ? JSON.stringify(ragResult, null, 2) : 'Run a query to see the raw output.'}
                  </pre>
                </details>
              </div>
            </>
          )}
        </div>
      </section>
    </div>
  );
};

export default EsgDemo;
