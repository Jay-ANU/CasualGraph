import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ArrowDown, X } from 'lucide-react';
import {
  OfferCopy,
  OfferDecision,
  OfferLanguage,
  PublicOffer,
  clockOf,
  copyFor,
  countdownTo,
  employmentLabel,
  formatAmount,
  formatLongDate,
  formatShortDate,
  formatTimestamp,
  greetingName,
  offerReference,
  periodLabel,
  referenceBars,
  referenceSeed,
  replyWindowLeft,
} from './offerContent';
import './offerPage.css';

const prefersReducedMotion = () =>
  Boolean(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);

// The card only follows a pointer that can hover; on touch screens it simply lies flat.
const hasFinePointer = () =>
  Boolean(window.matchMedia && window.matchMedia('(hover: hover) and (pointer: fine)').matches);

const langAttr = (language?: string) => (language === 'zh' ? 'zh-CN' : 'en');

const useNow = (intervalMs: number) => {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), intervalMs);
    return () => window.clearInterval(timer);
  }, [intervalMs]);
  return now;
};

/** True once the element has been scrolled into view (and stays true). */
const useInView = (ref: React.RefObject<HTMLElement>, threshold = 0.4) => {
  const [inView, setInView] = useState(false);
  useEffect(() => {
    const element = ref.current;
    if (!element || !('IntersectionObserver' in window)) {
      setInView(true);
      return undefined;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setInView(true);
          observer.disconnect();
        }
      },
      { threshold }
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, [ref, threshold]);
  return inView;
};

/** Splits the letter into paragraphs on blank lines; single line breaks are kept. */
const paragraphsOf = (text: string) =>
  text
    .replace(/\r\n?/g, '\n')
    .split(/\n[ \t]*\n/)
    .map((block) => block.trim())
    .filter(Boolean);

const BrandMark: React.FC<{ size?: number }> = ({ size = 22 }) => (
  <img src="/brand/logo-mark.svg" alt="" aria-hidden="true" width={size} height={size} className="of-mark" />
);

/** The credential's machine-readable strip: bar widths (in whole pixels) derived from the offer token. */
const CodeStrip: React.FC<{ seed: string }> = ({ seed }) => {
  const bars = useMemo(() => referenceBars(seed), [seed]);
  const total = bars.reduce((sum, [bar, gap]) => sum + bar + gap, 0);
  return (
    <svg className="of-code" width={total} height="22" aria-hidden="true" shapeRendering="crispEdges">
      {bars.map(([bar], index) => (
        <rect key={index} x={bars.slice(0, index).reduce((sum, [width, gap]) => sum + width + gap, 0)} y="0" width={bar} height="22" />
      ))}
    </svg>
  );
};

// Circumference of the seal's text ring (radius 36 in the 96-unit viewBox).
const SEAL_RING = (2 * Math.PI * 36).toFixed(1);

/** The organisation's seal, printed on the credential (on the main part, or on the stub on phones). */
const Seal: React.FC<{ organisation: string; place: 'main' | 'stub' }> = ({ organisation, place }) => {
  const name = organisation.toUpperCase();
  const ring = `${name} · `.repeat(name.length > 22 ? 1 : 2);
  const pathId = `of-seal-path-${place}`;
  return (
    <svg className={`of-seal of-seal--${place}`} viewBox="0 0 96 96" aria-hidden="true">
      <defs>
        <path id={pathId} d="M48 48 m-36 0 a36 36 0 1 1 72 0 a36 36 0 1 1 -72 0" />
      </defs>
      <circle cx="48" cy="48" r="45" fill="none" stroke="currentColor" strokeWidth="2.4" />
      <circle cx="48" cy="48" r="28" fill="none" stroke="currentColor" strokeWidth="1" />
      <text className="of-seal-text" fontSize="7" fill="currentColor" textLength={SEAL_RING} lengthAdjust="spacing">
        <textPath href={`#${pathId}`} startOffset="0" textLength={SEAL_RING} lengthAdjust="spacing">
          {ring}
        </textPath>
      </text>
      <g transform="translate(48 48)" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round">
        <circle r="3.6" />
        <ellipse rx="14" ry="5.4" />
        <ellipse rx="14" ry="5.4" transform="rotate(60)" />
        <ellipse rx="14" ry="5.4" transform="rotate(120)" />
      </g>
    </svg>
  );
};

