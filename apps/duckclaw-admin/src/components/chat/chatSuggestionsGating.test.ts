import { describe, expect, it } from 'vitest';
import { shouldFetchChatSuggestions, shouldShowSuggestionChips } from './adminChatPure';

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

  it('false si no hay respuesta del asistente', () => {
    expect(shouldFetchChatSuggestions('hola', '', false)).toBe(false);
    expect(shouldFetchChatSuggestions('hola', '   ', false)).toBe(false);
  });
});

describe('shouldShowSuggestionChips', () => {
  it('true con sugerencias, sin loading, e input vacío', () => {
    expect(shouldShowSuggestionChips(['a', 'b'], false, '')).toBe(true);
  });

  it('false sin sugerencias', () => {
    expect(shouldShowSuggestionChips([], false, '')).toBe(false);
  });

  it('false mientras carga', () => {
    expect(shouldShowSuggestionChips(['a'], true, '')).toBe(false);
  });

  it('false si el usuario ya está escribiendo', () => {
    expect(shouldShowSuggestionChips(['a'], false, 'algo')).toBe(false);
  });
});
