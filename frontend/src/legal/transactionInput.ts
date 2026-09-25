export function emptyTransactionInputs() {
  return { performanceStage: '未知', attachmentsStatus: '未知', businessPriority: '综合审查', dealValue: '', currency: 'CNY' };
}

/** Preserve decimal text; never silently turn NaN into JSON null or round cents. */
export function transactionAmount(input: string): { valid: boolean; value: string | null } {
  const value = input.trim();
  if (!value) return { valid: true, value: null };
  if (!/^\d{1,13}(?:\.\d{1,2})?$/.test(value)) return { valid: false, value: null };
  const [whole, fraction = ''] = value.split('.');
  const cents = BigInt(whole) * 100n + BigInt(fraction.padEnd(2, '0'));
  return { valid: cents <= 100000000000000n, value };
}
