import React, { useEffect, useState } from 'react';
import { Cpu, RefreshCw } from 'lucide-react';
import { parseModelStatus, modelDisplayName, type ModelConfiguration } from '../utils/modelStatus';

/** Configuration only: never imply a configured key was tested or has credit. */
export default function ModelStatus({ apiBase, tier }: { apiBase: string; tier: 'flash' | 'deep' }) {
  const [configuration, setConfiguration] = useState<ModelConfiguration | null>(null);
  const [state, setState] = useState<'loading' | 'loaded' | 'error'>('loading');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setState('loading');
    const timeout = window.setTimeout(() => controller.abort(), 8000);
    fetch(`${apiBase.replace(/\/$/, '')}/models/status`, { signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error('Model configuration unavailable');
        const value = parseModelStatus(await response.json());
        if (!value) throw new Error('Invalid model configuration');
        if (active) { setConfiguration(value); setState('loaded'); }
      })
      .catch(() => { if (active) setState('error'); })
      .finally(() => window.clearTimeout(timeout));
    return () => { active = false; window.clearTimeout(timeout); controller.abort(); };
  }, [apiBase, attempt]);
  const mode = configuration?.modes[tier];
  return (
    <div className="research-model" role="status" aria-live="polite">
      <Cpu size={15} aria-hidden="true" />
      {state === 'loading' ? <span>Checking model configuration…</span> : state === 'error' ? (
        <><span>Model status unavailable</span><button type="button" onClick={() => setAttempt(n => n + 1)} aria-label="Retry model status"><RefreshCw size={13} /> Retry</button></>
      ) : (
        <>
          <strong>{modelDisplayName(mode?.model || configuration?.model || '')}</strong>
          <span className={`research-status-dot ${mode?.configured ? 'is-configured' : ''}`} />
          <span>{mode?.configured ? (mode.thinking ? 'Deep reasoning · configured' : 'Fast answers · configured') : 'Server API key required'}</span>
          <details><summary aria-label="About model configuration">Info</summary>
            <p>{mode?.configured
              ? 'Configuration detected, not a live connection or credit check. Answers still depend on provider availability and report evidence.'
              : 'The server administrator must configure the selected provider API key and restart the backend. Never put a secret in browser settings.'}</p>
          </details>
        </>
      )}
    </div>
  );
}
