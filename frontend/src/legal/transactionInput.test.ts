import { describe, it, expect } from 'vitest';
import { emptyTransactionInputs, transactionAmount } from './transactionInput';

describe('transaction amount and reset', () => {
  it('does not round cents or invent an amount for unknown', () => {
    expect(transactionAmount('999999999999.99')).toEqual({ valid: true, value: '999999999999.99' });
    expect(transactionAmount('')).toEqual({ valid: true, value: null });
    expect(transactionAmount('0')).toEqual({ valid: true, value: '0' });
    expect(transactionAmount('1000000000000')).toEqual({ valid: true, value: '1000000000000' });
  });
  it.each(['-1', 'NaN', 'Infinity', '1e4', '三万元', '1.001', '1000000000000.01'])('rejects invalid amount %s', value => {
    expect(transactionAmount(value).valid).toBe(false);
  });
  it('new contract has independent unknown context', () => {
    const first = emptyTransactionInputs(); first.dealValue = '100';
    expect(emptyTransactionInputs().dealValue).toBe('');
    expect(emptyTransactionInputs().performanceStage).toBe('未知');
  });
});
