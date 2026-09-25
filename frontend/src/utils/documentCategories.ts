/**
 * Upload categories. The value is stored by the backend as the document's
 * `domain`; "general" keeps the value earlier uploads used by default.
 */
export const DOCUMENT_CATEGORIES = [
  { value: 'contract', label: '合同' },
  { value: 'attachment', label: '附件' },
  { value: 'general', label: '其他' },
] as const;

/** Label for a stored domain; values from before the categories changed are shown as written. */
export const documentCategoryLabel = (domain?: string): string => {
  const value = String(domain || 'general').trim();
  const known = DOCUMENT_CATEGORIES.find((category) => category.value === value);
  return known ? known.label : value.replace(/_/g, ' ');
};
