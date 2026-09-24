// Data and wording for the candidate's offer page (/offer/:token). The page
// follows the language the admin chose for the offer.

export type OfferLanguage = 'en' | 'zh';
export type PublicOfferStatus = 'open' | 'accepted' | 'declined' | 'withdrawn';
export type OfferDecision = 'accept' | 'decline';

export interface OfferSalary {
  amount: number;
  currency: string;
  period: string;
  formatted: string;
}

/** What GET /offers/{token} returns; a withdrawn offer carries only the first block. */
export interface PublicOffer {
  organisation: string;
  status: PublicOfferStatus;
  language: OfferLanguage;
  candidate_name: string;
  position: string;
  sender_name: string;
  responded_at?: string | null;
  team?: string;
  location?: string;
  employment_type?: string;
  reports_to?: string;
  salary?: OfferSalary | null;
  extra_compensation?: string;
  benefits?: string[];
  start_date?: string;
  respond_by?: string;
  letter?: string;
  sent_at?: string | null;
}

export const EMPLOYMENT_TYPES: Array<{ value: string; en: string; zh: string }> = [
  { value: 'full_time', en: 'Full-time', zh: '全职' },
  { value: 'part_time', en: 'Part-time', zh: '兼职' },
  { value: 'internship', en: 'Internship', zh: '实习' },
  { value: 'contract', en: 'Contract', zh: '合同制' },
  { value: 'casual', en: 'Casual', zh: '临时' },
];

export const SALARY_PERIODS: Array<{ value: string; en: string; zh: string }> = [
  { value: 'year', en: 'per year', zh: '每年' },
  { value: 'month', en: 'per month', zh: '每月' },
  { value: 'week', en: 'per week', zh: '每周' },
  { value: 'day', en: 'per day', zh: '每天' },
  { value: 'hour', en: 'per hour', zh: '每小时' },
];

// Candidates can be anywhere: the common currencies first, then the rest alphabetically.
// Keep in sync with CURRENCIES in recruitment_offers.py.
export const CURRENCIES = [
  'AUD', 'USD', 'EUR', 'GBP', 'CNY', 'HKD', 'SGD', 'JPY', 'CAD', 'NZD',
  'AED', 'BRL', 'CHF', 'CZK', 'DKK', 'IDR', 'ILS', 'INR', 'KRW', 'MXN',
  'MYR', 'NOK', 'PHP', 'PLN', 'SAR', 'SEK', 'THB', 'TRY', 'TWD', 'VND',
  'ZAR',
];

