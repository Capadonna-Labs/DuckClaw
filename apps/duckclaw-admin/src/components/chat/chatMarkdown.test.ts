import { describe, expect, it } from 'vitest';
import { fixTableDelimiterRows, looksLikeMarkdown } from './chatMarkdownDetection';

describe('looksLikeMarkdown', () => {
  it('detecta encabezados y listas', () => {
    const sample = `### Claude Fable 5 (Anthropic)

- Fable 5 supera a todos los Claude anteriores
- Precio: 10 USD por millón`;
    expect(looksLikeMarkdown(sample)).toBe(true);
  });

  it('no formatea texto plano corto', () => {
    expect(looksLikeMarkdown('hola, revisa el pedido')).toBe(false);
    expect(looksLikeMarkdown('precio: 10 USD')).toBe(false);
  });

  it('detecta bloques de código y enlaces', () => {
    expect(looksLikeMarkdown('```python\nx=1\n```')).toBe(true);
    expect(looksLikeMarkdown('ver [docs](https://example.com)')).toBe(true);
  });
});

describe('ChatMarkdown code blocks', () => {
  it('el code dentro de pre hereda el color del bloque (un fence sin lenguaje llega como código en línea)', async () => {
    const { readFileSync } = await import('node:fs');
    const src = readFileSync(new URL('./ChatMarkdown.tsx', import.meta.url), 'utf8');
    const pre = src.split('const pre = isUser')[1].split('const inlineCode')[0];
    expect(pre.match(/\[&_code\]:!text-inherit/g)).toHaveLength(2); // usuario y asistente
    expect(pre.match(/\[&_code\]:!bg-transparent/g)).toHaveLength(2);
  });
});
describe('fixTableDelimiterRows', () => {
  it('resizes a delimiter row with one column too many (MSFT reply, 16-nov)', () => {
    const t = '| A | B | C |\n|---|---:|---:|---:|\n| 1 | 2 | 3 |';
    expect(fixTableDelimiterRows(t).split('\n')[1]).toBe('|---|---:|---:|');
  });
  it('pads a short one and leaves good tables alone', () => {
    expect(fixTableDelimiterRows('| A | B |\n|---|').split('\n')[1]).toBe('|---|---|');
    const ok = '| A | B |\n|---|---|';
    expect(fixTableDelimiterRows(ok)).toBe(ok);
  });
});
