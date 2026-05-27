export interface AccountPlanUser {
  role?: string;
  plan?: string;
  plan_label?: string;
}

export const formatAccountPlanLabel = (user?: AccountPlanUser | null): 'Free' | 'Pro' | 'Max' => {
  const role = String(user?.role || '').toLowerCase();
  const plan = String(user?.plan || '').toLowerCase();
  const label = String(user?.plan_label || '').toLowerCase();

  if (role === 'admin' || plan === 'max' || label === 'max') return 'Max';
  if (plan === 'pro' || label === 'pro') return 'Pro';
  return 'Free';
};