export const OFFER_COPY = {
  en: {
    confidential: 'Private and confidential',
    kicker: 'Offer of employment',
    issued: (date: string) => `Issued ${date}`,
    greeting: (name: string) => (name ? `${name}, we would like you to join us.` : 'We would like you to join us.'),
    intro: (organisation: string, position: string) =>
      position
        ? `${organisation} is offering you the position of ${position}. Everything is set out below.`
        : `${organisation} is offering you a position. Everything is set out below.`,
    replyRequest: (date: string) => `Please let us know by ${date}.`,
    sentenceGap: ' ',
    card: {
      reference: 'Reference',
      issued: 'Issued',
      start: 'Start',
      replyBy: 'Reply by',
      holder: 'Prepared for',
    },
    accept: 'Accept the offer',
    decline: 'Decline',
    jump: 'Reply to this offer',
    replyTitle: 'Your reply',
    replyBy: (date: string) => `Reply by ${date}`,
    remaining: (days: number, clock: string) => (days > 0 ? `${days} ${days === 1 ? 'day' : 'days'} ${clock} left` : `${clock} left`),
    replyDatePassed: 'The reply date has passed. You can still answer, and the team will see it.',
    compensation: 'Compensation',
    baseSalary: 'Base salary',
    alsoIncluded: 'Also included',
    role: 'The role',
    startDate: 'Start date',
    replyByLabel: 'Reply by',
    reportsTo: 'Reports to',
    location: 'Location',
    employment: 'Employment',
    team: 'Team',
    benefits: 'Benefits',
    note: (sender: string) => (sender ? `A note from ${sender}` : 'A note from the team'),
    decideBody: 'Your answer goes straight to the team. You can add a message if you like.',
    messageLabel: 'Message to the team (optional)',
    acceptTitle: 'Accept this offer?',
    acceptBody: (position: string, organisation: string) =>
      position ? `You are accepting the position of ${position} at ${organisation}.` : `You are accepting the offer from ${organisation}.`,
    declineTitle: 'Decline this offer?',
    declineBody: 'We are sorry to hear that. A short note helps the team, but it is optional.',
    confirmAccept: 'Accept offer',
    confirmDecline: 'Decline offer',
    cancel: 'Cancel',
    sending: 'Sending…',
    stampAccepted: 'Accepted',
    stampDeclined: 'Declined',
    acceptedTitle: (name: string) => (name ? `Welcome to the team, ${name}.` : 'Welcome to the team.'),
    acceptedBody: 'Your acceptance is with the team. They will be in touch about next steps.',
    declinedTitle: 'Offer declined',
    declinedBody: 'Thank you for letting us know. We wish you all the best.',
    acceptedOn: (date: string) => `Accepted on ${date}`,
    declinedOn: (date: string) => `Declined on ${date}`,
    withdrawnTitle: 'This offer has been withdrawn',
    withdrawnBody: (sender: string) => `Please contact ${sender || 'the team'} if you have any questions.`,
    invalidTitle: 'This offer link isn’t valid',
    invalidBody: 'Open the full link from your offer email, or ask the sender for a new one.',
    errorTitle: 'We couldn’t load your offer',
    errorBody: 'Check your connection and try again.',
    retry: 'Try again',
    loading: 'Opening your offer',
    privateNote: 'This page is private to you. Please don’t share the link.',
    previewBanner: 'Preview of the candidate’s offer page. Buttons are disabled.',
    closePreview: 'Close preview',
    respondFailed: 'Your answer could not be sent. Please try again.',
  },
  zh: {
    confidential: '私人机密',
    kicker: '录用通知',
    issued: (date: string) => `签发于${date}`,
    // Zero-width spaces mark where the headline may wrap (the page keeps CJK words together).
    greeting: (name: string) => (name ? `${name}，\u200B我们诚挚\u200B邀请您加入。` : '我们诚挚\u200B邀请您加入。'),
    intro: (organisation: string, position: string) =>
      position ? `${organisation} 诚聘您担任${position}，详情如下。` : `${organisation} 诚聘您加入，详情如下。`,
    replyRequest: (date: string) => `请于${date}前告知我们您的决定。`,
    sentenceGap: '',
    card: {
      reference: '编号',
      issued: '签发',
      start: '入职',
      replyBy: '回复截止',
      holder: '致',
    },
    accept: '接受录用',
    decline: '婉拒',
    jump: '答复此录用',
    replyTitle: '您的答复',
    replyBy: (date: string) => `请于${date}前回复`,
    remaining: (days: number, clock: string) => (days > 0 ? `剩余 ${days} 天 ${clock}` : `剩余 ${clock}`),
    replyDatePassed: '回复截止日期已过。您仍可以答复，团队会看到。',
    compensation: '薪酬',
    baseSalary: '基本薪资',
    alsoIncluded: '另含',
    role: '职位信息',
    startDate: '入职日期',
    replyByLabel: '回复截止',
    reportsTo: '汇报对象',
    location: '工作地点',
    employment: '用工类型',
    team: '团队',
    benefits: '福利',
    note: (sender: string) => (sender ? `来自${sender}的话` : '来自团队的话'),
    decideBody: '您的答复会直接送达团队，也可以附上留言。',
    messageLabel: '给团队的留言（可选）',
    acceptTitle: '确认接受此录用？',
    acceptBody: (position: string, organisation: string) =>
      position ? `您将接受 ${organisation} 的「${position}」职位。` : `您将接受 ${organisation} 的录用。`,
    declineTitle: '确认婉拒此录用？',
    declineBody: '很遗憾听到这个消息。简单说明原因会对团队很有帮助（可选）。',
    confirmAccept: '确认接受',
    confirmDecline: '确认婉拒',
    cancel: '取消',
    sending: '正在提交…',
    stampAccepted: '已接受',
    stampDeclined: '已婉拒',
    acceptedTitle: (name: string) => (name ? `欢迎加入团队，${name}。` : '欢迎加入团队。'),
    acceptedBody: '团队已收到您的答复，稍后会与您联系后续安排。',
    declinedTitle: '已婉拒此录用',
    declinedBody: '感谢您的告知，祝您一切顺利。',
    acceptedOn: (date: string) => `已于${date}接受`,
    declinedOn: (date: string) => `已于${date}婉拒`,
    withdrawnTitle: '此录用已撤回',
    withdrawnBody: (sender: string) => `如有疑问，请联系${sender || '团队'}。`,
    invalidTitle: '此录用链接无效',
    invalidBody: '请打开录用邮件中的完整链接，或联系发件人获取新链接。',
    errorTitle: '无法加载录用详情',
    errorBody: '请检查网络连接后重试。',
    retry: '重试',
    loading: '正在打开录用通知',
    privateNote: '此页面仅供您本人查看，请勿转发链接。',
    previewBanner: '候选人录用页面预览，按钮已停用。',
    closePreview: '关闭预览',
    respondFailed: '答复提交失败，请重试。',
  },
};

