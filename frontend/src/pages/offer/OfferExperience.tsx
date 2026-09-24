import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowDown, Check, X } from 'lucide-react';
import NetworkField from './NetworkField';
import Celebration from './Celebration';
import {
  OfferCopy,
  OfferDecision,
  PublicOffer,
  copyFor,
  countdownTo,
  easeOutExpo,
  employmentLabel,
  formatAmount,
  formatLongDate,
  formatTimestamp,
  greetingName,
  periodLabel,
  twoDigits,
} from './offerContent';
import './offerPage.css';

const prefersReducedMotion = () =>
  Boolean(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);

const useTypewriter = (text: string, enabled: boolean) => {
  const [length, setLength] = useState(enabled ? 0 : text.length);
  useEffect(() => {
    if (!enabled) {
      setLength(text.length);
      return undefined;
    }
    setLength(0);
    let index = 0;
    const timer = window.setInterval(() => {
      index += 1;
      setLength(index);
      if (index >= text.length) window.clearInterval(timer);
    }, 55);
    return () => window.clearInterval(timer);
  }, [text, enabled]);
  return text.slice(0, length);
};

const useCountUp = (target: number, active: boolean, animate: boolean) => {
  const [value, setValue] = useState(animate ? 0 : target);
  useEffect(() => {
    if (!active) return undefined;
    if (!animate) {
      setValue(target);
      return undefined;
    }
    let frame = 0;
    const started = performance.now();
    const tick = (now: number) => {
      const progress = Math.min(1, (now - started) / 1800);
      setValue(target * easeOutExpo(progress));
      if (progress < 1) frame = window.requestAnimationFrame(tick);
    };
    frame = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(frame);
  }, [target, active, animate]);
  return value;
};

const useNow = (intervalMs: number) => {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), intervalMs);
    return () => window.clearInterval(timer);
  }, [intervalMs]);
  return now;
};

// Adds `is-visible` to `.ox-reveal` elements as they scroll into view.
const useReveal = (root: React.RefObject<HTMLElement>, key: unknown) => {
  useEffect(() => {
    const container = root.current;
    if (!container) return undefined;
    const elements = Array.prototype.slice.call(container.querySelectorAll('.ox-reveal')) as HTMLElement[];
    if (!('IntersectionObserver' in window) || prefersReducedMotion()) {
      elements.forEach((element) => element.classList.add('is-visible'));
      return undefined;
    }
    const observer = new IntersectionObserver(
      (entries) =>
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-visible');
            observer.unobserve(entry.target);
          }
        }),
      { threshold: 0, rootMargin: '0px 0px -8% 0px' }
    );
    elements.forEach((element) => observer.observe(element));
    return () => observer.disconnect();
  }, [root, key]);
};

export const OfferMark: React.FC<{ size?: number; spin?: boolean }> = ({ size = 30, spin = false }) => (
  <svg width={size} height={size} viewBox="0 0 40 40" aria-hidden="true" className="ox-mark">
    <defs>
      <linearGradient id="ox-mark-gradient" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stopColor="#22d3ee" />
        <stop offset="0.5" stopColor="#6366f1" />
        <stop offset="1" stopColor="#a855f7" />
      </linearGradient>
    </defs>
    <rect x="0.5" y="0.5" width="39" height="39" rx="11" fill="rgba(255,255,255,0.04)" stroke="rgba(255,255,255,0.16)" />
    <g
      className={spin ? 'ox-mark-orbits' : undefined}
      transform="translate(8 8)"
      fill="none"
      stroke="url(#ox-mark-gradient)"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <circle cx="12" cy="12" r="3" />
      <ellipse cx="12" cy="12" rx="10" ry="4" />
      <ellipse cx="12" cy="12" rx="10" ry="4" transform="rotate(60 12 12)" />
      <ellipse cx="12" cy="12" rx="10" ry="4" transform="rotate(120 12 12)" />
    </g>
  </svg>
);

/** Background layers shared by every state of the offer page. */
export const OfferShell: React.FC<{ children: React.ReactNode; className?: string; lang?: string }> = ({
  children,
  className = '',
  lang,
}) => {
  const rootRef = useRef<HTMLDivElement>(null);
  const onPointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    rootRef.current?.style.setProperty('--ox-mx', `${event.clientX}px`);
    rootRef.current?.style.setProperty('--ox-my', `${event.clientY}px`);
  };
  return (
    <div ref={rootRef} className={`ox ${className}`} lang={lang} onPointerMove={onPointerMove}>
      <div className="ox-aurora" aria-hidden="true" />
      <NetworkField className="ox-field" />
      <div className="ox-floor" aria-hidden="true" />
      <div className="ox-spotlight" aria-hidden="true" />
      {children}
    </div>
  );
};

