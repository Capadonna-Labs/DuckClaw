/** Helpers to edit common manifest fields without hand-writing YAML. */

export type ToolProfile = 'general' | 'minimal' | 'rag_only';

export type ManifestQuickState = {
  toolProfile: ToolProfile;
  browserSandbox: boolean;
  webSearch: boolean;
  baselineOff: boolean;
  /** Pasos con herramientas por turno (manifest `agent_node.max_tool_rounds`). */
  maxToolRounds: number;
};

export const DEFAULT_MAX_TOOL_ROUNDS = 10;
export const MAX_TOOL_ROUNDS_CEILING = 50;

const DEFAULT_STATE: ManifestQuickState = {
  toolProfile: 'general',
  browserSandbox: false,
  webSearch: false,
  baselineOff: false,
  maxToolRounds: DEFAULT_MAX_TOOL_ROUNDS,
};

function readScalar(yaml: string, key: string): string | null {
  const match = yaml.match(new RegExp(`^${key}:\\s*(.+?)\\s*$`, 'm'));
  if (!match) return null;
  return match[1].trim().replace(/^['"]|['"]$/g, '');
}

function readBool(yaml: string, key: string): boolean {
  const raw = readScalar(yaml, key);
  if (!raw) return false;
  return ['true', 'yes', '1', 'on'].includes(raw.toLowerCase());
}

function readAgentNodeMaxToolRounds(yaml: string): number {
  const normalized = yaml.replace(/\r\n/g, '\n');
  const blockMatch = normalized.match(/^agent_node:\s*\n((?:[ \t]+.+(?:\n|$))*)/m);
  if (!blockMatch) return DEFAULT_MAX_TOOL_ROUNDS;
  const inner = blockMatch[1];
  const mtr = inner.match(/^[ \t]+max_tool_rounds:\s*(\d+)[ \t]*$/m);
  if (!mtr) return DEFAULT_MAX_TOOL_ROUNDS;
  const n = Number.parseInt(mtr[1], 10);
  if (!Number.isFinite(n) || n < 1) return DEFAULT_MAX_TOOL_ROUNDS;
  return Math.min(MAX_TOOL_ROUNDS_CEILING, n);
}

export function parseManifestQuick(yaml: string): ManifestQuickState {
  const profile = (readScalar(yaml, 'tool_profile') || 'general').toLowerCase();
  const toolProfile: ToolProfile =
    profile === 'minimal' || profile === 'rag_only' ? profile : 'general';
  const webSearch = /^\s*-\s*research\s*:/m.test(yaml) || /^\s*-\s*research\s*$/m.test(yaml);
  return {
    toolProfile,
    browserSandbox: readBool(yaml, 'browser_sandbox'),
    webSearch,
    baselineOff: readScalar(yaml, 'baseline') === 'false',
    maxToolRounds: readAgentNodeMaxToolRounds(yaml),
  };
}

function upsertScalar(yaml: string, key: string, value: string): string {
  const line = `${key}: ${value}`;
  const pattern = new RegExp(`^${key}:\\s*.+$`, 'm');
  if (pattern.test(yaml)) {
    return yaml.replace(pattern, line);
  }
  const trimmed = yaml.trimEnd();
  return `${trimmed}\n${line}\n`;
}

function upsertBool(yaml: string, key: string, enabled: boolean): string {
  if (!enabled) {
    return yaml
      .replace(new RegExp(`^${key}:\\s*.+\\n?`, 'm'), '')
      .replace(new RegExp(`^baseline:\\s*false\\n?`, 'm'), '');
  }
  return upsertScalar(yaml, key, 'true');
}

function upsertResearchSkill(yaml: string, enabled: boolean): string {
  const block = `- research:
      tavily_enabled: true
      search_depth: basic`;
  const hasResearch = /^\s*-\s*research\b/m.test(yaml);
  if (enabled && !hasResearch) {
    if (/^skills:\s*\[\s*\]/m.test(yaml)) {
      return yaml.replace(/^skills:\s*\[\s*\]/m, `skills:\n  ${block.split('\n').join('\n  ')}`);
    }
    if (/^skills:\s*$/m.test(yaml)) {
      return yaml.replace(/^skills:\s*$/m, `skills:\n  ${block.split('\n').join('\n  ')}`);
    }
    if (/^skills:/m.test(yaml)) {
      return yaml.replace(/^skills:\s*$/m, `skills:\n  ${block.split('\n').join('\n  ')}`);
    }
    return `${yaml.trimEnd()}\nskills:\n  ${block.split('\n').join('\n  ')}\n`;
  }
  if (!enabled && hasResearch) {
    return yaml.replace(/^\s*-\s*research[^\n]*\n(?:\s+.+\n)*/gm, '');
  }
  return yaml;
}

function upsertAgentNodeMaxToolRounds(yaml: string, rounds: number): string {
  const value = Math.max(1, Math.min(MAX_TOOL_ROUNDS_CEILING, Math.floor(rounds)));
  const normalized = yaml.replace(/\r\n/g, '\n');
  const blockRe = /^agent_node:\s*\n((?:[ \t]+.+(?:\n|$))*)/m;
  const hasBlock = blockRe.test(normalized);
  const roundsLine = `  max_tool_rounds: ${value}`;

  if (value === DEFAULT_MAX_TOOL_ROUNDS) {
    if (!hasBlock) return normalized;
    // Do not let \s* eat the trailing newline — that breaks the next parse.
    let out = normalized.replace(/^[ \t]+max_tool_rounds:\s*\d+[ \t]*\n?/m, '');
    const afterRemove = out.match(blockRe);
    if (afterRemove && !/^[ \t]+\S/m.test(afterRemove[1])) {
      out = out.replace(/^agent_node:\s*\n?/m, '');
    }
    return out;
  }

  if (hasBlock) {
    if (/^[ \t]+max_tool_rounds:\s*\d+[ \t]*$/m.test(normalized)) {
      return normalized.replace(/^[ \t]+max_tool_rounds:\s*\d+[ \t]*$/m, roundsLine);
    }
    return normalized.replace(/^agent_node:\s*\n/m, `agent_node:\n${roundsLine}\n`);
  }

  const trimmed = normalized.trimEnd();
  return `${trimmed}\nagent_node:\n${roundsLine}\n`;
}

export function applyManifestQuick(yaml: string, state: ManifestQuickState): string {
  let out = yaml.trimEnd() + '\n';
  out = upsertScalar(out, 'tool_profile', state.toolProfile);
  out = upsertBool(out, 'browser_sandbox', state.browserSandbox);
  if (state.baselineOff) {
    out = upsertScalar(out, 'baseline', 'false');
  } else {
    out = out.replace(/^baseline:\s*.+\n?/m, '');
  }
  out = upsertResearchSkill(out, state.webSearch);
  out = upsertAgentNodeMaxToolRounds(out, state.maxToolRounds);
  return out.replace(/\n{3,}/g, '\n\n');
}

export function defaultManifestQuickState(): ManifestQuickState {
  return { ...DEFAULT_STATE };
}