export type OfferCopy = (typeof OFFER_COPY)['en'];

export const copyFor = (language?: string): OfferCopy =>
  (language === 'zh' ? OFFER_COPY.zh : OFFER_COPY.en) as OfferCopy;

const CJK = /[㐀-鿿豈-﫿]/;

/** "Ada Lovelace" → "Ada"; Chinese names are used in full. */
export const greetingName = (fullName: string) => {
  const name = String(fullName || '').trim();
  if (!name || CJK.test(name)) return name;
  return name.split(/\s+/)[0];
};

export const employmentLabel = (value: string | undefined, language: OfferLanguage) => {
  const match = EMPLOYMENT_TYPES.find((item) => item.value === value);
  return match ? match[language] : '';
};

export const periodLabel = (value: string | undefined, language: OfferLanguage) => {
  const match = SALARY_PERIODS.find((item) => item.value === value);
  return match ? match[language] : value || '';
};

const localeFor = (language: OfferLanguage) => (language === 'zh' ? 'zh-CN' : 'en-AU');

/** Parses YYYY-MM-DD as a local calendar date. */
export const parseIsoDate = (value?: string | null): Date | null => {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value || ''));
  if (!match) return null;
  return new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
};

export const formatLongDate = (value: string | null | undefined, language: OfferLanguage) => {
  const date = parseIsoDate(value);
  if (!date) return '';
  return date.toLocaleDateString(localeFor(language), {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });
};

/** "9 Oct 2026" / "2026年10月9日": the compact form used on the credential card. */
export const formatShortDate = (value: string | null | undefined, language: OfferLanguage) => {
  const date = parseIsoDate(value);
  if (!date) return '';
  return date.toLocaleDateString(localeFor(language), { day: 'numeric', month: 'short', year: 'numeric' });
};

export const formatTimestamp = (
  value: string | null | undefined,
  language: OfferLanguage,
  style: 'long' | 'short' = 'long'
) => {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleDateString(localeFor(language), {
    day: 'numeric',
    month: style === 'short' ? 'short' : 'long',
    year: 'numeric',
  });
};

/** Groups thousands; shows cents only when asked to, or when the amount has them. */
export const formatAmount = (amount: number, language: OfferLanguage, fractionDigits?: number) => {
  const digits = fractionDigits !== undefined ? fractionDigits : Math.round(amount) === amount ? 0 : 2;
  return new Intl.NumberFormat(localeFor(language), {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  }).format(amount);
};

export interface CountdownParts {
  days: number;
  hours: number;
  minutes: number;
  seconds: number;
  passed: boolean;
}

