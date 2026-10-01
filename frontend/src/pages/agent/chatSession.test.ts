import { setCurrentLang } from '../../i18n/core';
import { buildChatMessage, deriveSessionTitle, formatRelativeTime, toSessionSummary } from './chatSession';

describe('chat session labels', () => {
  const minutesAgo = (minutes: number) => new Date(Date.now() - minutes * 60_000).toISOString();

  beforeEach(() => setCurrentLang('en'));
  afterEach(() => setCurrentLang('zh'));

  it('keeps the English labels', () => {
    expect(deriveSessionTitle([])).toBe('New chat');
    expect(toSessionSummary({ id: 's1' }).title).toBe('New chat');
    expect(formatRelativeTime(minutesAgo(0))).toBe('just now');
    expect(formatRelativeTime(minutesAgo(5))).toBe('5m ago');
    expect(formatRelativeTime(minutesAgo(3 * 60))).toBe('3h ago');
    expect(formatRelativeTime(minutesAgo(2 * 24 * 60))).toBe('2d ago');
  });

  it('labels untitled chats and recent times in Chinese', () => {
    setCurrentLang('zh');
    expect(deriveSessionTitle([])).toBe('新对话');
    expect(toSessionSummary({ id: 's1' }).title).toBe('新对话');
    expect(formatRelativeTime(minutesAgo(0))).toBe('刚刚');
    expect(formatRelativeTime(minutesAgo(5))).toBe('5 分钟前');
    expect(formatRelativeTime(minutesAgo(3 * 60))).toBe('3 小时前');
    expect(formatRelativeTime(minutesAgo(2 * 24 * 60))).toBe('2 天前');
  });

  it('never translates what the user wrote', () => {
    setCurrentLang('zh');
    const question = buildChatMessage('user', 'Summarise the payment terms');
    expect(deriveSessionTitle([question])).toBe('Summarise the payment terms');
    expect(toSessionSummary({ id: 's2', title: 'Payment terms' }).title).toBe('Payment terms');
  });
});
