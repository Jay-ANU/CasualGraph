import { pick } from '../i18n/core';

/**
 * Upload categories. The value is stored by the backend as the document's
 * `domain`; "general" keeps the value earlier uploads used by default.
 */
export const DOCUMENT_CATEGORIES = [
  { value: 'contract', label: '合同', labelEn: 'Contract' },
  { value: 'attachment', label: '附件', labelEn: 'Attachment' },
  { value: 'general', label: '其他', labelEn: 'Other' },
] as const;

/** Label for a stored domain; values from before the categories changed are shown as written. */
export const documentCategoryLabel = (domain?: string): string => {
  const value = String(domain || 'general').trim();
  const known = DOCUMENT_CATEGORIES.find((category) => category.value === value);
  return known ? pick(known.label, known.labelEn) : value.replace(/_/g, ' ');
};