const OfferHeader: React.FC<{ copy: OfferCopy; organisation: string }> = ({ copy, organisation }) => (
  <header className="ox-top">
    <span className="ox-brand">
      <OfferMark spin />
      <span>{organisation}</span>
    </span>
    <span className="ox-badge">
      <span className="ox-badge-dot" />
      {copy.confidential}
    </span>
  </header>
);

export const OfferLoading: React.FC<{ language?: string }> = ({ language }) => {
  const copy = copyFor(language);
  return (
    <OfferShell>
      <main className="ox-center">
        <div className="ox-terminal" role="status">
          <div className="ox-terminal-bar">
            <span />
            <span />
            <span />
            <em>offer://secure</em>
          </div>
          {copy.loading.map((line, index) => (
            <p key={line} className="ox-terminal-line" style={{ animationDelay: `${index * 0.45}s` }}>
              <span className="ox-terminal-prompt">&gt;</span> {line}
              <span className="ox-terminal-ok">✓</span>
            </p>
          ))}
          <div className="ox-terminal-progress">
            <span />
          </div>
        </div>
      </main>
    </OfferShell>
  );
};

export const OfferNotice: React.FC<{
  title: string;
  body: string;
  language?: string;
  actionLabel?: string;
  onAction?: () => void;
}> = ({ title, body, language, actionLabel, onAction }) => (
  <OfferShell lang={language === 'zh' ? 'zh-CN' : 'en'}>
    <main className="ox-center">
      <div className="ox-card ox-notice">
        <OfferMark size={44} spin />
        <h1>{title}</h1>
        <p>{body}</p>
        {actionLabel && onAction && (
          <button type="button" onClick={onAction} className="ox-btn ox-btn-ghost">
            {actionLabel}
          </button>
        )}
      </div>
    </main>
  </OfferShell>
);

interface OfferExperienceProps {
  offer: PublicOffer;
  /** Admin preview: no requests are made and the buttons are disabled. */
  preview?: boolean;
  onRespond?: (decision: OfferDecision, note: string) => Promise<void>;
  onClosePreview?: () => void;
}

