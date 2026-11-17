import { describe, expect, it } from 'vitest';
import { openMentionQuery, resolveMentionedWorker } from './workerOptions';

const workers = [{ id: 'finanz_bot', label: 'Finanz' }, { id: 'quant_trader', label: 'Quant Trader' }];

describe('@mentions', () => {
  it('routes an exact @ anywhere by id or label, case and spaces aside', () => {
    expect(resolveMentionedWorker(workers, '@Finanz cuánto gasté')).toBe('finanz_bot');
    expect(resolveMentionedWorker(workers, '@quanttrader hola')).toBe('quant_trader');
    expect(resolveMentionedWorker(workers, 'hola @Finanz, revisa esto')).toBe('finanz_bot');
    expect(resolveMentionedWorker(workers, 'hola @Finanz revisa esto')).toBe('finanz_bot');
    expect(resolveMentionedWorker(workers, 'escribe a juan@finanz.com')).toBe('');
    expect(resolveMentionedWorker(workers, '@Fin hola')).toBe('');
    expect(resolveMentionedWorker(workers, '@nadie hola')).toBe('');
  });
  it('finds the open @query at the caret', () => {
    expect(openMentionQuery('@fi', 3)).toBe('fi');
    expect(openMentionQuery('hola @', 6)).toBe('');
    expect(openMentionQuery('mail@x', 6)).toBeNull();
    expect(openMentionQuery('@fin hola', 9)).toBeNull();
  });
});
