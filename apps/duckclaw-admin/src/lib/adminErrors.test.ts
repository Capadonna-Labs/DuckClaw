import { describe, expect, it } from 'vitest';
import {
  friendlyGatewayError,
  isConversationNotFoundError,
  isGatewayUnreachableMessage,
} from './adminErrors';

describe('adminErrors timeout vs stack-down', () => {
  it('does not treat BFF 30s timeout as PM2 stack down', () => {
    const msg = 'Gateway no respondió en 30s';
    expect(isGatewayUnreachableMessage(msg)).toBe(false);
    expect(friendlyGatewayError(msg)).not.toMatch(/Iniciar stack/);
  });

  it('detects conversation 404 without treating gateway timeouts as missing', () => {
    expect(isConversationNotFoundError(new Error('Conversación no encontrada'))).toBe(true);
    expect(isConversationNotFoundError(new Error('El gateway tardó demasiado. Recarga el historial; el stack ya está en marcha.'))).toBe(false);
  });
});
