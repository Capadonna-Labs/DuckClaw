import { describe, expect, it } from 'vitest';

import { isUnauthorizedDetail, isUnauthorizedStatus } from './sessionExpired';

describe('sessionExpired', () => {
  it('detects 401 status', () => {
    expect(isUnauthorizedStatus(401)).toBe(true);
    expect(isUnauthorizedStatus(403)).toBe(false);
    expect(isUnauthorizedStatus(200)).toBe(false);
  });

  it('detects Spanish gateway detail', () => {
    expect(isUnauthorizedDetail('No autenticado')).toBe(true);
    expect(isUnauthorizedDetail('no autenticado')).toBe(true);
    expect(isUnauthorizedDetail('Error: No autenticado')).toBe(true);
    expect(isUnauthorizedDetail('CSRF token inválido')).toBe(false);
  });
});
