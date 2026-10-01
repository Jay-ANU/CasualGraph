import { useEffect, useRef, useState } from 'react';
import { Check, FileText, Lock, UploadCloud } from 'lucide-react';
import type { COPY } from './copy';
import { useInView, useScrollProgress } from './motion';

type Workflow = (typeof COPY)['zh']['workflow'];
type Mock = Workflow['mock'];

const WIDE = '(min-width: 960px)';
function useWide() {
  const [wide, setWide] = useState(() => typeof window.matchMedia === 'function' && window.matchMedia(WIDE).matches);
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return;
    const query = window.matchMedia(WIDE);
    const update = () => setWide(query.matches);
    query.addEventListener('change', update);
    return () => query.removeEventListener('change', update);
  }, []);
  return wide;
}

/** The five screens of the desk, drawn in its own visual language; each plays when active. */
function Scene({ index, copy }: { index: number; copy: Mock }) {
  if (index === 0) return (
    <div className="ap-scene ap-scene-upload">
      <div className="ap-drop"><UploadCloud size={28} strokeWidth={1.5} aria-hidden="true" /><span>DOCX · PDF · TXT</span></div>
      <div className="ap-file">
        <FileText size={18} strokeWidth={1.6} aria-hidden="true" />
        <div className="ap-file-meta">
          <b>{copy.file}</b>
          <span className="ap-file-bar"><i /></span>
          <span className="ap-file-status"><em>{copy.uploading}</em><strong><Lock size={11} aria-hidden="true" />{copy.stored}</strong></span>
        </div>
        <span className="ap-file-size">186 KB</span>
      </div>
    </div>
  );
  if (index === 1) return (
    <div className="ap-scene ap-scene-redact">
      <div className="ap-scene-title">{copy.redactTitle}</div>
      {copy.redactLines.map(([label, value, token], i) => (
        <p key={label} style={{ '--i': i } as React.CSSProperties}>
          <span className="ap-rl-label">{label}</span>
          <span className="ap-rl-slot"><span className="ap-rl-raw">{value}</span><span className="ap-rl-token">{token}</span></span>
        </p>
      ))}
      <div className="ap-chip-ok"><Check size={12} strokeWidth={2.4} aria-hidden="true" />{copy.redactDone}</div>
    </div>
  );
  if (index === 2) return (
    <div className="ap-scene ap-scene-setup">
      <div className="ap-fields">{copy.setupFields.map(([label, value]) => <div key={label}><span>{label}</span><b>{value}</b></div>)}</div>
      <span className="ap-field-label">{copy.tierLabel}</span>
      <div className="ap-seg">{copy.tiers.map((tier, i) => <span key={tier} className={i === 2 ? 'is-on' : ''}>{tier}</span>)}<i /></div>
      <span className="ap-field-label">{copy.modelLabel}</span>
      <div className="ap-models-row">{['GPT', 'Claude', 'DeepSeek', 'Kimi', 'GLM'].map((m, i) => <span key={m} className={i === 4 ? 'is-on' : ''}>{m}</span>)}</div>
      <div className="ap-consent"><span><Check size={11} strokeWidth={3} aria-hidden="true" /></span>{copy.consent}</div>
    </div>
  );
  if (index === 3) return (
    <div className="ap-scene ap-scene-agents">
      <div className="ap-scene-title">{copy.agentsTitle}</div>
      {copy.agents.map((name, i) => (
        <div key={name} className="ap-agent-row" style={{ '--i': i } as React.CSSProperties}>
          <span>{name}</span>
          <span className="ap-agent-bar"><i /></span>
          <span className="ap-agent-done"><Check size={11} strokeWidth={3} aria-hidden="true" /></span>
        </div>
      ))}
    </div>
  );
  return (
    <div className="ap-scene ap-scene-result">
      <div className="ap-clause-head"><span>{copy.clause}</span><b>{copy.risk}</b></div>
      <p className="ap-clause">{copy.before}<del>{copy.deleted}</del><ins>{copy.inserted}</ins>{copy.after}</p>
      <div className="ap-clause-actions">{copy.actions.map((a, i) => <span key={a} className={i === 0 ? 'is-on' : ''}>{a}</span>)}</div>
      <div className="ap-export">
        <span className="ap-export-btn">{copy.export}</span>
        <span className="ap-export-done"><Check size={12} strokeWidth={2.6} aria-hidden="true" />{copy.exported}</span>
      </div>
    </div>
  );
}

function Screen({ index, active, copy }: { index: number; active: boolean; copy: Mock }) {
  return (
    <div className={`ap-screen ${active ? 'is-active' : ''}`} aria-hidden="true">
      <div className="ap-screen-bar"><i /><i /><i /><span>CausalGraph · {index + 1}/5</span></div>
      <div className="ap-screen-body"><Scene index={index} copy={copy} /></div>
    </div>
  );
}

function MobileStep({ index, step, copy }: { index: number; step: Workflow['steps'][number]; copy: Mock }) {
  const [ref, inView] = useInView<HTMLLIElement>({ threshold: 0.35 });
  return (
    <li ref={ref} className={`ap-mstep ${inView ? 'is-active' : ''}`}>
      <span className="ap-step-num">{String(index + 1).padStart(2, '0')}</span>
      <h3>{step.title}</h3>
      <p>{step.body}</p>
      <div className="ap-mstep-screen"><Screen index={index} active={inView} copy={copy} /></div>
    </li>
  );
}

/**
 * On wide screens the window stays pinned while scrolling walks through the five steps;
 * on narrow screens the steps stack, each screen playing as it arrives.
 */
export default function WorkflowStory({ copy }: { copy: Workflow }) {
  const wide = useWide();
  const section = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState(0);
  const count = copy.steps.length;

  useScrollProgress(section, (progress) => {
    if (!wide) return;
    section.current?.style.setProperty('--p', progress.toFixed(4));
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
      <ol className="ap-mstory">
        {copy.steps.map((step, i) => <MobileStep key={step.title} index={i} step={step} copy={copy.mock} />)}
      </ol>
    );
  }
  return (
    <div ref={section} className="ap-story" style={{ '--steps': count } as React.CSSProperties}>
      <div className="ap-story-sticky">
        <div className="ap-story-grid">
          <ol className="ap-story-steps">
            {copy.steps.map((step, i) => (
              <li key={step.title} className={i === active ? 'is-active' : i < active ? 'is-done' : ''}>
                <button type="button" onClick={() => jump(i)} aria-current={i === active ? 'step' : undefined}>
                  <span className="ap-step-num">{String(i + 1).padStart(2, '0')}</span>
                  <span className="ap-step-text"><strong>{step.title}</strong><span>{step.body}</span></span>
                </button>
              </li>
            ))}
          </ol>
          <div className="ap-story-stage">
            {copy.steps.map((step, i) => <Screen key={step.title} index={i} active={i === active} copy={copy.mock} />)}
          </div>
        </div>
      </div>
    </div>
  );
}