/** An office date stamp; `pressed` plays the stamping motion once. */
const Stamp: React.FC<{ label: string; date: string; tone: 'accent' | 'ink'; pressed: boolean }> = ({
  label,
  date,
  tone,
  pressed,
}) => (
  <span className={`of-stamp of-stamp--${tone}${pressed ? ' is-pressed' : ''}`} aria-hidden="true">
    <span className="of-stamp-label">{label}</span>
    {date && <span className="of-stamp-date">{date}</span>}
  </span>
);

const ROLL = '01234567890123456789'.split('');

/** Digits roll into place like a mechanical counter; the amount is read out in full by screen readers. */
const Odometer: React.FC<{ value: string; run: boolean; animate: boolean }> = ({ value, run, animate }) => {
  if (!animate) return <span className="of-odo">{value}</span>;
  return (
    <span className="of-odo" aria-hidden="true">
      {value.split('').map((character, index) => {
        if (!/\d/.test(character)) {
          return (
            <span key={index} className="of-odo-sep">
              {character}
            </span>
          );
        }
        const order = (value.slice(0, index).match(/\d/g) || []).length;
        const target = run ? 10 + Number(character) : 0;
        return (
          <span key={index} className="of-odo-digit">
            <span
              className="of-odo-roll"
              style={{
                transform: `translateY(${-target}em)`,
                transitionDuration: `${1.5 + order * 0.14}s`,
              }}
            >
              {ROLL.map((digit, position) => (
                <span key={position}>{digit}</span>
              ))}
            </span>
          </span>
        );
      })}
    </span>
  );
};

/** Background and language wrapper shared by every state of the offer page. */
const OfferShell: React.FC<{ children: React.ReactNode; className?: string; language?: string }> = ({
  children,
  className = '',
  language,
}) => (
  <div className={`of ${className}`.trim()} lang={langAttr(language)}>
    {children}
  </div>
);

