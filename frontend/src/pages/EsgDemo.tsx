import React, { useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import { Database, FileText, Network, Search, Workflow } from 'lucide-react';
import type { RagResponse, RagStreamEvent } from '../types/api';

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
  const esgApiBase = process.env.REACT_APP_ESG_API_BASE || (localApiHost ? `http://${host}:8000` : '');
  const platformApiBase = `http://${host}:8001`;

  const [health, setHealth] = useState<HealthState[]>([
    { label: 'Evidence API', url: `${esgApiBase}/health`, ok: null, detail: 'Checking...' },
    { label: 'Application API', url: `${platformApiBase}/`, ok: null, detail: 'Checking...' },
  ]);

  const [extractText, setExtractText] = useState(SAMPLE_TEXT);
  const [extractLoading, setExtractLoading] = useState(false);
  const [extractResult, setExtractResult] = useState<any>(null);

  const [question, setQuestion] = useState(SAMPLE_QUESTION);
  const [ragLoading, setRagLoading] = useState(false);
  const [ragResult, setRagResult] = useState<any>(null);
  const [activeDemoTab, setActiveDemoTab] = useState<'ask' | 'extract'>('ask');

  const serviceTargets = useMemo(
    () => [
      { label: 'Evidence API', url: `${esgApiBase}/health`, ok: null, detail: 'Checking...' },
      { label: 'Application API', url: `${platformApiBase}/`, ok: null, detail: 'Checking...' },
    ],
    [esgApiBase, platformApiBase]
  );

  useEffect(() => {
    setHealth(serviceTargets);
  }, [serviceTargets]);

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

  const runExtraction = async () => {
    setExtractLoading(true);
    setExtractResult(null);
    try {
      const response = await fetch(`${esgApiBase}/extract`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: extractText }),
      });
      const payload = await response.json();
      setExtractResult(payload);
    } catch (error) {
      setExtractResult({
        entities: [],
        relations: [],
        error: 'request_failed',
        message: error instanceof Error ? error.message : 'Network error',
      });
    } finally {
      setExtractLoading(false);
    }
  };

  const runRag = async () => {
    setRagLoading(true);
    setRagResult(null);
    try {
      const response = await fetch(`${esgApiBase}/rag/ask/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
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

  return (
    <div className="min-h-screen text-slate-950">
      <section className="tech-hero app-grid">
        <div className="mx-auto max-w-[1600px] px-4 py-16 sm:px-6 lg:px-8">
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45 }} className="max-w-4xl">
            <h1 className="text-4xl font-semibold tracking-tight text-slate-950 sm:text-5xl">
              Inspect the pipeline from report text to cited answer.
            </h1>
            <p className="mt-5 max-w-3xl text-lg leading-8 text-slate-600">
              Check service readiness, extract ESG entities and relationships, then query the active report index with
              the returned evidence in view.
            </p>
          </motion.div>
        </div>
      </section>

      <div className="mx-auto max-w-[1600px] space-y-8 px-4 py-10 sm:px-6 lg:px-8">
        <section>
          <div className="mb-4 flex items-center gap-3">
            <Database className="h-5 w-5 text-slate-500" />
            <h2 className="text-2xl font-semibold text-slate-950">System status</h2>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            {health.map((item) => (
              <div key={item.label} className="app-panel p-5">
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <div className="text-sm font-semibold text-slate-950">{item.label}</div>
                    <div className="mt-1 font-mono text-xs text-slate-500">{item.url}</div>
                  </div>
                  <div
                    className={`rounded-md px-2.5 py-1 text-xs font-medium ${
                      item.ok === null
                        ? 'bg-slate-100 text-slate-600'
                        : item.ok
                          ? 'bg-emerald-50 text-emerald-700'
                          : 'bg-rose-50 text-rose-700'
                    }`}
                  >
                    {item.ok === null ? 'Checking' : item.ok ? 'Online' : 'Offline'}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="app-panel overflow-hidden">
          <div className="flex flex-col gap-3 border-b border-slate-200 p-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="text-2xl font-semibold text-slate-950">Demo workflow</h2>
              <p className="mt-1 text-sm text-slate-600">Run one step at a time.</p>
            </div>
            <div className="inline-flex rounded-full border border-slate-200 bg-white p-1">
              {[
                { id: 'ask', label: 'Ask' },
                { id: 'extract', label: 'Extract' },
              ].map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setActiveDemoTab(tab.id as 'ask' | 'extract')}
                  className={`rounded-full px-4 py-2 text-sm font-semibold transition ${
                    activeDemoTab === tab.id ? 'bg-slate-950 text-white' : 'text-slate-600 hover:bg-slate-100'
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>
          </div>

          <motion.div
            key={activeDemoTab}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.24 }}
            className="grid gap-6 p-5 lg:grid-cols-[minmax(0,0.95fr)_minmax(320px,0.65fr)]"
          >
            {activeDemoTab === 'extract' ? (
              <>
                <div>
                  <div className="mb-4 flex items-center gap-3">
                    <Workflow className="h-5 w-5 text-slate-500" />
                    <h3 className="text-xl font-semibold text-slate-950">ESG extraction</h3>
                  </div>
                  <textarea
                    value={extractText}
                    onChange={(e) => setExtractText(e.target.value)}
                    className="min-h-[260px] w-full rounded-xl border border-slate-300 bg-white/70 p-4 text-sm text-slate-800 outline-none focus:border-slate-500 focus:ring-2 focus:ring-slate-200"
                  />
                  <button
                    onClick={runExtraction}
                    disabled={extractLoading}
                    className="tech-button mt-4 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <FileText className="h-4 w-4" />
                    {extractLoading ? 'Extracting...' : 'Run extraction'}
                  </button>
                </div>
                <div className="rounded-xl bg-slate-50 p-4">
                  <div className="text-sm font-semibold text-slate-950">Result</div>
                  <div className="mt-4 grid grid-cols-2 gap-3">
                    <div className="rounded-lg bg-white p-3">
                      <div className="text-2xl font-semibold text-slate-950">{extractResult?.entities?.length || 0}</div>
                      <div className="mt-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Entities</div>
                    </div>
                    <div className="rounded-lg bg-white p-3">
                      <div className="text-2xl font-semibold text-slate-950">{extractResult?.relations?.length || 0}</div>
                      <div className="mt-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Relations</div>
                    </div>
                  </div>
                  <details className="mt-4">
                    <summary className="cursor-pointer text-sm font-semibold text-slate-700">Raw JSON</summary>
                    <pre className="mt-3 max-h-[340px] overflow-auto whitespace-pre-wrap rounded-xl bg-slate-950 p-4 text-xs leading-5 text-slate-100">
                      {extractResult ? JSON.stringify(extractResult, null, 2) : 'Run extraction to see raw output.'}
                    </pre>
                  </details>
                </div>
              </>
            ) : (
              <>
                <div>
                  <div className="mb-4 flex items-center gap-3">
                    <Search className="h-5 w-5 text-slate-500" />
                    <h3 className="text-xl font-semibold text-slate-950">Evidence-backed query</h3>
                  </div>
                  <textarea
                    value={question}
                    onChange={(e) => setQuestion(e.target.value)}
                    className="min-h-[150px] w-full rounded-xl border border-slate-300 bg-white/70 p-4 text-sm text-slate-800 outline-none focus:border-slate-500 focus:ring-2 focus:ring-slate-200"
                  />
                  <button
                    onClick={runRag}
                    disabled={ragLoading}
                    className="tech-button mt-4 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <Network className="h-4 w-4" />
                    {ragLoading ? 'Retrieving...' : 'Ask question'}
                  </button>
                </div>
                <div className="rounded-xl bg-slate-50 p-4">
                  <div className="text-sm font-semibold text-slate-950">Answer</div>
                  <p className="mt-3 min-h-[120px] whitespace-pre-wrap text-sm leading-6 text-slate-700">
                    {ragResult?.message || ragResult?.answer || 'Ask the sample question to see the grounded answer.'}
                  </p>
                  <div className="mt-4 rounded-lg bg-white p-3 text-sm text-slate-600">
                    Sources: {Array.isArray(ragResult?.sources) ? ragResult.sources.length : 0}
                  </div>
                  <details className="mt-4">
                    <summary className="cursor-pointer text-sm font-semibold text-slate-700">Raw JSON</summary>
                    <pre className="mt-3 max-h-[340px] overflow-auto whitespace-pre-wrap rounded-xl bg-slate-950 p-4 text-xs leading-5 text-slate-100">
                      {ragResult ? JSON.stringify(ragResult, null, 2) : 'Run a query to see raw output.'}
                    </pre>
                  </details>
                </div>
              </>
            )}
          </motion.div>
        </section>
      </div>
    </div>
  );
};

export default EsgDemo;
