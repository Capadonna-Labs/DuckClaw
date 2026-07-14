import { describe, expect, it } from 'vitest';
import {
  isMermaidLanguage,
  preprocessBareMermaidBlocks,
} from './chatMarkdownMermaid';

describe('chatMarkdownMermaid', () => {
  it('isMermaidLanguage detects mermaid fence', () => {
    expect(isMermaidLanguage('language-mermaid')).toBe(true);
    expect(isMermaidLanguage('language-python')).toBe(false);
  });

  it('wraps bare flowchart blocks', () => {
    const input = `Intro

flowchart TB
    A --> B
    B --> C

Fin`;
    const out = preprocessBareMermaidBlocks(input);
    expect(out).toContain('```mermaid');
    expect(out).toContain('flowchart TB');
    expect(out).toContain('A --> B');
    expect(out).toContain('Intro');
    expect(out).toContain('Fin');
  });

  it('leaves fenced mermaid unchanged', () => {
    const input = '```mermaid\ngraph LR\n  A --> B\n```';
    expect(preprocessBareMermaidBlocks(input)).toBe(input);
  });
});