export const OfferLoading: React.FC<{ language?: string }> = ({ language }) => {
  const copy = copyFor(language);
  return (
    <OfferShell language={language} className="of--centre">
      <div className="of-loading" role="status">
        <span className="of-loading-line" aria-hidden="true" />
        <p>{copy.loading}</p>
      </div>
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
  <OfferShell language={language} className="of--centre">
    <main className="of-notice">
      <BrandMark size={28} />
      <h1>{title}</h1>
      <p>{body}</p>
      {actionLabel && onAction && (
        <button type="button" onClick={onAction} className="of-btn of-btn--secondary">
          {actionLabel}
        </button>
      )}
    </main>
  </OfferShell>
);

interface CredentialProps {
  offer: PublicOffer;
  copy: OfferCopy;
  language: OfferLanguage;
  reference: string;
  seed: string;
}

/** The offer as a card-stock credential: it tilts a few degrees towards the pointer, lit softly. */
const Credential: React.FC<CredentialProps> = ({ offer, copy, language, reference, seed }) => {
  const ref = useRef<HTMLDivElement>(null);
  const tilts = useMemo(() => hasFinePointer() && !prefersReducedMotion(), []);

  const onPointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    const element = ref.current;
    if (!element || !tilts) return;
    const box = element.getBoundingClientRect();
    const px = Math.min(0.5, Math.max(-0.5, (event.clientX - box.left) / box.width - 0.5));
    const py = Math.min(0.5, Math.max(-0.5, (event.clientY - box.top) / box.height - 0.5));
    element.style.setProperty('--of-ry', `${(px * 5).toFixed(2)}deg`);
    element.style.setProperty('--of-rx', `${(-py * 4).toFixed(2)}deg`);
    element.style.setProperty('--of-lx', `${((px + 0.5) * 100).toFixed(1)}%`);
    element.style.setProperty('--of-ly', `${((py + 0.5) * 100).toFixed(1)}%`);
    element.style.setProperty('--of-sx', `${(-px * 16).toFixed(1)}px`);
    element.style.setProperty('--of-sy', `${(16 - py * 10).toFixed(1)}px`);
    element.classList.add('is-live');
  };

  const onPointerLeave = () => {
    const element = ref.current;
    if (!element) return;
    ['--of-ry', '--of-rx', '--of-lx', '--of-ly', '--of-sx', '--of-sy'].forEach((name) => element.style.removeProperty(name));
    element.classList.remove('is-live');
  };

  const meta = [offer.team, offer.location, employmentLabel(offer.employment_type, language)].filter(Boolean) as string[];
  const issued = formatTimestamp(offer.sent_at, language, 'short');
  const stub: Array<[string, string]> = [
    [copy.card.issued, issued],
    [copy.card.start, formatShortDate(offer.start_date, language)],
    [copy.card.replyBy, formatShortDate(offer.respond_by, language)],
  ];

  return (
    <div className="of-card-stage">
      <div ref={ref} className="of-card" onPointerMove={onPointerMove} onPointerLeave={onPointerLeave}>
        <div className="of-card-main">
          <div className="of-card-head">
            <span className="of-card-brand">
              <BrandMark />
              {offer.organisation}
            </span>
            <span className="of-card-kind">{copy.kicker}</span>
          </div>
          {offer.candidate_name && (
            <p className="of-card-holder">
              <span>{copy.card.holder}</span> {offer.candidate_name}
            </p>
          )}
          {offer.position && <p className="of-card-position">{offer.position}</p>}
          {meta.length > 0 && (
            <ul className="of-card-meta">
              {meta.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          )}
          <Seal organisation={offer.organisation} place="main" />
        </div>
        <div className="of-card-stub">
          <Seal organisation={offer.organisation} place="stub" />
          <dl className="of-stub-list">
            <div className="of-stub-item">
              <dt>{copy.card.reference}</dt>
              <dd className="of-data">{reference}</dd>
            </div>
            <div className="of-stub-code">
              <CodeStrip seed={seed} />
            </div>
            {stub
              .filter(([, value]) => value)
              .map(([label, value]) => (
                <div key={label} className="of-stub-item">
                  <dt>{label}</dt>
                  <dd className="of-data">{value}</dd>
                </div>
              ))}
          </dl>
        </div>
      </div>
    </div>
  );
};

interface OfferExperienceProps {
  offer: PublicOffer;
  /** Admin preview: no requests are made and the buttons are disabled. */
  preview?: boolean;
  onRespond?: (decision: OfferDecision, note: string) => Promise<void>;
  onClosePreview?: () => void;
}

const OfferExperience: React.FC<OfferExperienceProps> = ({ offer, preview = false, onRespond, onClosePreview }) => {
  const language: OfferLanguage = offer.language === 'zh' ? 'zh' : 'en';
  const copy = copyFor(language);
  const animate = useMemo(() => !prefersReducedMotion(), []);
  const salaryRef = useRef<HTMLDivElement>(null);
  const replyRef = useRef<HTMLElement>(null);
  const noteRef = useRef<HTMLTextAreaElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const openerRef = useRef<HTMLElement | null>(null);
  const [dialog, setDialog] = useState<OfferDecision | null>(null);
  const [note, setNote] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [justDecided, setJustDecided] = useState(false);
  const salaryInView = useInView(salaryRef);
  const now = useNow(1000);

  const seed = useMemo(() => referenceSeed(offer, window.location.pathname), [offer]);
  const reference = useMemo(() => offerReference(seed), [seed]);
  const firstName = greetingName(offer.candidate_name);
  const salary = offer.salary || null;
  const isOpen = offer.status === 'open';
  const countdown = isOpen ? countdownTo(offer.respond_by, now) : null;
  const windowLeft = isOpen ? replyWindowLeft(offer.sent_at, offer.respond_by, now) : null;
  const benefits = offer.benefits || [];
  const paragraphs = offer.letter ? paragraphsOf(offer.letter) : [];
  const issued = formatTimestamp(offer.sent_at, language);
  const respondBy = formatLongDate(offer.respond_by, language);
  const respondedOn = formatTimestamp(offer.responded_at, language);
  const respondedShort = formatTimestamp(offer.responded_at, language, 'short');

  const facts: Array<[string, string]> = [
    [copy.team, offer.team || ''],
    [copy.location, offer.location || ''],
    [copy.employment, employmentLabel(offer.employment_type, language)],
    [copy.reportsTo, offer.reports_to || ''],
    [copy.startDate, formatLongDate(offer.start_date, language)],
    [copy.replyByLabel, respondBy],
  ].filter(([, value]) => value) as Array<[string, string]>;

  const openDialog = (decision: OfferDecision) => {
    openerRef.current = document.activeElement as HTMLElement | null;
    setError('');
    setDialog(decision);
  };

  const closeDialog = useCallback(() => {
    if (submitting) return;
    setDialog(null);
    setError('');
    const opener = openerRef.current;
    if (opener && document.contains(opener)) opener.focus();
  }, [submitting]);

  useEffect(() => {
    if (!dialog) return undefined;
    noteRef.current?.focus();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        closeDialog();
        return;
      }
      if (event.key !== 'Tab' || !dialogRef.current) return;
      const focusable = Array.prototype.slice.call(
        dialogRef.current.querySelectorAll('button:not([disabled]), textarea, [href]')
      ) as HTMLElement[];
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = previousOverflow;
    };
  }, [dialog, closeDialog]);

  const submit = async () => {
    if (!dialog || !onRespond || preview) return;
    setSubmitting(true);
    setError('');
    try {
      await onRespond(dialog, note.trim());
      setDialog(null);
      setNote('');
      setJustDecided(true);
      openerRef.current = null;
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : copy.respondFailed);
    } finally {
      setSubmitting(false);
    }
  };

  const scrollToReply = () => {
    replyRef.current?.scrollIntoView({ behavior: animate ? 'smooth' : 'auto', block: 'start' });
  };

  return (
    <OfferShell language={language} className={preview ? 'of--preview' : ''}>
      {preview && (
        <div className="of-preview" role="note">
          <span>{copy.previewBanner}</span>
          {onClosePreview && (
            <button type="button" onClick={onClosePreview} className="of-preview-close" aria-label={copy.closePreview}>
              <X aria-hidden="true" />
            </button>
          )}
        </div>
      )}

      <header className="of-top">
        <span className="of-brand">
          <BrandMark />
          <span>{offer.organisation}</span>
        </span>
        <span className="of-top-note">{copy.confidential}</span>
      </header>

      <main className="of-main">
        <section className="of-lead">
          <p className="of-lead-meta">
            <span>{copy.kicker}</span>
            {issued && <span>{copy.issued(issued)}</span>}
          </p>
          <h1 className="of-title">{copy.greeting(firstName)}</h1>
          <p className="of-intro">
            {copy.intro(offer.organisation, offer.position)}
            {isOpen && respondBy && `${copy.sentenceGap}${copy.replyRequest(respondBy)}`}
          </p>
          {isOpen && (
            <button type="button" className="of-jump" onClick={scrollToReply}>
              {copy.jump}
              <ArrowDown aria-hidden="true" />
            </button>
          )}
        </section>

        <Credential offer={offer} copy={copy} language={language} reference={reference} seed={seed} />

        {(salary || offer.extra_compensation) && (
          <section className="of-section" aria-labelledby="of-h-compensation">
            <h2 id="of-h-compensation" className="of-h2">
              {copy.compensation}
            </h2>
            <div ref={salaryRef} className="of-salary">
              {salary && (
                <>
                  <p className="of-salary-label">{copy.baseSalary}</p>
                  <p className="of-amount">
                    <span className="of-visually-hidden">
                      {salary.currency} {formatAmount(salary.amount, language)} {periodLabel(salary.period, language)}
                    </span>
                    <span className="of-amount-row" aria-hidden="true">
                      <span className="of-currency">{salary.currency}</span>
                      <Odometer value={formatAmount(salary.amount, language)} run={salaryInView} animate={animate} />
                      <span className="of-period">{periodLabel(salary.period, language)}</span>
                    </span>
                  </p>
                </>
              )}
              {offer.extra_compensation && (
                <p className={salary ? 'of-extra' : 'of-extra of-extra--alone'}>
                  {salary && <span>{copy.alsoIncluded}</span>}
                  {offer.extra_compensation}
                </p>
              )}
            </div>
          </section>
        )}

        {facts.length > 0 && (
          <section className="of-section" aria-labelledby="of-h-role">
            <h2 id="of-h-role" className="of-h2">
              {copy.role}
            </h2>
            <dl className="of-facts">
              {facts.map(([label, value]) => (
                <div key={label} className="of-fact">
                  <dt>{label}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
          </section>
        )}

        {benefits.length > 0 && (
          <section className="of-section" aria-labelledby="of-h-benefits">
            <h2 id="of-h-benefits" className="of-h2">
              {copy.benefits}
            </h2>
            <ul className="of-benefits">
              {benefits.map((benefit, index) => (
                <li key={`${benefit}-${index}`}>{benefit}</li>
              ))}
            </ul>
          </section>
        )}

        {paragraphs.length > 0 && (
          <section className="of-section" aria-labelledby="of-h-note">
            <h2 id="of-h-note" className="of-h2">
              {copy.note(offer.sender_name)}
            </h2>
            <div className="of-letter">
              {paragraphs.map((paragraph, index) => (
                <p key={index}>{paragraph}</p>
              ))}
            </div>
          </section>
        )}

        <section ref={replyRef} id="of-reply" className="of-section of-section--reply" aria-labelledby="of-h-reply">
          <div className="of-slip">
            <h2 id="of-h-reply" className="of-h2">
              {copy.replyTitle}
            </h2>

            {isOpen && (
              <>
                {countdown && (
                  <div className="of-window">
                    <div className="of-window-row">
                      <span>{countdown.passed ? copy.replyDatePassed : copy.replyBy(respondBy)}</span>
                      {!countdown.passed && (
                        <span className="of-data of-window-left">{copy.remaining(countdown.days, clockOf(countdown))}</span>
                      )}
                    </div>
                    <div className="of-line" aria-hidden="true">
                      <span style={{ width: `${(countdown.passed ? 0 : windowLeft === null ? 1 : windowLeft) * 100}%` }} />
                    </div>
                  </div>
                )}
                <p className="of-slip-body">{copy.decideBody}</p>
                <div className="of-actions">
                  <button
                    type="button"
                    className="of-btn of-btn--primary"
                    onClick={() => openDialog('accept')}
                    disabled={preview}
                    title={preview ? copy.previewBanner : undefined}
                  >
                    {copy.accept}
                  </button>
                  <button
                    type="button"
                    className="of-btn of-btn--secondary"
                    onClick={() => openDialog('decline')}
                    disabled={preview}
                    title={preview ? copy.previewBanner : undefined}
                  >
                    {copy.decline}
                  </button>
                </div>
              </>
            )}

            {offer.status === 'accepted' && (
              <div className="of-decided" role="status">
                <Stamp label={copy.stampAccepted} date={respondedShort} tone="accent" pressed={justDecided && animate} />
                <div>
                  <p className="of-decided-title">{copy.acceptedTitle(firstName)}</p>
                  <p className="of-slip-body">{copy.acceptedBody}</p>
                  {respondedOn && <p className="of-decided-meta">{copy.acceptedOn(respondedOn)}</p>}
                </div>
              </div>
            )}

            {offer.status === 'declined' && (
              <div className="of-decided" role="status">
                <Stamp label={copy.stampDeclined} date={respondedShort} tone="ink" pressed={justDecided && animate} />
                <div>
                  <p className="of-decided-title">{copy.declinedTitle}</p>
                  <p className="of-slip-body">{copy.declinedBody}</p>
                  {respondedOn && <p className="of-decided-meta">{copy.declinedOn(respondedOn)}</p>}
                </div>
              </div>
            )}
          </div>
        </section>
      </main>

      <footer className="of-foot">
        <p>{copy.privateNote}</p>
        <p>
          © {new Date().getFullYear()} {offer.organisation}
        </p>
      </footer>

      {dialog && (
        <div className="of-backdrop" role="presentation" onMouseDown={closeDialog}>
          <div
            ref={dialogRef}
            className="of-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="of-dialog-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <h2 id="of-dialog-title">{dialog === 'accept' ? copy.acceptTitle : copy.declineTitle}</h2>
            <p className="of-dialog-body">
              {dialog === 'accept' ? copy.acceptBody(offer.position, offer.organisation) : copy.declineBody}
            </p>
            <label htmlFor="of-note" className="of-label">
              {copy.messageLabel}
            </label>
            <textarea
              id="of-note"
              ref={noteRef}
              value={note}
              onChange={(event) => setNote(event.target.value)}
              maxLength={1000}
              rows={4}
              className="of-textarea"
            />
            <p className="of-counter of-data" aria-hidden="true">
              {note.length} / 1000
            </p>
            {error && (
              <p role="alert" className="of-error">
                {error}
              </p>
            )}
            <div className="of-dialog-actions">
              <button type="button" className="of-btn of-btn--secondary" onClick={closeDialog} disabled={submitting}>
                {copy.cancel}
              </button>
              <button
                type="button"
                className={`of-btn ${dialog === 'accept' ? 'of-btn--primary' : 'of-btn--danger'}`}
                onClick={submit}
                disabled={submitting}
              >
                {submitting ? copy.sending : dialog === 'accept' ? copy.confirmAccept : copy.confirmDecline}
              </button>
            </div>
          </div>
        </div>
      )}
    </OfferShell>
  );
};

export default OfferExperience;
