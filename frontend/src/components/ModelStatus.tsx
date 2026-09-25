import React, { useEffect, useState } from 'react';
import { apiFetch } from '../api/client';
import type { ModelConfiguration } from '../types/api';
import { parseModelStatus, modelDisplayName } from '../utils/modelStatus';

/** Configuration only: never imply a configured key was tested or has credit. */
export default function ModelStatus({ tier }: { tier: 'flash' | 'deep' }) {
  const [configuration, setConfiguration] = useState<ModelConfiguration | null>(null);
  const [state, setState] = useState<'loading' | 'loaded' | 'error'>('loading');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    const timeout = window.setTimeout(() => controller.abort(), 8000);
    apiFetch<unknown>('/models/status', { signal: controller.signal })
      .then(payload => {
        const value = parseModelStatus(payload);
        if (!value) throw new Error('Invalid model configuration');
        if (active) { setConfiguration(value); setState('loaded'); }
      })
      .catch(() => { if (active) setState('error'); })
      .finally(() => window.clearTimeout(timeout));
    return () => { active = false; window.clearTimeout(timeout); controller.abort(); };
  }, [attempt]);
  const retry = () => {
    setState('loading');
    setAttempt(n => n + 1);
  };
  const mode = configuration?.modes[tier];
  return (
    <div className="research-model relative flex min-w-0 flex-wrap items-center gap-x-1.5 gap-y-0.5 text-xs text-ink-4" role="status" aria-live="polite">
      {state === 'loading' ? (
        <span>Checking model configuration…</span>
      ) : state === 'error' ? (
        <>
          <span className="status-dot bg-warn" aria-hidden="true" />
          <span>Model status unavailable</span>
          <button
            type="button"
            onClick={retry}
            aria-label="Retry model status"
            className="text-link text-ink-3"
          >
            Retry
          </button>
        </>
      ) : (
        <>
          <span className={`status-dot ${mode?.configured ? 'bg-ok' : 'bg-warn'}`} aria-hidden="true" />
          <strong className="font-medium text-ink-3">{modelDisplayName(mode?.model || configuration?.model || '')}</strong>
          <span aria-hidden="true">·</span>
          <span>{mode?.configured ? (mode.thinking ? 'Deep reasoning · configured' : 'Fast answers · configured') : 'Server API key required'}</span>
          <details>
            <summary aria-label="About model configuration" className="cursor-pointer list-none text-ink-3 underline decoration-line-strong underline-offset-2 hover:text-ink [&::-webkit-details-marker]:hidden">
              Details
            </summary>
            <p className="menu absolute bottom-full left-0 z-30 mb-2 w-[min(320px,calc(100vw-2rem))] p-3 text-xs leading-5 text-ink-3">
              {mode?.configured
                ? 'Configuration detected, not a live connection or credit check. Answers still depend on provider availability and document evidence.'
                : 'The server administrator must configure the selected provider API key and restart the backend. Never put a secret in browser settings.'}
            </p>
          </details>
        </>
      )}
    </div>
  );
}