const OfferExperience: React.FC<OfferExperienceProps> = ({ offer, preview = false, onRespond, onClosePreview }) => {
  const language = offer.language === 'zh' ? 'zh' : 'en';
  const copy = copyFor(language);
  const reduceMotion = prefersReducedMotion();
  const contentRef = useRef<HTMLDivElement>(null);
  const salaryRef = useRef<HTMLDivElement>(null);
  const noteRef = useRef<HTMLTextAreaElement>(null);
  const [salaryVisible, setSalaryVisible] = useState(false);
  const [dialog, setDialog] = useState<OfferDecision | null>(null);
  const [note, setNote] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [burst, setBurst] = useState(0);
  const now = useNow(1000);

  const firstName = greetingName(offer.candidate_name);
  const greeting = useTypewriter(copy.greeting(firstName), !reduceMotion);
  const typing = greeting.length < copy.greeting(firstName).length;
  const salary = offer.salary || null;
  const amount = useCountUp(salary ? salary.amount : 0, salaryVisible, !reduceMotion);
  // While counting, show the same precision as the final amount so the number doesn't jitter.
  const salaryDigits = salary && Math.round(salary.amount) !== salary.amount ? 2 : 0;
  const countdown = offer.status === 'open' ? countdownTo(offer.respond_by, now) : null;
  const isOpen = offer.status === 'open';
  const employment = employmentLabel(offer.employment_type, language);
  const benefits = offer.benefits || [];
  useReveal(contentRef, offer.status);

  useEffect(() => {
    const element = salaryRef.current;
    if (!element || !('IntersectionObserver' in window)) {
      setSalaryVisible(true);
      return undefined;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setSalaryVisible(true);
          observer.disconnect();
        }
      },
      { threshold: 0.35 }
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const closeDialog = useCallback(() => {
    if (submitting) return;
    setDialog(null);
    setError('');
  }, [submitting]);

  useEffect(() => {
    if (!dialog) return undefined;
    noteRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closeDialog();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [dialog, closeDialog]);

  const submit = async () => {
    if (!dialog || !onRespond || preview) return;
    setSubmitting(true);
    setError('');
    try {
      await onRespond(dialog, note.trim());
      const decision = dialog;
      setDialog(null);
      setNote('');
      if (decision === 'accept') setBurst(Date.now());
      window.scrollTo({ top: 0, behavior: reduceMotion ? 'auto' : 'smooth' });
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : copy.respondFailed);
    } finally {
      setSubmitting(false);
    }
  };

  const facts: Array<[string, string]> = [
    [copy.startDate, formatLongDate(offer.start_date, language)],
    [copy.replyBy, formatLongDate(offer.respond_by, language)],
    [copy.team, offer.team || ''],
    [copy.location, offer.location || ''],
    [copy.employment, employment],
    [copy.reportsTo, offer.reports_to || ''],
  ];
  const visibleFacts = facts.filter(([, value]) => value);
  const chips = [offer.team, offer.location, employment].filter(Boolean) as string[];

  const decisionButtons = (
    <div className="ox-actions">
      <button
        type="button"
        className="ox-btn ox-btn-primary"
        onClick={() => setDialog('accept')}
        disabled={preview}
        title={preview ? copy.previewBanner : undefined}
      >
        <Check className="ox-btn-icon" aria-hidden="true" />
        {copy.accept}
      </button>
      <button
        type="button"
        className="ox-btn ox-btn-ghost"
        onClick={() => setDialog('decline')}
        disabled={preview}
        title={preview ? copy.previewBanner : undefined}
      >
        {copy.decline}
      </button>
    </div>
  );

  return (
    <OfferShell className={preview ? 'ox--preview' : ''} lang={language === 'zh' ? 'zh-CN' : 'en'}>
      {preview && (
        <div className="ox-preview-bar" role="note">
          <span>{copy.previewBanner}</span>
          {onClosePreview && (
            <button type="button" onClick={onClosePreview} className="ox-preview-close" aria-label={copy.closePreview}>
              <X aria-hidden="true" />
            </button>
          )}
        </div>
      )}
      <OfferHeader copy={copy} organisation={offer.organisation} />

      <div ref={contentRef}>
        <section className="ox-hero">
          <div className="ox-hero-text">
            <p className="ox-kicker">
              <span className="ox-kicker-line" />
              {copy.kicker}
            </p>
            <h1 className="ox-greeting" aria-label={copy.greeting(firstName)}>
              <span aria-hidden="true">{greeting}</span>
              <span className={`ox-caret${typing ? '' : ' ox-caret--idle'}`} aria-hidden="true" />
            </h1>
            <p className="ox-intro">{copy.intro(offer.organisation)}</p>
            <p className="ox-role">{offer.position}</p>
            {chips.length > 0 && (
              <ul className="ox-chips">
                {chips.map((chip) => (
                  <li key={chip} className="ox-chip">
                    <span className="ox-chip-dot" />
                    {chip}
                  </li>
                ))}
              </ul>
            )}

            {offer.status === 'accepted' && (
              <div className="ox-status ox-status--accepted" role="status">
                <span className="ox-status-icon">
                  <Check aria-hidden="true" />
                </span>
                <div>
                  <p className="ox-status-title">{copy.acceptedTitle(firstName)}</p>
                  <p>{copy.acceptedBody}</p>
                  {offer.responded_at && <p className="ox-status-meta">{copy.acceptedOn(formatTimestamp(offer.responded_at, language))}</p>}
                </div>
              </div>
            )}
            {offer.status === 'declined' && (
              <div className="ox-status ox-status--declined" role="status">
                <div>
                  <p className="ox-status-title">{copy.declinedTitle}</p>
                  <p>{copy.declinedBody}</p>
                  {offer.responded_at && <p className="ox-status-meta">{copy.declinedOn(formatTimestamp(offer.responded_at, language))}</p>}
                </div>
              </div>
            )}

            {isOpen && (
              <>
                {decisionButtons}
                {countdown && (
                  <div className="ox-countdown" aria-live="off">
                    {countdown.passed ? (
                      <span className="ox-countdown-label">{copy.replyDatePassed}</span>
                    ) : (
                      <>
                        <span className="ox-countdown-label">{copy.replyWithin}</span>
                        {(
                          [
                            [countdown.days, copy.units.days],
                            [countdown.hours, copy.units.hours],
                            [countdown.minutes, copy.units.minutes],
                            [countdown.seconds, copy.units.seconds],
                          ] as Array<[number, string]>
                        ).map(([value, unit]) => (
                          <span key={unit} className="ox-countdown-cell">
                            <strong>{twoDigits(value)}</strong>
                            <small>{unit}</small>
                          </span>
                        ))}
                      </>
                    )}
                  </div>
                )}
              </>
            )}
          </div>

          <div className="ox-hud" aria-hidden="true">
            <div className="ox-hud-ring ox-hud-ring--glow" />
            <div className="ox-hud-ring ox-hud-ring--dash" />
            <div className="ox-hud-ring ox-hud-ring--ticks" />
            <div className="ox-hud-orbit" />
            <div className="ox-hud-orbit ox-hud-orbit--slow" />
            <div className="ox-hud-core">
              <OfferMark size={64} spin />
              <span>{copy.kicker}</span>
            </div>
          </div>

          <a href="#ox-details" className="ox-scroll">
            {copy.scroll}
            <ArrowDown aria-hidden="true" />
          </a>
        </section>

        <section id="ox-details" className="ox-section">
          <div className="ox-grid">
            {salary && (
              <div ref={salaryRef} className="ox-card ox-card--salary ox-reveal">
                <p className="ox-label">{copy.compensation}</p>
                <p className="ox-sublabel">{copy.baseSalary}</p>
                <p className="ox-amount">
                  <span className="ox-currency">{salary.currency}</span>
                  <span className="ox-amount-value">{formatAmount(amount, language, salaryDigits)}</span>
                </p>
                <p className="ox-period">{periodLabel(salary.period, language)}</p>
                <div className={`ox-bar${salaryVisible ? ' is-full' : ''}`}>
                  <span />
                </div>
                {offer.extra_compensation && (
                  <p className="ox-extra">
                    <span>{copy.alsoIncluded}</span>
                    {offer.extra_compensation}
                  </p>
                )}
                <div className="ox-wave" aria-hidden="true">
                  <svg viewBox="0 0 1200 70" preserveAspectRatio="none">
                    <path d="M0 35 Q75 5 150 35 T300 35 T450 35 T600 35 T750 35 T900 35 T1050 35 T1200 35" />
                    <path d="M0 42 Q150 14 300 42 T600 42 T900 42 T1200 42" />
                  </svg>
                </div>
              </div>
            )}
            {visibleFacts.length > 0 && (
              <div className={`ox-card ox-card--facts ox-reveal${salary ? '' : ' ox-card--wide'}`}>
                <p className="ox-label">{copy.role}</p>
                <dl className="ox-facts">
                  {visibleFacts.map(([label, value]) => (
                    <div key={label} className="ox-fact">
                      <dt>{label}</dt>
                      <dd>{value}</dd>
                    </div>
                  ))}
                </dl>
              </div>
            )}
          </div>
        </section>

        {benefits.length > 0 && (
          <section className="ox-section">
            <h2 className="ox-section-title ox-reveal">{copy.benefits}</h2>
            <ul className="ox-benefits">
              {benefits.map((benefit, index) => (
                <li key={`${benefit}-${index}`} className="ox-benefit ox-reveal" style={{ transitionDelay: `${index * 70}ms` }}>
                  <span className="ox-benefit-icon">
                    <Check aria-hidden="true" />
                  </span>
                  {benefit}
                </li>
              ))}
            </ul>
          </section>
        )}

        {offer.letter && (
          <section className="ox-section">
            <h2 className="ox-section-title ox-reveal">{copy.note}</h2>
            <div className="ox-card ox-letter ox-reveal">
              <p className="ox-letter-body">{offer.letter}</p>
            </div>
          </section>
        )}

        {isOpen && (
          <section className="ox-section ox-decide ox-reveal">
            <h2>{copy.decideTitle}</h2>
            <p>{copy.decideBody}</p>
            {decisionButtons}
          </section>
        )}

        <footer className="ox-footer">
          <p>{copy.privateNote}</p>
          <p>© {new Date().getFullYear()} {offer.organisation}</p>
        </footer>
      </div>

      {dialog && (
        <div className="ox-backdrop" role="presentation" onMouseDown={closeDialog}>
          <div
            className="ox-card ox-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="ox-dialog-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <h2 id="ox-dialog-title">{dialog === 'accept' ? copy.acceptTitle : copy.declineTitle}</h2>
            <p>{dialog === 'accept' ? copy.acceptBody(offer.position) : copy.declineBody}</p>
            <label htmlFor="ox-note" className="ox-field-label">
              {copy.messageLabel}
            </label>
            <textarea
              id="ox-note"
              ref={noteRef}
              value={note}
              onChange={(event) => setNote(event.target.value)}
              maxLength={1000}
              rows={4}
              className="ox-textarea"
            />
            {error && (
              <p role="alert" className="ox-error">
                {error}
              </p>
            )}
            <div className="ox-dialog-actions">
              <button type="button" className="ox-btn ox-btn-ghost" onClick={closeDialog} disabled={submitting}>
                {copy.cancel}
              </button>
              <button
                type="button"
                className={`ox-btn ${dialog === 'accept' ? 'ox-btn-primary' : 'ox-btn-danger'}`}
                onClick={submit}
                disabled={submitting}
              >
                {submitting ? copy.sending : dialog === 'accept' ? copy.confirmAccept : copy.confirmDecline}
              </button>
            </div>
          </div>
        </div>
      )}
      <Celebration burst={burst} />
    </OfferShell>
  );
};

export default OfferExperience;
