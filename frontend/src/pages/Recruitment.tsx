import { apiBase as restoredApiBase } from '../api/config';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Eye, RefreshCw, RotateCcw, Send, Trash2 } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import AdminTabs from '../components/AdminTabs';
import useDocumentTitle from '../utils/useDocumentTitle';
import OfferExperience from './offer/OfferExperience';
import {
  CURRENCIES,
  EMPLOYMENT_TYPES,
  OfferSalary,
  PublicOffer,
  SALARY_PERIODS,
  offerReference,
  tokenFromPath,
} from './offer/offerContent';
import {
  MANUAL_OFFER_STATUSES,
  OFFER_PLACEHOLDERS,
  OFFER_STATUS_DOT,
  OFFER_STATUS_LABELS,
  OFFER_TEMPLATES,
  OfferLanguage,
  OfferStatus,
  describeMissingPlaceholder,
  formatIsoDate,
  insertAtSelection,
  isTemplateUntouched,
  isValidEmail,
  joinWithAnd,
  loadPayDefaults,
  loadStoredLetter,
  placeholderToken,
  savePayDefaults,
  saveStoredLetter,
} from './recruitment/offerTemplates';

interface RecruitmentOffer {
  id: string;
  candidate_name: string;
  candidate_email: string;
  position: string;
  start_date?: string | null;
  respond_by?: string | null;
  language: OfferLanguage;
  subject: string;
  letter: string;
  sender_name: string;
  reply_to?: string | null;
  copy_to_sender: boolean;
  status: OfferStatus;
  delivery?: 'smtp' | 'log' | null;
  last_error?: string | null;
  send_count: number;
  created_by_email: string;
  created_at: string;
  sent_at?: string | null;
  updated_at: string;
  team?: string | null;
  location?: string | null;
  employment_type?: string | null;
  reports_to?: string | null;
  salary?: OfferSalary | null;
  extra_compensation?: string | null;
  benefits: string[];
  offer_url?: string | null;
  viewed_at?: string | null;
  view_count: number;
  responded_at?: string | null;
  response_note?: string | null;
}

interface MailStatus {
  mode: 'smtp' | 'log' | 'unavailable';
  sender?: string | null;
  detail?: string;
}

interface OfferPreview {
  subject: string;
  html: string;
  from?: string | null;
  to: string;
  reply_to?: string | null;
  bcc?: string | null;
  missing: string[];
  unknown: string[];
  warnings: string[];
  hero_cid: string;
  page: PublicOffer;
}

const apiBase = () => {
  const host = window.location.hostname || '127.0.0.1';
  const localApiHost = host === 'localhost' || host === '127.0.0.1';
  return restoredApiBase() || (localApiHost ? 'http://127.0.0.1:8000' : '');
};

const formatDateTime = (value?: string | null) => {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
};

// The short reference printed on the candidate's offer page and in the email.
const referenceOf = (offerUrl?: string | null) => {
  if (!offerUrl) return '';
  try {
    const token = tokenFromPath(new URL(offerUrl).pathname);
    return token ? offerReference(token) : '';
  } catch {
    return '';
  }
};

const readJson = async (response: Response) => {
  try {
    return await response.json();
  } catch {
    return {};
  }
};

const errorMessage = (payload: unknown, fallback: string): string => {
  if (!payload || typeof payload !== 'object') return fallback;
  const data = payload as { detail?: unknown; message?: unknown };
  if (typeof data.detail === 'string') return data.detail;
  if (Array.isArray(data.detail)) {
    const messages = data.detail.map((item: unknown) => {
      if (!item || typeof item !== 'object') return '';
      const message = (item as { msg?: unknown }).msg;
      return typeof message === 'string' ? message : '';
    }).filter(Boolean);
    if (messages.length) return messages.join(' ');
  }
  return typeof data.message === 'string' ? data.message : fallback;
};

// Fields the backend fills from the form itself; a missing one is reported as a required field instead.
const FORM_PLACEHOLDERS = new Set(['candidate_name', 'position']);