const endOfReplyDay = (respondBy: string | undefined): Date | null => {
  const day = parseIsoDate(respondBy);
  return day ? new Date(day.getFullYear(), day.getMonth(), day.getDate(), 23, 59, 59) : null;
};

/** Time left until the end of the reply day, in the candidate's own time zone. */
export const countdownTo = (respondBy: string | undefined, now: Date): CountdownParts | null => {
  const deadline = endOfReplyDay(respondBy);
  if (!deadline) return null;
  const remaining = Math.max(0, Math.floor((deadline.getTime() - now.getTime()) / 1000));
  return {
    days: Math.floor(remaining / 86400),
    hours: Math.floor((remaining % 86400) / 3600),
    minutes: Math.floor((remaining % 3600) / 60),
    seconds: remaining % 60,
    passed: remaining === 0,
  };
};

export const twoDigits = (value: number) => (value < 10 ? `0${value}` : String(value));

/** "08:49:35" for the part of the countdown below a day. */
export const clockOf = (parts: CountdownParts) =>
  `${twoDigits(parts.hours)}:${twoDigits(parts.minutes)}:${twoDigits(parts.seconds)}`;

/**
 * Share of the reply window still open, from the moment the offer was sent to the end
 * of the reply day: 1 just after sending, 0 once the date has passed. Null when either
 * end is unknown, in which case the page simply shows the full line.
 */
export const replyWindowLeft = (
  sentAt: string | null | undefined,
  respondBy: string | undefined,
  now: Date
): number | null => {
  const deadline = endOfReplyDay(respondBy);
  if (!deadline) return null;
  const start = sentAt ? new Date(sentAt).getTime() : Number.NaN;
  if (!Number.isFinite(start) || start >= deadline.getTime()) return null;
  const left = (deadline.getTime() - now.getTime()) / (deadline.getTime() - start);
  return Math.min(1, Math.max(0, left));
};

const OFFER_PATH = /^\/offer\/([A-Za-z0-9_-]{16,128})\/?$/;

/** The offer token from a page path such as /offer/abc…, or "" (e.g. in the admin preview). */
export const tokenFromPath = (pathname: string) => {
  const match = OFFER_PATH.exec(pathname || '');
  return match ? match[1] : '';
};

const fnv1a = (text: string, seed = 0x811c9dc5) => {
  let hash = seed >>> 0;
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash >>> 0;
};

// Crockford's base 32: no I, L, O or U, so the reference is easy to read out.
const ALPHABET = '0123456789ABCDEFGHJKMNPQRSTVWXYZ';

/** A short, stable reference such as "7F3A-92K1", derived from the offer's token. */
export const offerReference = (seed: string) => {
  const first = fnv1a(seed);
  const second = fnv1a(`${seed}\u0000${first}`);
  let characters = '';
  for (let index = 0; index < 4; index += 1) characters += ALPHABET[(first >>> (index * 5)) & 31];
  for (let index = 0; index < 4; index += 1) characters += ALPHABET[(second >>> (index * 5)) & 31];
  return `${characters.slice(0, 4)}-${characters.slice(4)}`;
};

/**
 * Bar and gap widths (in units) for the code strip printed on the credential, derived
 * from the same seed as the reference so the two always belong together.
 */
export const referenceBars = (seed: string, count = 30): Array<[number, number]> => {
  const bars: Array<[number, number]> = [];
  let bits = 0;
  for (let index = 0; index < count; index += 1) {
    if (index % 10 === 0) bits = fnv1a(`${seed}/${index}`);
    const chunk = (bits >>> ((index % 10) * 3)) & 7;
    const bar = 1 + (chunk & 1) + ((chunk >>> 1) & 1); // 1, 2, 2 or 3 units
    const gap = 1 + ((chunk >>> 2) & 1); // 1 or 2 units
    bars.push([bar, gap]);
  }
  return bars;
};

/** Something stable to derive the reference from when the page has no token (the admin preview). */
export const referenceSeed = (offer: PublicOffer, pathname: string) =>
  tokenFromPath(pathname) || `draft:${offer.organisation}|${offer.candidate_name}|${offer.position}|${offer.sent_at || ''}`;
