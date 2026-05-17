import { existsSync, readdirSync, readFileSync } from 'fs';
import { join } from 'path';

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

function forgeDir(): string {
  return join(repoRoot(), 'packages/agents/src/duckclaw/forge');
}

export function fallbackSkillsCatalog() {
  const global: { id: string; path: string; scope: string }[] = [];
  const skillsDir = join(forgeDir(), 'skills');
  if (existsSync(skillsDir)) {
    for (const name of readdirSync(skillsDir)) {
      if (name.endsWith('.py') && !name.startsWith('_')) {
        global.push({
          id: name.replace(/\.py$/, ''),
          path: `packages/agents/src/duckclaw/forge/skills/${name}`,
          scope: 'global',
        });
      }
    }
  }
  const template_local: {
    id: string;
    path: string;
    scope: string;
    worker_id: string;
  }[] = [];
  const root = templatesDir();
  if (existsSync(root)) {
    for (const worker of readdirSync(root)) {
      const local = join(root, worker, 'skills');
      if (!existsSync(local)) continue;
      for (const name of readdirSync(local)) {
        if (name.endsWith('.py') && !name.startsWith('_')) {
          template_local.push({
            id: name.replace(/\.py$/, ''),
            worker_id: worker,
            path: `packages/agents/src/duckclaw/forge/templates/${worker}/skills/${name}`,
            scope: 'template',
          });
        }
      }
    }
  }
  return { global, template_local, _fallback: true as const };
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
    github_note: 'GitHub MCP vía forge/skills/github_bridge.py (Docker)',
    _fallback: true as const,
    _gateway_stale: true as const,
  };
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
  const starters = [
    { id: 'default', name: 'Asistente en blanco', path: 'default' },
    {
      id: 'industries/business_standard',
      name: 'Asistente de negocio',
      path: 'industries/business_standard',
    },
    { id: 'support', name: 'Atención al cliente', path: 'support' },
    { id: 'research_worker', name: 'Investigación y resúmenes', path: 'research_worker' },
    { id: 'finanz', name: 'Finanzas personales', path: 'finanz' },
  ];
  return { industries, starters, _fallback: true as const };
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
        id: 'axis_orchestrator',
        label: 'AXIS orquestador',
        description:
          'Coordina sub-workers (AXIS-Coder, AXIS-Mirror, etc.) vía orchestrator.orchestrates en manifest.yaml. Ejemplo: AXIS-Maestro.',
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
