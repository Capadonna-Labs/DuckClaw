import { describe, expect, it } from 'vitest';
import {
  lastUserAssistantExchange,
  shouldFetchChatSuggestions,
  shouldShowSuggestionChips,
  suggestionsExchangeKey,
} from './adminChatPure';
import type { ChatMsg } from './types';

describe('shouldFetchChatSuggestions', () => {
  it('true tras una respuesta normal no abortada', () => {
    expect(shouldFetchChatSuggestions('hola', 'Respuesta del asistente', false)).toBe(true);
  });

  it('false si el turno fue abortado', () => {
    expect(shouldFetchChatSuggestions('hola', 'Respuesta del asistente', true)).toBe(false);
  });

  it('false para comandos slash (/loop, /meditate, etc.)', () => {
    expect(shouldFetchChatSuggestions('/loop on', 'Modo /loop activo', false)).toBe(false);
    expect(shouldFetchChatSuggestions('  /summarize', 'Resumen listo', false)).toBe(false);
  });

  it('true tras ciclos /loop (SYSTEM_EVENT o [Ciclo loop]) con reporte outbound', () => {
    expect(
      shouldFetchChatSuggestions(
        '[SYSTEM_EVENT: Ciclo de auto-mejora modo conversación activa /loop on. Metas…]',
        '## Reporte /loop — contraste metas vs datos',
        false
      )
    ).toBe(true);
    expect(
      shouldFetchChatSuggestions('[Ciclo loop] tick', 'Resumen del ciclo con TP/SL', false)
    ).toBe(true);
  });

  it('false si no hay respuesta del asistente', () => {
    expect(shouldFetchChatSuggestions('hola', '', false)).toBe(false);
    expect(shouldFetchChatSuggestions('hola', '   ', false)).toBe(false);
  });
});

describe('shouldShowSuggestionChips', () => {
  it('true con sugerencias', () => {
    expect(shouldShowSuggestionChips(['a', 'b'], false, '')).toBe(true);
  });

  it('false sin sugerencias', () => {
    expect(shouldShowSuggestionChips([], false, '')).toBe(false);
  });

  it('true aunque loading (el caller limpia chips al iniciar el turno)', () => {
    expect(shouldShowSuggestionChips(['a'], true, '')).toBe(true);
  });

  it('persiste aunque el usuario esté escribiendo', () => {
    expect(shouldShowSuggestionChips(['a'], false, 'algo')).toBe(true);
  });
});

describe('lastUserAssistantExchange', () => {
  it('devuelve el último par user→assistant', () => {
    const messages: ChatMsg[] = [
      { role: 'user', text: 'antes' },
      { role: 'assistant', text: 'vieja' },
      { role: 'user', text: '¿Qué sigue?' },
      { role: 'assistant', text: 'La protección está completa.' },
    ];
    expect(lastUserAssistantExchange(messages)).toEqual({
      userText: '¿Qué sigue?',
      assistantText: 'La protección está completa.',
    });
  });

  it('ignora assistant aún streaming', () => {
    const messages: ChatMsg[] = [
      { role: 'user', text: 'hola' },
      { role: 'assistant', text: 'parcial', streaming: true },
    ];
    expect(lastUserAssistantExchange(messages)).toBeNull();
  });

  it('null si el último user es comando slash', () => {
    const messages: ChatMsg[] = [
      { role: 'user', text: '/loop on' },
      { role: 'assistant', text: 'Modo activo' },
    ];
    expect(lastUserAssistantExchange(messages)).toBeNull();
  });

  it('devuelve el par tras un ciclo /loop SYSTEM_EVENT', () => {
    const messages: ChatMsg[] = [
      { role: 'user', text: '/loop on' },
      { role: 'assistant', text: 'Modo /loop activo' },
      {
        role: 'user',
        text: '[SYSTEM_EVENT: Ciclo de auto-mejora modo conversación activa /loop on. Metas…]',
      },
      { role: 'assistant', text: '## Reporte /loop — CEG mark IBKR' },
    ];
    expect(lastUserAssistantExchange(messages)).toEqual({
      userText:
        '[SYSTEM_EVENT: Ciclo de auto-mejora modo conversación activa /loop on. Metas…]',
      assistantText: '## Reporte /loop — CEG mark IBKR',
    });
  });
});


describe('suggestionsExchangeKey', () => {
  it('cambia cuando cambia el texto del assistant', () => {
    const a = suggestionsExchangeKey('c1', 'hola', 'respuesta A');
    const b = suggestionsExchangeKey('c1', 'hola', 'respuesta B');
    expect(a).not.toBe(b);
  });

  it('es estable para el mismo intercambio', () => {
    const a = suggestionsExchangeKey('c1', 'hola', 'misma');
    const b = suggestionsExchangeKey('c1', 'hola', 'misma');
    expect(a).toBe(b);
  });
});
