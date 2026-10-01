import { pick } from '../../i18n/core';

export interface AccountPlanUser {
  role?: string;
  plan?: string;
  plan_label?: string;
}

/** The plan shown under the account name: "Max" in English, "Max 会员" in Chinese. */
export const formatAccountPlanLabel = (user?: AccountPlanUser | null): string => {
  const role = String(user?.role || '').toLowerCase();
  const plan = String(user?.plan || '').toLowerCase();
  const label = String(user?.plan_label || '').toLowerCase();

  if (role === 'admin' || plan === 'max' || label === 'max') return pick('Max 会员', 'Max');
  if (plan === 'pro' || label === 'pro') return pick('Pro 会员', 'Pro');
  return pick('免费版', 'Free');
};
