import { Check, Lock } from 'lucide-react';
import { useInView } from './motion';

type Copy = { before: string; after: string; lines: string[][]; status: string };

/** Before and after, side by side: what was uploaded and what a model is allowed to see. */
export default function Redaction({ copy, still }: { copy: Copy; still: boolean }) {
  const [ref, inView] = useInView<HTMLDivElement>({ threshold: 0.35 });
  return (
    <div ref={ref} className={`ap-redact ${inView || still ? 'is-on' : ''}`}>
      <div className="ap-redact-col">
        <div className="ap-redact-head"><Lock size={14} strokeWidth={2} aria-hidden="true" />{copy.before}</div>
        {copy.lines.map(([label, value]) => (
          <p key={label}><span className="ap-redact-label">{label}</span><span className="ap-redact-raw">{value}</span></p>
        ))}
      </div>
      <div className="ap-redact-arrow" aria-hidden="true"><span /></div>
      <div className="ap-redact-col is-after">
        <div className="ap-redact-head"><Check size={14} strokeWidth={2.4} aria-hidden="true" />{copy.after}</div>
        {copy.lines.map(([label, , token], i) => (
          <p key={label} style={{ '--i': i } as React.CSSProperties}><span className="ap-redact-label">{label}</span><span className="ap-redact-token">{token}</span></p>
        ))}
        <div className="ap-redact-status">{copy.status}</div>
      </div>
    </div>
  );
}
