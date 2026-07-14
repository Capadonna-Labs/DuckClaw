/** Envuelve diagramas Mermaid sueltos (sin ```mermaid) para que el renderer los detecte. */

const MERMAID_DIAGRAM_START =
  /^(?:flowchart\s+(?:TB|BT|RL|LR|TD)|graph\s+(?:TB|BT|RL|LR|TD)|sequenceDiagram|classDiagram|stateDiagram(?:-v2)?|erDiagram|gantt|pie|gitGraph|C4Context|mindmap|timeline)\b/;

const FENCE_LINE = /^(`{3,}|~{3,})(\w*)?\s*$/;

function isMermaidContinuation(line: string): boolean {
  const t = line.trim();
  if (!t) return true;
  if (MERMAID_DIAGRAM_START.test(t)) return true;
  if (/^(subgraph|end|classDef|style|linkStyle|click)\b/.test(t)) return true;
  if (/^[A-Za-z0-9_"'[\]().\s-]+(-->|---|<-->|-\.-|==>|===)/.test(t)) return true;
  if (/^[\s|:-]+/.test(line) && /[|{}[\]()]/.test(t)) return true;
  return false;
}

export function preprocessBareMermaidBlocks(text: string): string {
  const lines = (text || '').split('\n');
  const out: string[] = [];
  let i = 0;
  let fenceMarker: string | null = null;

  while (i < lines.length) {
    const line = lines[i];
    const fence = line.match(FENCE_LINE);
    if (fence) {
      const marker = fence[1];
      if (fenceMarker === marker) {
        fenceMarker = null;
      } else if (!fenceMarker) {
        fenceMarker = marker;
      }
      out.push(line);
      i += 1;
      continue;
    }

    if (fenceMarker) {
      out.push(line);
      i += 1;
      continue;
    }

    const trimmed = line.trim();
    if (MERMAID_DIAGRAM_START.test(trimmed)) {
      const block: string[] = [line];
      i += 1;
      while (i < lines.length) {
        const next = lines[i];
        if (!next.trim()) {
          if (i + 1 < lines.length && isMermaidContinuation(lines[i + 1])) {
            block.push(next);
            i += 1;
            continue;
          }
          break;
        }
        if (!isMermaidContinuation(next)) break;
        block.push(next);
        i += 1;
      }
      out.push('```mermaid');
      out.push(...block.map((row) => row.trimEnd()));
      out.push('```');
      continue;
    }

    out.push(line);
    i += 1;
  }

  return out.join('\n');
}

export function isMermaidLanguage(className: string | undefined): boolean {
  const lang = (className || '').replace(/^language-/, '').trim().toLowerCase();
  return lang === 'mermaid';
}
