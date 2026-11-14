import { describe, expect, it } from 'vitest';
import { quotePreview, withQuote } from '@/components/chat/useQuoteMessage';

describe('quote reply', () => {
  it('sends only the start of the quote, on one line, before the message', () => {
    expect(withQuote('línea 1\nlínea 2', 'mi duda')).toBe('> línea 1 línea 2\n\nmi duda');
  });

  it('leaves the message alone without a quote', () => {
    expect(withQuote('  ', 'hola')).toBe('hola');
  });

  it('does not resend a long message: the quote is cut to a short excerpt', () => {
    const out = withQuote('x'.repeat(5000), 'q');
    expect(out.length).toBeLessThan(200);
    expect(out).toContain('…');
    expect(out.endsWith('\n\nq')).toBe(true);
  });

  it('previews on one line without markdown noise', () => {
    expect(quotePreview('## Título\n\n**negrita** y `code`')).toBe('Título negrita y code');
  });
});
