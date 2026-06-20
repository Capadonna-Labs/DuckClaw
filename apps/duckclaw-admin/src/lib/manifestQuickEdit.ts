/** Helpers to edit common manifest fields without hand-writing YAML. */

export type ToolProfile = 'general' | 'minimal' | 'rag_only';

export type ManifestQuickState = {
  toolProfile: ToolProfile;
  browserSandbox: boolean;
  webSearch: boolean;
  baselineOff: boolean;
};

const DEFAULT_STATE: ManifestQuickState = {
  toolProfile: 'general',
  browserSandbox: false,
  webSearch: false,
  baselineOff: false,
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
  return out.replace(/\n{3,}/g, '\n\n');
}

export function defaultManifestQuickState(): ManifestQuickState {
  return { ...DEFAULT_STATE };
}
