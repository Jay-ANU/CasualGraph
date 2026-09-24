export type OfferLanguage = 'en' | 'zh';
export type OfferStatus = 'sending' | 'sent' | 'failed' | 'accepted' | 'declined' | 'withdrawn';

export interface OfferTemplate {
  subject: string;
  letter: string;
}

// Placeholders are filled in by the backend for each candidate; keep the keys
// in sync with PLACEHOLDER_LABELS in recruitment_offers.py.
export const OFFER_PLACEHOLDERS: Array<{ key: string; label: string }> = [
  { key: 'candidate_name', label: 'Candidate name' },
  { key: 'position', label: 'Position' },
  { key: 'team', label: 'Team' },
  { key: 'location', label: 'Location' },
  { key: 'salary', label: 'Salary' },
  { key: 'start_date', label: 'Start date' },
  { key: 'respond_by', label: 'Reply date' },
  { key: 'sender_name', label: 'Your name' },
];

export const OFFER_TEMPLATES: Record<OfferLanguage, OfferTemplate> = {
  en: {
    subject: 'Offer: {{position}} at CausalGraph AI',
    letter: [
      'Dear {{candidate_name}},',
      '',
      'On behalf of the CausalGraph AI team, I am delighted to offer you the position of {{position}}.',
      '',
      'We enjoyed getting to know you during the selection process and believe your skills will make a real contribution to our work on evidence-based ESG research.',
      '',
      'Your personal offer page sets out the full details, including your compensation and benefits. Your start date would be {{start_date}}. Please review the offer and let us know your decision by {{respond_by}} using the buttons on that page. If you have any questions in the meantime, just reply to this email.',
      '',
      'We look forward to working with you.',
      '',
      'Kind regards,',
      '{{sender_name}}',
      'CausalGraph AI',
    ].join('\n'),
  },
  zh: {
    subject: 'CausalGraph AI 录用通知：{{position}}',
    letter: [
      '{{candidate_name}}，您好：',
      '',
      '我谨代表 CausalGraph AI 团队，很高兴地通知您：您已被录用为{{position}}。',
      '',
      '在招募过程中，我们对您的能力与经历印象深刻，相信您将为我们基于证据的 ESG 研究工作带来重要贡献。',
      '',
      '您的专属录用页面列出了完整的录用详情，包括薪酬与福利。您的入职日期为{{start_date}}。请于{{respond_by}}前在该页面上确认是否接受此录用。如有任何疑问，欢迎直接回复本邮件。',
      '',
      '期待与您共事！',
      '',
      '此致',
      '敬礼！',
      '',
      '{{sender_name}}',
      'CausalGraph AI',
    ].join('\n'),
  },
};

export const OFFER_STATUS_LABELS: Record<OfferStatus, string> = {
  sending: 'Sending…',
  sent: 'Awaiting reply',
  accepted: 'Accepted',
  declined: 'Declined',
  withdrawn: 'Withdrawn',
  failed: 'Not delivered',
};

export const OFFER_STATUS_DOT: Record<OfferStatus, string> = {
  sending: 'bg-info',
  sent: 'bg-info',
  accepted: 'bg-ok',
  declined: 'bg-ink-5',
  withdrawn: 'bg-line-strong',
  failed: 'bg-err',
};

// Statuses an admin can pick once the offer has reached the candidate.
export const MANUAL_OFFER_STATUSES: OfferStatus[] = ['sent', 'accepted', 'declined', 'withdrawn'];

const MISSING_HINTS: Record<string, string> = {
  candidate_name: "Add the candidate's name",
  position: 'Add the position',
  team: 'Add the team',
  location: 'Add a location',
  salary: 'Add a salary',
  start_date: 'Add a start date',
  respond_by: 'Add a reply date',
};

export const placeholderToken = (key: string) => `{{${key}}}`;

export const describeMissingPlaceholder = (key: string) =>
  MISSING_HINTS[key]
    ? `${MISSING_HINTS[key]} or remove ${placeholderToken(key)}.`
    : `Nothing to fill in for ${placeholderToken(key)} yet. Remove it or fill in the matching field.`;

export const isTemplateUntouched = (language: OfferLanguage, subject: string, letter: string) =>
  subject === OFFER_TEMPLATES[language].subject && letter === OFFER_TEMPLATES[language].letter;

// Same rule as the backend: the browser's email check, with a dot in the domain.
const EMAIL_PATTERN =
  /^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$/;

export const isValidEmail = (value: string) => value.length <= 254 && EMAIL_PATTERN.test(value);

/** Formats a YYYY-MM-DD date as a local calendar date (no time-zone shift). */
export const formatIsoDate = (value?: string | null, locale?: string) => {
  if (!value) return '—';
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return value;
  const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  return date.toLocaleDateString(locale, { day: 'numeric', month: 'short', year: 'numeric' });
};

export const insertAtSelection = (text: string, insertion: string, start: number, end: number) => {
  const from = Math.max(0, Math.min(start, text.length));
  const to = Math.max(from, Math.min(end, text.length));
  return { value: text.slice(0, from) + insertion + text.slice(to), cursor: from + insertion.length };
};

export const joinWithAnd = (items: string[]) => {
  if (items.length <= 1) return items.join('');
  return `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`;
};

const LETTER_STORAGE_KEY = 'causalgraph_recruitment_letter_v1';

export interface StoredLetter {
  language: OfferLanguage;
  subject?: string;
  letter?: string;
}

/** The admin's email language and, if they edited it, their own subject and letter. */
export const loadStoredLetter = (): StoredLetter | null => {
  try {
    const raw = localStorage.getItem(LETTER_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    const language: OfferLanguage = parsed?.language === 'zh' ? 'zh' : 'en';
    return {
      language,
      subject: typeof parsed?.subject === 'string' ? parsed.subject : undefined,
      letter: typeof parsed?.letter === 'string' ? parsed.letter : undefined,
    };
  } catch {
    return null;
  }
};

export const saveStoredLetter = (language: OfferLanguage, subject: string, letter: string) => {
  try {
    const value: StoredLetter = isTemplateUntouched(language, subject, letter)
      ? { language }
      : { language, subject, letter };
    localStorage.setItem(LETTER_STORAGE_KEY, JSON.stringify(value));
  } catch {
    // Storage can be unavailable (private mode); the draft simply isn't remembered.
  }
};

const PAY_DEFAULTS_KEY = 'causalgraph_recruitment_pay_defaults_v1';

export interface PayDefaults {
  currency: string;
  period: string;
}

/** The currency and pay period the admin used last, so a team outside Australia sets them once. */
export const loadPayDefaults = (currencies: string[], periods: string[]): PayDefaults => {
  const fallback = { currency: 'AUD', period: 'year' };
  try {
    const parsed = JSON.parse(localStorage.getItem(PAY_DEFAULTS_KEY) || 'null');
    return {
      currency: currencies.indexOf(parsed?.currency) >= 0 ? parsed.currency : fallback.currency,
      period: periods.indexOf(parsed?.period) >= 0 ? parsed.period : fallback.period,
    };
  } catch {
    return fallback;
  }
};

export const savePayDefaults = (value: PayDefaults) => {
  try {
    localStorage.setItem(PAY_DEFAULTS_KEY, JSON.stringify(value));
  } catch {
    // Storage can be unavailable (private mode); the defaults simply aren't remembered.
  }
};
