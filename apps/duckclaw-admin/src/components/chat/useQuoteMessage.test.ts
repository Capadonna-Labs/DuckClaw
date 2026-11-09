import { describe, expect, it } from 'vitest';
import { quotePreview, withQuote } from '@/components/chat/useQuoteMessage';

describe('quote reply', () => {
  it('sends the quote as a markdown blockquote before the message', () => {
    expect(withQuote('línea 1\nlínea 2', 'mi duda')).toBe('> línea 1\n> línea 2\n\nmi duda');
  });

  it('leaves the message alone without a quote', () => {
    expect(withQuote('  ', 'hola')).toBe('hola');
  });

  it('cuts a very long quote', () => {
    const out = withQuote('x'.repeat(5000), 'q');
    expect(out.length).toBeLessThan(1300);
    expect(out).toContain('…');
  });

  it('previews on one line without markdown noise', () => {
    expect(quotePreview('## Título\n\n**negrita** y `code`')).toBe('Título negrita y code');
  });
});
