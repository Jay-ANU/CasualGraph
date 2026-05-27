import { formatAccountPlanLabel } from './accountPlan';

describe('account plan labels', () => {
  it('shows Max for admins, Pro for whitelisted users, and Free for regular users', () => {
    expect(formatAccountPlanLabel({ role: 'admin' })).toBe('Max');
    expect(formatAccountPlanLabel({ role: 'user', plan: 'pro' })).toBe('Pro');
    expect(formatAccountPlanLabel({ role: 'user' })).toBe('Free');
  });
});
