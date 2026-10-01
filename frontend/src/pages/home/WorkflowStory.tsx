import { useEffect, useRef, useState } from 'react';
import { Check, CheckCircle2, UploadCloud, Download, FileText, Lock, ShieldCheck } from 'lucide-react';
import type { COPY } from './copy';
import { useInView, useScrollProgress } from './motion';

type Workflow = (typeof COPY)['zh']['workflow'];
type Agent = (typeof COPY)['zh']['agents']['list'][number];

const WIDE = '(min-width: 960px)';
const useWide = () => {
  const [wide, setWide] = useState(() => typeof window.matchMedia === 'function' && window.matchMedia(WIDE).matches);
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return;
    const query = window.matchMedia(WIDE);
    const update = () => setWide(query.matches);
    query.addEventListener('change', update);
    return () => query.removeEventListener('change', update);
  }, []);
  return wide;
};

function Scene({ index, copy, agents }: { index: number; copy: Workflow['mock']; agents: Agent[] }) {
  if (index === 0) return (
    <div className="lp-scene-upload">
      <div className="lp-drop">
        <UploadCloud size={30} strokeWidth={1.4} aria-hidden="true" />
        <span>DOCX · PDF · TXT</span>
      </div>
      <div className="lp-file">
        <FileText size={20} strokeWidth={1.6} aria-hidden="true" />
        <div className="lp-file-meta">
          <strong>{copy.file}</strong>
          <span className="lp-file-bar"><i /></span>
          <span className="lp-file-status"><em>{copy.uploading}</em><b><Lock size={12} aria-hidden="true" />{copy.stored}</b></span>
        </div>
        <span className="lp-file-size">186 KB</span>
      </div>
    </div>
  );
  if (index === 1) return (
    <div className="lp-scene-redact">
      <div className="lp-scene-title"><ShieldCheck size={15} aria-hidden="true" />{copy.redactTitle}</div>
      {copy.redactLines.map(([label, value, token], i) => (
        <p key={label} style={{ '--i': i } as React.CSSProperties}>
          <span className="lp-redact-label">{label}</span>
          <span className="lp-redact-slot"><span className="lp-redact-raw">{value}</span><span className="lp-redact-token">{token}</span></span>
        </p>
      ))}
      <div className="lp-scene-chip"><Check size={13} aria-hidden="true" />{copy.redactDone}</div>
    </div>
  );
  if (index === 2) return (
    <div className="lp-scene-setup">
      <div className="lp-setup-fields">
        {copy.setupFields.map(([label, value]) => (
          <div key={label}><span>{label}</span><strong>{value}</strong></div>
        ))}
      </div>
      <span className="lp-setup-label">{copy.tierLabel}</span>
      <div className="lp-tiers">{copy.tiers.map((tier, i) => <span key={tier} className={i === 2 ? 'is-on' : ''}>{tier}</span>)}<i /></div>
      <span className="lp-setup-label">{copy.modelLabel}</span>
      <div className="lp-models">{['GPT', 'Claude', 'DeepSeek', 'Kimi', 'GLM'].map((m, i) => <span key={m} className={i === 4 ? 'is-on' : ''}>{m}</span>)}</div>
      <label className="lp-consent"><span><Check size={12} aria-hidden="true" /></span>{copy.consent}</label>
    </div>
  );
  if (index === 3) return (
    <div className="lp-scene-agents">
      <div className="lp-scene-title"><span className="lp-feed-dot" />{copy.agentsTitle}</div>
      {agents.map((agent, i) => (
        <div key={agent.id} className={`lp-agent-row lp-tone-${agent.tone}`} style={{ '--i': i } as React.CSSProperties}>
          <span>{agent.name}</span>
          <span className="lp-agent-bar"><i /></span>
          <CheckCircle2 size={15} aria-hidden="true" />
        </div>
      ))}
    </div>
  );
  return (
    <div className="lp-scene-result">
      <div className="lp-clause-head"><span>{copy.clause}</span><b>{copy.risk}</b></div>
      <p className="lp-clause-text">
        {copy.before}<del>{copy.deleted}</del><ins>{copy.inserted}</ins>{copy.after}
      </p>
      <div className="lp-clause-actions">{copy.actions.map((a, i) => <span key={a} className={i === 0 ? 'is-on' : ''}>{a}</span>)}</div>
      <div className="lp-export">
        <span className="lp-export-btn"><Download size={15} aria-hidden="true" />{copy.export}</span>
        <span className="lp-export-done"><CheckCircle2 size={14} aria-hidden="true" />{copy.exported}</span>
      </div>
    </div>
  );
}

