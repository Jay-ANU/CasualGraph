import { setCurrentLang } from '../../i18n/core';
import { formatAccountPlanLabel } from './accountPlan';

describe('account plan labels', () => {
  beforeEach(() => setCurrentLang('en'));
  afterEach(() => setCurrentLang('zh'));

  it('shows Max for admins, Pro for whitelisted users, and Free for regular users', () => {
    expect(formatAccountPlanLabel({ role: 'admin' })).toBe('Max');
    expect(formatAccountPlanLabel({ role: 'user', plan: 'pro' })).toBe('Pro');
    expect(formatAccountPlanLabel({ role: 'user' })).toBe('Free');
  });

  it('names the plans in Chinese', () => {
    setCurrentLang('zh');
    expect(formatAccountPlanLabel({ role: 'admin' })).toBe('Max 会员');
    expect(formatAccountPlanLabel({ role: 'user', plan_label: 'Pro' })).toBe('Pro 会员');
    expect(formatAccountPlanLabel(null)).toBe('免费版');
  });
});
