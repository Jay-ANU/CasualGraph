import { ROLE_EN, SCENARIO_EN } from './scenarios.en';

/**
 * English for Chinese strings that do not live in a component. Only the small shared part
 * ships with every page; feature areas add their own entries with `registerEnglish` when
 * their code loads (the contract desk registers i18n/legal.en.ts from legal/i18n.ts).
 */
export const BASE_EN: Record<string, string> = {
  ...SCENARIO_EN,
  ...ROLE_EN,
};