function Screen({ index, active, copy, agents }: { index: number; active: boolean; copy: Workflow['mock']; agents: Agent[] }) {
  return (
    <div className={`lp-screen ${active ? 'is-active' : ''}`} aria-hidden="true">
      <div className="lp-screen-bar"><i /><i /><i /><span>CausalGraph · {index + 1}/5</span></div>
      <div className="lp-screen-body"><Scene index={index} copy={copy} agents={agents} /></div>
    </div>
  );
}

function MobileStep({ index, step, copy, agents }: { index: number; step: Workflow['steps'][number]; copy: Workflow['mock']; agents: Agent[] }) {
  const [ref, inView] = useInView<HTMLLIElement>({ threshold: 0.35 });
  return (
    <li ref={ref} className={`lp-mstep ${inView ? 'is-active' : ''}`}>
      <span className="lp-step-num">{String(index + 1).padStart(2, '0')}</span>
      <h3>{step.title}</h3>
      <p>{step.body}</p>
      <div className="lp-mstep-screen"><Screen index={index} active={inView} copy={copy} agents={agents} /></div>
    </li>
  );
}

/**
 * Apple-style pinned story on wide screens: the screen stays put while scrolling advances the
 * five steps. Narrow screens get the same scenes stacked, each playing as it scrolls in.
 */
export default function WorkflowStory({ copy, agents }: { copy: Workflow; agents: Agent[] }) {
  const wide = useWide();
  const section = useRef<HTMLDivElement>(null);
  const rail = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState(0);
  const count = copy.steps.length;

  useScrollProgress(section, (progress) => {
    if (!wide) return;
    rail.current?.style.setProperty('--p', progress.toFixed(4));
    const next = Math.min(count - 1, Math.floor(progress * count * 0.999));
    setActive(current => (current === next ? current : next));
  });

  const jump = (index: number) => {
    const element = section.current;
    if (!element) return;
    const top = element.getBoundingClientRect().top + window.scrollY;
    const span = element.offsetHeight - window.innerHeight;
    window.scrollTo({ top: top + span * ((index + 0.5) / count), behavior: 'smooth' });
  };

  if (!wide) {
    return (
      <ol className="lp-mstory">
        {copy.steps.map((step, i) => <MobileStep key={step.title} index={i} step={step} copy={copy.mock} agents={agents} />)}
      </ol>
    );
  }
  return (
    <div ref={section} className="lp-story" style={{ '--steps': count } as React.CSSProperties}>
      <div className="lp-story-sticky">
        <div className="lp-story-grid">
          <div ref={rail} className="lp-story-rail">
            <ol className="lp-story-steps">
              {copy.steps.map((step, i) => (
                <li key={step.title} className={i === active ? 'is-active' : i < active ? 'is-done' : ''}>
                  <button type="button" onClick={() => jump(i)} aria-current={i === active ? 'step' : undefined}>
                    <span className="lp-step-num">{String(i + 1).padStart(2, '0')}</span>
                    <span className="lp-step-text"><strong>{step.title}</strong><span>{step.body}</span></span>
                  </button>
                </li>
              ))}
            </ol>
            <span className="lp-story-track" aria-hidden="true"><i /></span>
          </div>
          <div className="lp-story-stage">
            {copy.steps.map((step, i) => <Screen key={step.title} index={i} active={i === active} copy={copy.mock} agents={agents} />)}
          </div>
        </div>
      </div>
    </div>
  );
}
