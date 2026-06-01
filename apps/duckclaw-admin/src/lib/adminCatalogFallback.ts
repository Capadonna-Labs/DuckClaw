import { existsSync, readdirSync, readFileSync } from 'fs';
import { join } from 'path';
import { loadOfficialMcpReferenceFromRepo } from '@/lib/mcpOfficialReference';

const MCP_TOOLS = [
  {
    name: 'open_meteo_current_weather',
    description: 'Clima actual por ciudad (Open-Meteo)',
    server: 'duckclaw_mcp',
  },
  {
    name: 'invoke_manager_graph',
    description: 'Fly commands / y grafo Manager (Telegram, workers, team)',
    server: 'duckclaw_mcp',
  },
  {
    name: 'invoke_core_conversation_graph',
    description: 'Grafo core (/status, /balance)',
    server: 'duckclaw_mcp',
  },
  {
    name: 'list_graph_tools',
    description: 'Descubrimiento de capacidades MCP',
    server: 'duckclaw_mcp',
  },
] as const;

export function repoRoot(): string {
  const fromEnv = process.env.DUCKCLAW_REPO_ROOT?.trim();
  if (fromEnv) return fromEnv;
  return join(process.cwd(), '..', '..');
}

function templatesDir(): string {
  return join(
    repoRoot(),
    'packages/agents/src/duckclaw/forge/templates'
  );
}

export function fallbackSkillsCatalog() {
  return {
    global: [],
    template_local: [],
    _fallback: true as const,
    warning: 'El catálogo de skills requiere Gateway DB-first activo.',
  };
}

export function fallbackMcpCatalog() {
  const mcpPort = (process.env.DUCKCLAW_MCP_PORT || '8001').trim();
  const stdio_servers: { id: string; enabled: boolean; note: string }[] = [];
  const cfgPath = join(repoRoot(), 'config/mcp_servers.yaml');
  if (existsSync(cfgPath)) {
    try {
      const raw = readFileSync(cfgPath, 'utf-8');
      const re = /^  (\w+):/gm;
      let m: RegExpExecArray | null;
      while ((m = re.exec(raw)) !== null) {
        const id = m[1];
        if (id === 'mcp_servers') continue;
        stdio_servers.push({
          id,
          enabled: true,
          note: 'stdio vía gateway (config/mcp_servers.yaml)',
        });
      }
    } catch {
      /* ignore */
    }
  }
  return {
    duckclaw_mcp: {
      command: `uv run python -m duckclaw_mcp --host 0.0.0.0 --port ${mcpPort}`,
      url: `http://127.0.0.1:${mcpPort}/mcp`,
      tools: [...MCP_TOOLS],
    },
    stdio_servers,
    official_reference: loadOfficialMcpReferenceFromRepo(),
    github_note: 'GitHub MCP vía forge/skills/github_bridge.py (Docker)',
    _fallback: true as const,
    _gateway_stale: true as const,
  };
}

const CATALOG_STARTER_SKIP = new Set(['entry_router', 'manager_router', 'industries']);

function manifestDisplayFields(templateId: string): { name: string; subtitle: string } {
  const manifest = join(templatesDir(), templateId, 'manifest.yaml');
  let name = templateId;
  let subtitle = `Plantilla forge/templates/${templateId}`;
  if (!existsSync(manifest)) return { name, subtitle };
  try {
    const raw = readFileSync(manifest, 'utf-8');
    const nameMatch = raw.match(/^name:\s*(.+)$/m);
    const descMatch = raw.match(/^(?:description|subtitle):\s*(.+)$/m);
    if (nameMatch) name = nameMatch[1].replace(/^["']|["']$/g, '').trim();
    if (descMatch) subtitle = descMatch[1].replace(/^["']|["']$/g, '').trim();
  } catch {
    /* ignore */
  }
  return { name, subtitle };
}

function catalogStarterItems(): { id: string; name: string; path: string; subtitle: string }[] {
  const root = templatesDir();
  if (!existsSync(root)) return [];
  const starters: { id: string; name: string; path: string; subtitle: string }[] = [];
  for (const tid of readdirSync(root)) {
    if (CATALOG_STARTER_SKIP.has(tid)) continue;
    if (!existsSync(join(root, tid, 'manifest.yaml'))) continue;
    const { name, subtitle } = manifestDisplayFields(tid);
    starters.push({ id: tid, name, path: tid, subtitle });
  }
  starters.sort((a, b) => {
    if (a.id === 'default') return -1;
    if (b.id === 'default') return 1;
    return a.name.localeCompare(b.name);
  });
  return starters;
}

export function fallbackIndustriesCatalog() {
  const industries: { id: string; name: string; path: string }[] = [];
  const indDir = join(templatesDir(), 'industries');
  if (existsSync(indDir)) {
    for (const name of readdirSync(indDir)) {
      if (existsSync(join(indDir, name, 'manifest.yaml'))) {
        industries.push({ id: `industries/${name}`, name, path: `industries/${name}` });
      }
    }
  }
  return { industries, starters: catalogStarterItems(), _fallback: true as const };
}

export function fallbackTopologies() {
  return {
    topologies: [
      {
        id: 'general',
        label: 'General',
        description:
          'Worker autónomo estándar. Un agente, un manifest, skills propias. La mayoría de plantillas usan este modo.',
      },
      {
        id: 'orchestrator',
        label: 'Orquestador',
        description:
          'Coordina sub-workers vía orchestrator.orchestrates en manifest.yaml del coordinador.',
      },
    ],
    _fallback: true as const,
  };
}

export function fallbackSourcePreview(sourceTemplate: string) {
  const rel = sourceTemplate.trim().replace(/^\/+/, '') || 'default';
  const dir = join(templatesDir(), rel);
  if (!existsSync(dir)) {
    return fallbackSourcePreview('default');
  }
  let system_prompt = '';
  let soul = '';
  const sp = join(dir, 'system_prompt.md');
  const sl = join(dir, 'soul.md');
  if (existsSync(sp)) system_prompt = readFileSync(sp, 'utf-8');
  if (existsSync(sl)) soul = readFileSync(sl, 'utf-8');
  return {
    source_template: rel,
    name: rel,
    description: '',
    topology: 'general',
    skills: [] as string[],
    system_prompt,
    soul,
    _fallback: true as const,
  };
}

export function catalogFallbackResponse(
  subpath: string,
  searchParams?: URLSearchParams
): unknown | null {
  if (subpath === 'catalog/skills') return fallbackSkillsCatalog();
  if (subpath === 'catalog/mcp') return fallbackMcpCatalog();
  if (subpath === 'catalog/industries') return fallbackIndustriesCatalog();
  if (subpath === 'catalog/topologies') return fallbackTopologies();
  if (subpath === 'catalog/source-preview' && searchParams) {
    const src = searchParams.get('source_template') || 'default';
    return fallbackSourcePreview(src);
  }
  return null;
}
