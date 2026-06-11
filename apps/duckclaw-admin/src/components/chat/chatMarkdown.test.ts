import { describe, expect, it } from 'vitest';
import { looksLikeMarkdown } from '@/components/chat/ChatMarkdown';

describe('looksLikeMarkdown', () => {
  it('detecta encabezados y listas', () => {
    const sample = `### Claude Fable 5 (Anthropic)

- Fable 5 supera a todos los Claude anteriores
- Precio: 10 USD por millón`;
    expect(looksLikeMarkdown(sample)).toBe(true);
  });

  it('no formatea texto plano corto', () => {
    expect(looksLikeMarkdown('hola, revisa SPY')).toBe(false);
    expect(looksLikeMarkdown('precio: 10 USD')).toBe(false);
  });

  it('detecta bloques de código y enlaces', () => {
    expect(looksLikeMarkdown('```python\nx=1\n```')).toBe(true);
    expect(looksLikeMarkdown('ver [docs](https://example.com)')).toBe(true);
  });
});