const Recruitment: React.FC = () => {
  const { token, user } = useAuth();
  const base = useMemo(() => apiBase(), []);
  useDocumentTitle('Recruitment');

  const [initialLetter] = useState(() => {
    const stored = loadStoredLetter();
    const language: OfferLanguage = stored?.language || 'en';
    return {
      language,
      subject: stored?.subject ?? OFFER_TEMPLATES[language].subject,
      letter: stored?.letter ?? OFFER_TEMPLATES[language].letter,
    };
  });
  const [candidateName, setCandidateName] = useState('');
  const [candidateEmail, setCandidateEmail] = useState('');
  const [position, setPosition] = useState('');
  const [team, setTeam] = useState('');
  const [location, setLocation] = useState('');
  const [employmentType, setEmploymentType] = useState('full_time');
  const [reportsTo, setReportsTo] = useState('');
  const [salaryAmount, setSalaryAmount] = useState('');
  const [payDefaults] = useState(() => loadPayDefaults(CURRENCIES, SALARY_PERIODS.map((period) => period.value)));
  const [salaryCurrency, setSalaryCurrency] = useState(payDefaults.currency);
  const [salaryPeriod, setSalaryPeriod] = useState(payDefaults.period);
  const [extraCompensation, setExtraCompensation] = useState('');
  const [benefitsText, setBenefitsText] = useState('');
  const [startDate, setStartDate] = useState('');
  const [respondBy, setRespondBy] = useState('');
  const [language, setLanguage] = useState<OfferLanguage>(initialLetter.language);
  const [subject, setSubject] = useState(initialLetter.subject);
  const [letter, setLetter] = useState(initialLetter.letter);
  const [replyToSender, setReplyToSender] = useState(true);
  const [copyToSender, setCopyToSender] = useState(false);

  const [offers, setOffers] = useState<RecruitmentOffer[]>([]);
  const [mail, setMail] = useState<MailStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');

  const [preview, setPreview] = useState<OfferPreview | null>(null);
  const [previewError, setPreviewError] = useState('');
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewHeight, setPreviewHeight] = useState(560);
  const [showPagePreview, setShowPagePreview] = useState(false);

  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState('');
  const [notice, setNotice] = useState('');
  const [busyOfferId, setBusyOfferId] = useState<string | null>(null);
  const [expandedOfferId, setExpandedOfferId] = useState<string | null>(null);
  const [listMessage, setListMessage] = useState('');

  const [languageNote, setLanguageNote] = useState('');

  const letterRef = useRef<HTMLTextAreaElement>(null);
  // Where the caret was in the message box; placeholders go at the end until it has been used.
  const letterSelectionRef = useRef<{ start: number; end: number } | null>(null);
  const previewFrameRef = useRef<HTMLIFrameElement>(null);

  const authHeaders = useCallback(
    (json = false): HeadersInit => ({
      ...(json ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    }),
    [token]
  );

  const loadOffers = useCallback(async () => {
    setLoading(true);
    setLoadError('');
    try {
      const response = await fetch(`${base}/admin/recruitment/offers?limit=200`, { headers: authHeaders() });
      const payload = await readJson(response);
      if (!response.ok) throw new Error(errorMessage(payload, 'Unable to load offers'));
      setOffers(Array.isArray(payload.offers) ? payload.offers : []);
      setMail(payload.mail || null);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : 'Unable to load offers');
    } finally {
      setLoading(false);
    }
  }, [authHeaders, base]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- initial async load also resets the visible loading state
    void loadOffers();
  }, [loadOffers]);

  useEffect(() => {
    saveStoredLetter(language, subject, letter);
  }, [language, subject, letter]);

  useEffect(() => {
    savePayDefaults({ currency: salaryCurrency, period: salaryPeriod });
  }, [salaryCurrency, salaryPeriod]);

  const draft = useMemo(
    () => ({
      candidate_name: candidateName,
      candidate_email: candidateEmail.trim(),
      position,
      team,
      location,
      employment_type: employmentType,
      reports_to: reportsTo,
      salary_amount: salaryAmount.trim(),
      salary_currency: salaryCurrency,
      salary_period: salaryPeriod,
      extra_compensation: extraCompensation,
      benefits: benefitsText
        .split('\n')
        .map((item) => item.trim())
        .filter(Boolean),
      start_date: startDate,
      respond_by: respondBy,
      language,
      subject,
      letter,
      reply_to_sender: replyToSender,
      copy_to_sender: copyToSender,
    }),
    [
      candidateName,
      candidateEmail,
      position,
      team,
      location,
      employmentType,
      reportsTo,
      salaryAmount,
      salaryCurrency,
      salaryPeriod,
      extraCompensation,
      benefitsText,
      startDate,
      respondBy,
      language,
      subject,
      letter,
      replyToSender,
      copyToSender,
    ]
  );

  // Render the email on the server as the admin types, so the preview is exactly what gets sent.
  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setPreviewLoading(true);
      try {
        const response = await fetch(`${base}/admin/recruitment/offers/preview`, {
          method: 'POST',
          headers: authHeaders(true),
          body: JSON.stringify(draft),
          signal: controller.signal,
        });
        const payload = await readJson(response);
        if (!response.ok) throw new Error(errorMessage(payload, 'Preview unavailable'));
        setPreview(payload);
        setPreviewError('');
      } catch (err) {
        if (controller.signal.aborted) return;
        setPreviewError(err instanceof Error ? err.message : 'Preview unavailable');
      } finally {
        if (!controller.signal.aborted) setPreviewLoading(false);
      }
    }, 350);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [authHeaders, base, draft]);

  const measurePreview = useCallback(() => {
    const doc = previewFrameRef.current?.contentDocument;
    const height = doc?.body?.scrollHeight || doc?.documentElement?.scrollHeight;
    if (height) setPreviewHeight(Math.max(320, height));
  }, []);

  useEffect(() => {
    window.addEventListener('resize', measurePreview);
    return () => window.removeEventListener('resize', measurePreview);
  }, [measurePreview]);

  useEffect(() => {
    if (!showPagePreview) return undefined;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setShowPagePreview(false);
    };
    document.addEventListener('keydown', onKey);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener('keydown', onKey);
    };
  }, [showPagePreview]);

  // The email embeds its banner as an attachment; the preview loads the same file from the API.
  const previewHtml = preview
    ? preview.html.split(`cid:${preview.hero_cid}`).join(`${base}/recruitment-assets/offer-hero.gif`)
    : '';

  const templateUntouched = isTemplateUntouched(language, subject, letter);

  // Switching language swaps in that template unless the admin has written their own letter;
  // the language still sets the date format and labels in the email.
  const switchLanguage = (next: OfferLanguage) => {
    if (next === language) return;
    if (templateUntouched) {
      setSubject(OFFER_TEMPLATES[next].subject);
      setLetter(OFFER_TEMPLATES[next].letter);
      letterSelectionRef.current = null;
      setLanguageNote('');
    } else {
      setLanguageNote(
        `Your edited letter was kept. Choose “Reset to template” for the ${next === 'zh' ? 'Chinese' : 'English'} wording.`
      );
    }
    setLanguage(next);
  };

  const resetTemplate = () => {
    if (!window.confirm('Replace the subject and letter with the standard template? Your edits will be lost.')) return;
    setSubject(OFFER_TEMPLATES[language].subject);
    setLetter(OFFER_TEMPLATES[language].letter);
    letterSelectionRef.current = null;
    setLanguageNote('');
  };

  const insertPlaceholder = (key: string) => {
    const textarea = letterRef.current;
    const selection = letterSelectionRef.current || { start: letter.length, end: letter.length };
    const next = insertAtSelection(letter, placeholderToken(key), selection.start, selection.end);
    letterSelectionRef.current = { start: next.cursor, end: next.cursor };
    setLetter(next.value);
    window.requestAnimationFrame(() => {
      textarea?.focus();
      textarea?.setSelectionRange(next.cursor, next.cursor);
    });
  };

  const missingFields = [
    !candidateName.trim() && "the candidate's name",
    !isValidEmail(candidateEmail.trim()) && 'a valid email address',
    !position.trim() && 'the position',
    !subject.trim() && 'a subject',
    !letter.trim() && 'the letter',
  ].filter(Boolean) as string[];
  const placeholderIssues = preview
    ? [
        ...preview.missing.filter((key) => !FORM_PLACEHOLDERS.has(key)).map(describeMissingPlaceholder),
        ...preview.unknown.map((token) => `${token} isn't a placeholder this page can fill in.`),
      ]
    : [];
  const mailUnavailable = mail?.mode === 'unavailable';
  const canSend = !sending && !!preview && !mailUnavailable && missingFields.length === 0 && placeholderIssues.length === 0;
  const sendHint = mailUnavailable
    ? 'Email delivery is not set up on the server.'
    : missingFields.length > 0
      ? `Add ${joinWithAnd(missingFields)} to send.`
      : placeholderIssues.length > 0
        ? 'Fix the placeholders above to send.'
        : '';

  const sendOffer = async () => {
    if (!canSend) return;
    const recipient = `${candidateName.trim()} <${candidateEmail.trim()}>`;
    if (!window.confirm(`Send the offer for ${position.trim()} to ${recipient}?`)) return;
    setSending(true);
    setSendError('');
    setNotice('');
    try {
      const response = await fetch(`${base}/admin/recruitment/offers`, {
        method: 'POST',
        headers: authHeaders(true),
        body: JSON.stringify(draft),
      });
      const payload = await readJson(response);
      if (!response.ok) throw new Error(errorMessage(payload, 'The offer was not sent.'));
      const offer = payload.offer as RecruitmentOffer;
      setNotice(
        payload.delivery === 'log'
          ? `Offer to ${offer.candidate_name} recorded. Email delivery is off on this server, so nothing was emailed.`
          : `Offer sent to ${offer.candidate_name} (${offer.candidate_email}).`
      );
      setCandidateName('');
      setCandidateEmail('');
      setOffers((prev) => [offer, ...prev.filter((item) => item.id !== offer.id)]);
    } catch (err) {
      setSendError(err instanceof Error ? err.message : 'The offer was not sent.');
      // A failed delivery is kept on the server so it can be retried from the list.
      loadOffers();
    } finally {
      setSending(false);
    }
  };

  const replaceOffer = (offer: RecruitmentOffer) =>
    setOffers((prev) => prev.map((item) => (item.id === offer.id ? offer : item)));

  const changeStatus = async (offer: RecruitmentOffer, status: OfferStatus) => {
    setBusyOfferId(offer.id);
    setListMessage('');
    try {
      const response = await fetch(`${base}/admin/recruitment/offers/${encodeURIComponent(offer.id)}`, {
        method: 'PATCH',
        headers: authHeaders(true),
        body: JSON.stringify({ status }),
      });
      const payload = await readJson(response);
      if (!response.ok) throw new Error(errorMessage(payload, 'Unable to update the offer'));
      replaceOffer(payload.offer);
    } catch (err) {
      setListMessage(err instanceof Error ? err.message : 'Unable to update the offer');
    } finally {
      setBusyOfferId(null);
    }
  };

  const resendOffer = async (offer: RecruitmentOffer) => {
    const question =
      offer.status === 'failed'
        ? `Try sending the offer to ${offer.candidate_email} again?`
        : `Send the same offer to ${offer.candidate_email} again?`;
    if (!window.confirm(question)) return;
    setBusyOfferId(offer.id);
    setListMessage('');
    try {
      const response = await fetch(`${base}/admin/recruitment/offers/${encodeURIComponent(offer.id)}/resend`, {
        method: 'POST',
        headers: authHeaders(),
      });
      const payload = await readJson(response);
      if (!response.ok) throw new Error(errorMessage(payload, 'The offer was not sent.'));
      replaceOffer(payload.offer);
      setListMessage(
        payload.delivery === 'log'
          ? `Offer to ${offer.candidate_name} recorded again. Email delivery is off, so nothing was emailed.`
          : `Offer sent to ${offer.candidate_email} again.`
      );
    } catch (err) {
      setListMessage(err instanceof Error ? err.message : 'The offer was not sent.');
      loadOffers();
    } finally {
      setBusyOfferId(null);
    }
  };

  const copyOfferLink = async (offer: RecruitmentOffer) => {
    if (!offer.offer_url) return;
    try {
      await navigator.clipboard.writeText(offer.offer_url);
      setListMessage(`Link to ${offer.candidate_name}'s offer page copied.`);
    } catch {
      window.prompt('Copy the offer link:', offer.offer_url);
    }
  };

  const deleteOffer = async (offer: RecruitmentOffer) => {
    if (!window.confirm(`Delete the record of the offer to ${offer.candidate_name}? An email that was already sent is not recalled.`)) {
      return;
    }
    setBusyOfferId(offer.id);
    setListMessage('');
    try {
      const response = await fetch(`${base}/admin/recruitment/offers/${encodeURIComponent(offer.id)}`, {
        method: 'DELETE',
        headers: authHeaders(),
      });
      const payload = await readJson(response);
      if (!response.ok) throw new Error(errorMessage(payload, 'Unable to delete the offer'));
      setOffers((prev) => prev.filter((item) => item.id !== offer.id));
    } catch (err) {
      setListMessage(err instanceof Error ? err.message : 'Unable to delete the offer');
    } finally {
      setBusyOfferId(null);
    }
  };

  const counts = offers.reduce<Record<string, number>>((acc, offer) => {
    acc[offer.status] = (acc[offer.status] || 0) + 1;
    return acc;
  }, {});
  const metrics: Array<{ label: string; value: number; tone?: 'ok' | 'err' }> = [
    { label: 'Offers', value: offers.length },
    { label: 'Awaiting reply', value: counts.sent || 0 },
    { label: 'Accepted', value: counts.accepted || 0, tone: 'ok' },
    { label: 'Declined', value: counts.declined || 0 },
    { label: 'Not delivered', value: counts.failed || 0, tone: 'err' },
  ];

  const fromLabel =
    preview?.from || (mail?.mode === 'log' ? 'Not emailed (delivery is off)' : mail ? 'Not configured' : '—');

  return (
    <div className="mx-auto max-w-content px-5 pb-24 pt-10 sm:px-8 lg:pt-14">
      <AdminTabs />

      <header className="mt-8 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="page-title">Recruitment</h1>
          <p className="mt-1 text-sm text-ink-3">Email offer letters to candidates and keep track of their replies.</p>
        </div>
        <button type="button" onClick={loadOffers} disabled={loading} className="btn btn-secondary btn-sm">
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </header>

      {loadError && (
        <div role="alert" className="mt-6 rounded-lg border border-err-line bg-err-bg px-4 py-3 text-sm text-err">
          <p className="font-medium">Offers unavailable</p>
          <p className="mt-0.5">{loadError}</p>
        </div>
      )}
      {mail?.mode === 'unavailable' && (
        <div role="alert" className="mt-6 rounded-lg border border-err-line bg-err-bg px-4 py-3 text-sm text-err">
          <p className="font-medium">Offers can’t be emailed yet</p>
          <p className="mt-0.5">
            {mail.detail} Configure the MAIL_* settings on the backend, then refresh. You can still write and preview offers.
          </p>
        </div>
      )}
      {mail?.mode === 'log' && (
        <div role="status" className="mt-6 rounded-lg border border-warn-line bg-warn-bg px-4 py-3 text-sm text-warn">
          <p className="font-medium">Test mode: email delivery is off</p>
          <p className="mt-0.5">{mail.detail}</p>
        </div>
      )}

      <dl className="mt-8 grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-line bg-line sm:grid-cols-5">
        {metrics.map((metric) => (
          <div key={metric.label} className="bg-white px-4 py-4 first:col-span-2 sm:first:col-span-1">
            <dt className="text-xs text-ink-4">{metric.label}</dt>
            <dd
              className={`mt-1 text-2xl font-medium tabular-nums ${
                metric.tone === 'err' && metric.value > 0
                  ? 'text-err'
                  : metric.tone === 'ok' && metric.value > 0
                    ? 'text-ok'
                    : 'text-ink'
              }`}
            >
              {metric.value.toLocaleString()}
            </dd>
          </div>
        ))}
      </dl>

      <div className="mt-12 grid gap-10 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
        <form onSubmit={(event) => event.preventDefault()} noValidate aria-labelledby="new-offer-heading">
          <h2 id="new-offer-heading" className="text-base font-semibold text-ink">New offer</h2>
          <p className="mt-0.5 text-sm text-ink-3">
            Each offer goes to one candidate. The details and letter stay filled in for the next one.
          </p>

          <fieldset className="mt-6">
            <legend className="section-label">Candidate</legend>
            <div className="mt-2 grid gap-4 sm:grid-cols-2">
              <div>
                <label htmlFor="offer-candidate-name" className="field-label">Full name</label>
                <input
                  id="offer-candidate-name"
                  value={candidateName}
                  onChange={(event) => setCandidateName(event.target.value)}
                  className="input"
                  maxLength={120}
                  autoComplete="off"
                />
              </div>
              <div>
                <label htmlFor="offer-candidate-email" className="field-label">Email</label>
                <input
                  id="offer-candidate-email"
                  value={candidateEmail}
                  onChange={(event) => setCandidateEmail(event.target.value)}
                  className="input"
                  type="email"
                  maxLength={254}
                  autoComplete="off"
                  placeholder="name@example.com"
                />
              </div>
            </div>
          </fieldset>

          <fieldset className="mt-6">
            <legend className="section-label">Offer</legend>
            <div className="mt-2">
              <label htmlFor="offer-position" className="field-label">Position</label>
              <input
                id="offer-position"
                value={position}
                onChange={(event) => setPosition(event.target.value)}
                className="input"
                maxLength={160}
                placeholder="e.g. Research assistant"
              />
            </div>
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              <div>
                <label htmlFor="offer-team" className="field-label">
                  Team <span className="font-normal text-ink-4">(optional)</span>
                </label>
                <input
                  id="offer-team"
                  value={team}
                  onChange={(event) => setTeam(event.target.value)}
                  className="input"
                  maxLength={120}
                  placeholder="e.g. Research & Engineering"
                />
              </div>
              <div>
                <label htmlFor="offer-employment-type" className="field-label">Employment type</label>
                <select
                  id="offer-employment-type"
                  value={employmentType}
                  onChange={(event) => setEmploymentType(event.target.value)}
                  className="input"
                >
                  <option value="">Not specified</option>
                  {EMPLOYMENT_TYPES.map((type) => (
                    <option key={type.value} value={type.value}>{type.en}</option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="offer-location" className="field-label">
                  Location <span className="font-normal text-ink-4">(optional)</span>
                </label>
                <input
                  id="offer-location"
                  value={location}
                  onChange={(event) => setLocation(event.target.value)}
                  className="input"
                  maxLength={120}
                  placeholder="e.g. Remote, or the office city"
                />
              </div>
              <div>
                <label htmlFor="offer-reports-to" className="field-label">
                  Reports to <span className="font-normal text-ink-4">(optional)</span>
                </label>
                <input
                  id="offer-reports-to"
                  value={reportsTo}
                  onChange={(event) => setReportsTo(event.target.value)}
                  className="input"
                  maxLength={120}
                />
              </div>
            </div>
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              <div>
                <label htmlFor="offer-start-date" className="field-label">
                  Start date <span className="font-normal text-ink-4">(optional)</span>
                </label>
                <input
                  id="offer-start-date"
                  type="date"
                  value={startDate}
                  onChange={(event) => setStartDate(event.target.value)}
                  className="input"
                />
              </div>
              <div>
                <label htmlFor="offer-respond-by" className="field-label">
                  Reply by <span className="font-normal text-ink-4">(optional)</span>
                </label>
                <input
                  id="offer-respond-by"
                  type="date"
                  value={respondBy}
                  onChange={(event) => setRespondBy(event.target.value)}
                  className="input"
                />
              </div>
            </div>
          </fieldset>

          <fieldset className="mt-6">
            <legend className="section-label">Compensation</legend>
            <p className="field-hint mt-1">Shown on the candidate's offer page, not in the email itself.</p>
            <div className="mt-3 grid gap-4 sm:grid-cols-[minmax(0,1.4fr)_minmax(0,0.8fr)_minmax(0,1fr)]">
              <div>
                <label htmlFor="offer-salary" className="field-label">
                  Salary <span className="font-normal text-ink-4">(optional)</span>
                </label>
                <input
                  id="offer-salary"
                  value={salaryAmount}
                  onChange={(event) => setSalaryAmount(event.target.value)}
                  className="input"
                  inputMode="decimal"
                  maxLength={16}
                  placeholder="e.g. 95000"
                />
              </div>
              <div>
                <label htmlFor="offer-currency" className="field-label">Currency</label>
                <select
                  id="offer-currency"
                  value={salaryCurrency}
                  onChange={(event) => setSalaryCurrency(event.target.value)}
                  className="input"
                >
                  {CURRENCIES.map((currency) => (
                    <option key={currency} value={currency}>{currency}</option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="offer-period" className="field-label">Paid</label>
                <select
                  id="offer-period"
                  value={salaryPeriod}
                  onChange={(event) => setSalaryPeriod(event.target.value)}
                  className="input"
                >
                  {SALARY_PERIODS.map((period) => (
                    <option key={period.value} value={period.value}>{period.en}</option>
                  ))}
                </select>
              </div>
            </div>
            <div className="mt-4">
              <label htmlFor="offer-extra" className="field-label">
                Also included <span className="font-normal text-ink-4">(optional)</span>
              </label>
              <input
                id="offer-extra"
                value={extraCompensation}
                onChange={(event) => setExtraCompensation(event.target.value)}
                className="input"
                maxLength={200}
                placeholder="e.g. 10% annual bonus and equity"
              />
            </div>
            <div className="mt-4">
              <label htmlFor="offer-benefits" className="field-label">
                Benefits <span className="font-normal text-ink-4">(one per line, optional)</span>
              </label>
              <textarea
                id="offer-benefits"
                value={benefitsText}
                onChange={(event) => setBenefitsText(event.target.value)}
                className="input text-[14px]"
                rows={4}
                placeholder={'Flexible working hours\nConference and learning budget\nLatest MacBook Pro'}
              />
            </div>
          </fieldset>

          <fieldset className="mt-6">
            <legend className="section-label">Letter</legend>
            <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
              <div className="segmented" role="group" aria-label="Email language">
                <button type="button" aria-pressed={language === 'en'} onClick={() => switchLanguage('en')}>
                  English
                </button>
                <button type="button" aria-pressed={language === 'zh'} onClick={() => switchLanguage('zh')} lang="zh-CN">
                  中文
                </button>
              </div>
              <button type="button" onClick={resetTemplate} disabled={templateUntouched} className="btn btn-ghost btn-sm">
                <RotateCcw className="h-3.5 w-3.5" />
                Reset to template
              </button>
            </div>
            <p className="field-hint">
              {languageNote || 'The language sets the template, the date format and the labels in the email.'}
            </p>

            <div className="mt-4">
              <label htmlFor="offer-subject" className="field-label">Subject</label>
              <input
                id="offer-subject"
                value={subject}
                onChange={(event) => setSubject(event.target.value)}
                className="input"
                maxLength={200}
              />
            </div>
            <div className="mt-4">
              <label htmlFor="offer-letter" className="field-label">Message</label>
              <textarea
                id="offer-letter"
                ref={letterRef}
                value={letter}
                onChange={(event) => setLetter(event.target.value)}
                onSelect={(event) => {
                  letterSelectionRef.current = {
                    start: event.currentTarget.selectionStart,
                    end: event.currentTarget.selectionEnd,
                  };
                }}
                className="input text-[14px]"
                rows={16}
                maxLength={10000}
              />
              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                <span className="mr-0.5 text-xs text-ink-4">Insert</span>
                {OFFER_PLACEHOLDERS.map((placeholder) => (
                  <button
                    key={placeholder.key}
                    type="button"
                    onClick={() => insertPlaceholder(placeholder.key)}
                    className="tag transition-colors hover:border-line-strong hover:text-ink"
                    title={`Insert ${placeholderToken(placeholder.key)}`}
                  >
                    {placeholder.label}
                  </button>
                ))}
              </div>
              <p className="field-hint">
                Placeholders such as {placeholderToken('candidate_name')} are filled in for each candidate; the preview shows
                the result.
              </p>
            </div>
          </fieldset>

          <fieldset className="mt-6">
            <legend className="section-label">Replies</legend>
            <label className="mt-2 flex items-start gap-2.5 text-sm text-ink-2">
              <input
                type="checkbox"
                checked={replyToSender}
                onChange={(event) => setReplyToSender(event.target.checked)}
                className="mt-[3px] h-4 w-4 shrink-0 accent-ink"
              />
              <span>
                Send the candidate’s replies to <span className="text-ink">{user?.email || 'my email'}</span>
              </span>
            </label>
            <label className="mt-2 flex items-start gap-2.5 text-sm text-ink-2">
              <input
                type="checkbox"
                checked={copyToSender}
                onChange={(event) => setCopyToSender(event.target.checked)}
                className="mt-[3px] h-4 w-4 shrink-0 accent-ink"
              />
              <span>Send me a copy (Bcc)</span>
            </label>
          </fieldset>
        </form>

        <section aria-labelledby="offer-preview-heading" className="min-w-0 lg:sticky lg:top-[84px] lg:self-start">
          <div className="flex items-baseline justify-between gap-3">
            <h2 id="offer-preview-heading" className="text-base font-semibold text-ink">Preview</h2>
            <span className="text-xs text-ink-4">{previewLoading ? 'Updating…' : 'What the candidate receives'}</span>
          </div>
          <div className="panel mt-3 overflow-hidden">
            <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1.5 border-b border-line px-4 py-3 text-sm">
              <dt className="text-ink-4">From</dt>
              <dd className="truncate text-ink-2">{fromLabel}</dd>
              <dt className="text-ink-4">To</dt>
              <dd className="truncate text-ink-2">{preview?.to || '—'}</dd>
              {preview?.reply_to && (
                <>
                  <dt className="text-ink-4">Reply-to</dt>
                  <dd className="truncate text-ink-2">{preview.reply_to}</dd>
                </>
              )}
              {preview?.bcc && (
                <>
                  <dt className="text-ink-4">Bcc</dt>
                  <dd className="truncate text-ink-2">{preview.bcc}</dd>
                </>
              )}
              <dt className="text-ink-4">Subject</dt>
              <dd className="font-medium text-ink">{preview?.subject || '—'}</dd>
            </dl>
            {preview ? (
              <iframe
                ref={previewFrameRef}
                title="Offer email preview"
                sandbox="allow-same-origin"
                srcDoc={previewHtml}
                onLoad={measurePreview}
                style={{ height: previewHeight }}
                className="block w-full border-0 bg-paper"
              />
            ) : (
              <p className="px-4 py-20 text-center text-sm text-ink-4">{previewError || 'Loading preview…'}</p>
            )}
          </div>
          {preview && previewError && <p className="mt-2 text-xs text-err">Preview not updated: {previewError}</p>}

          {(placeholderIssues.length > 0 || (preview?.warnings.length || 0) > 0) && (
            <ul className="mt-4 space-y-1.5 text-sm">
              {placeholderIssues.map((issue) => (
                <li key={issue} className="flex items-start gap-2 text-err">
                  <span className="status-dot mt-[7px] bg-err" />
                  {issue}
                </li>
              ))}
              {preview?.warnings.map((warning) => (
                <li key={warning} className="flex items-start gap-2 text-warn">
                  <span className="status-dot mt-[7px] bg-warn" />
                  {warning}
                </li>
              ))}
            </ul>
          )}

          <div className="mt-5 flex flex-wrap items-center justify-end gap-3">
            {sendHint && <p className="mr-auto text-xs text-ink-4">{sendHint}</p>}
            <button
              type="button"
              onClick={() => setShowPagePreview(true)}
              disabled={!preview?.page}
              className="btn btn-secondary"
            >
              <Eye className="h-4 w-4" />
              Preview offer page
            </button>
            <button type="button" onClick={sendOffer} disabled={!canSend} className="btn btn-primary">
              <Send className="h-4 w-4" />
              {sending ? 'Sending…' : 'Send offer'}
            </button>
          </div>
          {sendError && (
            <div role="alert" className="mt-4 rounded-lg border border-err-line bg-err-bg px-4 py-3 text-sm text-err">
              {sendError}
            </div>
          )}
          {notice && (
            <p role="status" className="mt-4 rounded-lg border border-ok-line bg-ok-bg px-4 py-3 text-sm text-ok">
              {notice}
            </p>
          )}
        </section>
      </div>

      <section className="mt-16" aria-labelledby="sent-offers-heading">
        <div className="flex flex-wrap items-end justify-between gap-3 border-b border-line pb-3">
          <div>
            <h2 id="sent-offers-heading" className="text-base font-semibold text-ink">Sent offers</h2>
            <p className="mt-0.5 text-sm text-ink-3">
              Set the status when a candidate replies. Status changes are for your records; the candidate isn’t notified.
            </p>
          </div>
          {loading && <span className="text-xs text-ink-4">Loading…</span>}
        </div>
        {listMessage && (
          <p role="status" className="mt-4 rounded-lg bg-paper-sunken px-3 py-2 text-sm text-ink-2">
            {listMessage}
          </p>
        )}
        <div className="relative mt-1 overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-line text-xs text-ink-4">
                <th className="py-2.5 pr-6 font-medium">Candidate</th>
                <th className="py-2.5 pr-6 font-medium">Position</th>
                <th className="py-2.5 pr-6 font-medium">Sent</th>
                <th className="py-2.5 pr-6 font-medium">Reply by</th>
                <th className="py-2.5 pr-6 font-medium">Status</th>
                <th className="py-2.5 font-medium"><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {offers.map((offer) => {
                const isBusy = busyOfferId === offer.id;
                const isExpanded = expandedOfferId === offer.id;
                return (
                  <React.Fragment key={offer.id}>
                    <tr className="align-top">
                      <td className="py-3.5 pr-6">
                        <div className="font-medium text-ink">{offer.candidate_name}</div>
                        <div className="text-xs text-ink-4">{offer.candidate_email}</div>
                      </td>
                      <td className="py-3.5 pr-6 text-ink-2">
                        {offer.position}
                        {offer.language === 'zh' && (
                          <span className="tag ml-2 h-5 px-1.5 text-2xs" lang="zh-CN">中文</span>
                        )}
                      </td>
                      <td className="whitespace-nowrap py-3.5 pr-6 text-ink-3">
                        <div>{formatDateTime(offer.sent_at || offer.created_at)}</div>
                        <div className="text-xs text-ink-4">
                          by {offer.created_by_email}
                          {offer.send_count > 1 ? ` · sent ${offer.send_count} times` : ''}
                        </div>
                      </td>
                      <td className="whitespace-nowrap py-3.5 pr-6 text-ink-3">{formatIsoDate(offer.respond_by)}</td>
                      <td className="py-3.5 pr-6">
                        {offer.status === 'failed' ? (
                          <>
                            <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-err">
                              <span className="status-dot bg-err" />
                              {OFFER_STATUS_LABELS.failed}
                            </span>
                            {offer.last_error && (
                              <div className="mt-0.5 max-w-[16rem] text-xs text-ink-4">{offer.last_error}</div>
                            )}
                          </>
                        ) : offer.status === 'sending' ? (
                          <span className="inline-flex items-center gap-2 whitespace-nowrap text-ink-3">
                            <span className="cg-working" />
                            {OFFER_STATUS_LABELS.sending}
                          </span>
                        ) : (
                          <div className="flex items-center gap-2">
                            <span className={`status-dot ${OFFER_STATUS_DOT[offer.status] || 'bg-line-strong'}`} />
                            <select
                              value={offer.status}
                              onChange={(event) => changeStatus(offer, event.target.value as OfferStatus)}
                              disabled={isBusy}
                              className="input h-8 w-auto py-0 pl-2 text-[13px]"
                              aria-label={`Status of the offer to ${offer.candidate_name}`}
                            >
                              {MANUAL_OFFER_STATUSES.map((status) => (
                                <option key={status} value={status}>{OFFER_STATUS_LABELS[status]}</option>
                              ))}
                            </select>
                          </div>
                        )}
                        {offer.delivery === 'log' && <div className="mt-1 text-xs text-warn">Test mode: not emailed</div>}
                        {offer.responded_at ? (
                          <div className="mt-1 text-xs text-ink-4">Candidate replied {formatDateTime(offer.responded_at)}</div>
                        ) : offer.view_count > 0 ? (
                          <div className="mt-1 text-xs text-ink-4" title={`First opened ${formatDateTime(offer.viewed_at)}`}>
                            Opened {offer.view_count === 1 ? 'once' : `${offer.view_count} times`}
                          </div>
                        ) : (
                          offer.sent_at && offer.status === 'sent' && <div className="mt-1 text-xs text-ink-4">Not opened yet</div>
                        )}
                      </td>
                      <td className="py-3 text-right">
                        <div className="flex justify-end gap-1">
                          <button
                            type="button"
                            onClick={() => setExpandedOfferId(isExpanded ? null : offer.id)}
                            aria-expanded={isExpanded}
                            className="btn btn-ghost btn-sm"
                          >
                            {isExpanded ? 'Hide' : 'View'}
                          </button>
                          {offer.offer_url && offer.sent_at && (
                            <button type="button" onClick={() => copyOfferLink(offer)} className="btn btn-ghost btn-sm">
                              Copy link
                            </button>
                          )}
                          {(offer.status === 'sent' || offer.status === 'failed') && (
                            <button
                              type="button"
                              onClick={() => resendOffer(offer)}
                              disabled={isBusy}
                              className="btn btn-ghost btn-sm"
                            >
                              {offer.status === 'failed' ? 'Retry' : 'Resend'}
                            </button>
                          )}
                          <button
                            type="button"
                            onClick={() => deleteOffer(offer)}
                            disabled={isBusy || offer.status === 'sending'}
                            className="btn btn-ghost btn-sm hover:text-err"
                            aria-label={`Delete the offer to ${offer.candidate_name}`}
                            title="Delete"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr>
                        <td colSpan={6} className="pb-5 pt-1">
                          <div className="rounded-lg border border-line bg-white px-4 py-3">
                            <p className="text-xs text-ink-4">Subject</p>
                            <p className="mt-0.5 font-medium text-ink">{offer.subject}</p>
                            {offer.response_note && (
                              <div className="mt-3 rounded-md border border-line bg-paper-sunken px-3 py-2 text-sm text-ink-2">
                                <span className="text-xs text-ink-4">Message from the candidate</span>
                                <p className="mt-0.5 whitespace-pre-wrap">{offer.response_note}</p>
                              </div>
                            )}
                            <dl className="mt-3 grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
                              {[
                                ['Reference', referenceOf(offer.offer_url)],
                                ['Salary', offer.salary?.formatted],
                                ['Also included', offer.extra_compensation],
                                ['Team', offer.team],
                                ['Location', offer.location],
                                ['Employment', EMPLOYMENT_TYPES.find((type) => type.value === offer.employment_type)?.en],
                                ['Reports to', offer.reports_to],
                                ['Benefits', offer.benefits.join(' · ')],
                              ]
                                .filter(([, value]) => value)
                                .map(([label, value]) => (
                                  <div key={label} className="flex gap-2">
                                    <dt className="text-ink-4">{label}</dt>
                                    <dd className="text-ink-2">{value}</dd>
                                  </div>
                                ))}
                            </dl>
                            <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-ink-2">{offer.letter}</p>
                            <p className="mt-3 text-xs text-ink-4">
                              Start date {formatIsoDate(offer.start_date)} · Replies go to{' '}
                              {offer.reply_to || 'the sending mailbox'}
                              {offer.copy_to_sender ? ' · Bcc to the sender' : ''}
                            </p>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
              {!loading && offers.length === 0 && (
                <tr>
                  <td colSpan={6} className="py-12 text-center text-ink-4">
                    No offers yet. Offers you send appear here.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {showPagePreview && preview?.page && (
        <div className="fixed inset-0 z-[70] overflow-y-auto" role="dialog" aria-modal="true" aria-label="Offer page preview">
          <OfferExperience offer={preview.page} preview onClosePreview={() => setShowPagePreview(false)} />
        </div>
      )}
    </div>
  );
};

export default Recruitment;
