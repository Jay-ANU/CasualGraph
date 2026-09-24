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

export const CURRENCIES = ['AUD', 'USD', 'CNY', 'EUR', 'GBP', 'HKD', 'SGD', 'NZD', 'CAD', 'JPY'];

export const OFFER_COPY = {
  en: {
    confidential: 'Confidential offer',
    kicker: 'Offer of employment',
    greeting: (name: string) => `Welcome aboard, ${name}.`,
    intro: (organisation: string) => `${organisation} would love you to join as`,
    accept: 'Accept offer',
    decline: 'Decline',
    replyWithin: 'Reply within',
    replyDatePassed: 'The reply date has passed',
    units: { days: 'days', hours: 'hrs', minutes: 'min', seconds: 'sec' },
    scroll: 'See the details',
    compensation: 'Compensation',
    baseSalary: 'Base salary',
    alsoIncluded: 'Also included',
    role: 'The role',
    startDate: 'Start date',
    replyBy: 'Reply by',
    reportsTo: 'Reports to',
    location: 'Location',
    employment: 'Employment',
    team: 'Team',
    benefits: 'Benefits',
    note: 'A note from the team',
    signature: (sender: string, organisation: string) => `${sender}, ${organisation}`,
    decideTitle: 'Ready to decide?',
    decideBody: 'Your answer goes straight to the team. You can add a message if you like.',
    messageLabel: 'Message to the team (optional)',
    acceptTitle: 'Accept this offer?',
    acceptBody: (position: string) => `You are accepting the position of ${position}.`,
    declineTitle: 'Decline this offer?',
    declineBody: 'We are sorry to hear that. A short note helps the team, but it is optional.',
    confirmAccept: 'Accept offer',
    confirmDecline: 'Decline offer',
    cancel: 'Cancel',
    sending: 'Sending…',
    acceptedTitle: (name: string) => `Welcome to the team, ${name}!`,
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
    loading: ['Verifying your private link', 'Unsealing the offer', 'Rendering the details'],
    privateNote: 'This page is private to you. Please don’t share the link.',
    previewBanner: 'Preview of the candidate’s offer page. Buttons are disabled.',
    closePreview: 'Close preview',
    respondFailed: 'Your answer could not be sent. Please try again.',
  },
  zh: {
    confidential: '机密录用通知',
    kicker: '录用通知',
    greeting: (name: string) => `欢迎加入，${name}。`,
    intro: (organisation: string) => `${organisation} 诚邀您担任`,
    accept: '接受录用',
    decline: '婉拒',
    replyWithin: '回复剩余时间',
    replyDatePassed: '回复截止日期已过',
    units: { days: '天', hours: '时', minutes: '分', seconds: '秒' },
    scroll: '查看详情',
    compensation: '薪酬',
    baseSalary: '基本薪资',
    alsoIncluded: '另含',
    role: '职位信息',
    startDate: '入职日期',
    replyBy: '回复截止',
    reportsTo: '汇报对象',
    location: '工作地点',
    employment: '用工类型',
    team: '团队',
    benefits: '福利',
    note: '来自团队的话',
    signature: (sender: string, organisation: string) => `${sender}，${organisation}`,
    decideTitle: '准备好做决定了吗？',
    decideBody: '您的答复会直接送达团队，也可以附上留言。',
    messageLabel: '给团队的留言（可选）',
    acceptTitle: '确认接受此录用？',
    acceptBody: (position: string) => `您将接受「${position}」职位。`,
    declineTitle: '确认婉拒此录用？',
    declineBody: '很遗憾听到这个消息。简单说明原因会对团队很有帮助（可选）。',
    confirmAccept: '确认接受',
    confirmDecline: '确认婉拒',
    cancel: '取消',
    sending: '正在提交…',
    acceptedTitle: (name: string) => `欢迎加入团队，${name}！`,
    acceptedBody: '团队已收到您的答复，稍后会与您联系后续安排。',
    declinedTitle: '已婉拒此录用',
    declinedBody: '感谢您的告知，祝您一切顺利。',
    acceptedOn: (date: string) => `已于 ${date} 接受`,
    declinedOn: (date: string) => `已于 ${date} 婉拒`,
    withdrawnTitle: '此录用已撤回',
    withdrawnBody: (sender: string) => `如有疑问，请联系 ${sender || '团队'}。`,
    invalidTitle: '此录用链接无效',
    invalidBody: '请打开录用邮件中的完整链接，或联系发件人获取新链接。',
    errorTitle: '无法加载录用详情',
    errorBody: '请检查网络连接后重试。',
    retry: '重试',
    loading: ['正在验证专属链接', '正在解封录用通知', '正在生成详情'],
    privateNote: '此页面仅供您本人查看，请勿转发链接。',
    previewBanner: '候选人录用页面预览，按钮已停用。',
    closePreview: '关闭预览',
    respondFailed: '答复提交失败，请重试。',
  },
};

export type OfferCopy = (typeof OFFER_COPY)['en'];

export const copyFor = (language?: string): OfferCopy =>
  (language === 'zh' ? OFFER_COPY.zh : OFFER_COPY.en) as OfferCopy;

const CJK = /[㐀-鿿豈-﫿]/;

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

export const formatTimestamp = (value: string | null | undefined, language: OfferLanguage) => {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleDateString(localeFor(language), { day: 'numeric', month: 'long', year: 'numeric' });
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

/** Time left until the end of the reply day, in the candidate's own time zone. */
export const countdownTo = (respondBy: string | undefined, now: Date): CountdownParts | null => {
  const day = parseIsoDate(respondBy);
  if (!day) return null;
  const deadline = new Date(day.getFullYear(), day.getMonth(), day.getDate(), 23, 59, 59);
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

export const easeOutExpo = (t: number) => (t >= 1 ? 1 : 1 - Math.pow(2, -10 * t));
