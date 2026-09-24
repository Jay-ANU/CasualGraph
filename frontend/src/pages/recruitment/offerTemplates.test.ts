import {
  OFFER_PLACEHOLDERS,
  OFFER_TEMPLATES,
  describeMissingPlaceholder,
  formatIsoDate,
  insertAtSelection,
  isTemplateUntouched,
  isValidEmail,
  joinWithAnd,
  loadStoredLetter,
  saveStoredLetter,
} from './offerTemplates';

describe('offer templates', () => {
  it('only use placeholders the backend can fill', () => {
    const known = new Set(OFFER_PLACEHOLDERS.map((item) => item.key));
    Object.values(OFFER_TEMPLATES).forEach((template) => {
      const used = `${template.subject}\n${template.letter}`.match(/\{\{\s*([a-z_]+)\s*\}\}/g) || [];
      expect(used.length).toBeGreaterThan(0);
      used.forEach((token) => expect(known.has(token.replace(/[{}\s]/g, ''))).toBe(true));
    });
  });

  it('describes missing placeholders as actions', () => {
    expect(describeMissingPlaceholder('start_date')).toBe('Add a start date or remove {{start_date}}.');
    expect(describeMissingPlaceholder('sender_name')).toContain('{{sender_name}}');
  });

  it('detects whether the admin edited the template', () => {
    expect(isTemplateUntouched('zh', OFFER_TEMPLATES.zh.subject, OFFER_TEMPLATES.zh.letter)).toBe(true);
    expect(isTemplateUntouched('en', OFFER_TEMPLATES.en.subject, `${OFFER_TEMPLATES.en.letter}!`)).toBe(false);
  });
});

describe('offer form helpers', () => {
  it('validates candidate email addresses like the backend', () => {
    expect(isValidEmail('ada@example.org')).toBe(true);
    expect(isValidEmail('first.last+offers@uni.edu.au')).toBe(true);
    expect(isValidEmail('ada@localhost')).toBe(false);
    expect(isValidEmail('ada@')).toBe(false);
    expect(isValidEmail('ada lovelace@example.org')).toBe(false);
  });

  it('formats calendar dates without shifting the day', () => {
    expect(formatIsoDate('2026-10-01', 'en-AU')).toBe('1 Oct 2026');
    expect(formatIsoDate('')).toBe('—');
    expect(formatIsoDate('soon')).toBe('soon');
  });

  it('inserts a placeholder over the current selection', () => {
    expect(insertAtSelection('Dear ,', '{{candidate_name}}', 5, 5)).toEqual({
      value: 'Dear {{candidate_name}},',
      cursor: 23,
    });
    expect(insertAtSelection('Hello NAME!', 'X', 6, 10)).toEqual({ value: 'Hello X!', cursor: 7 });
  });

  it('joins lists into a sentence', () => {
    expect(joinWithAnd(['a'])).toBe('a');
    expect(joinWithAnd(['a', 'b', 'c'])).toBe('a, b and c');
  });
});

describe('stored letter', () => {
  beforeEach(() => localStorage.clear());

  it('remembers the language and only an edited letter', () => {
    saveStoredLetter('zh', OFFER_TEMPLATES.zh.subject, OFFER_TEMPLATES.zh.letter);
    expect(loadStoredLetter()).toEqual({ language: 'zh', subject: undefined, letter: undefined });

    saveStoredLetter('en', 'Custom subject', 'Custom letter');
    expect(loadStoredLetter()).toEqual({ language: 'en', subject: 'Custom subject', letter: 'Custom letter' });
  });

  it('ignores unreadable stored values', () => {
    localStorage.setItem('causalgraph_recruitment_letter_v1', '{not json');
    expect(loadStoredLetter()).toBeNull();
  });
});
