import { NextRequest, NextResponse } from 'next/server';
import { catalogFallbackResponse } from '@/lib/adminCatalogFallback';
import { adminApiKey, gatewayBase, gatewayProxyHeaders } from '@/lib/gatewayProxy';
import { requireAdminRouteAuth } from '@/lib/adminRouteAuth';

const OPS_COMMANDS_FALLBACK = {
  commands: [
    { id: 'pm2_list', label: 'PM2 — listar procesos', argv: ['pm2', 'list'] },
    { id: 'pm2_status', label: 'PM2 — estado', argv: ['pm2', 'status'] },
    {
      id: 'pm2_restart_gateway',
      label: 'Reiniciar DuckClaw-Gateway',
      argv: ['pm2', 'restart', 'DuckClaw-Gateway', '--update-env'],
    },
    {
      id: 'pm2_restart_db_writer',
      label: 'Reiniciar DuckClaw-DB-Writer',
      argv: ['pm2', 'restart', 'DuckClaw-DB-Writer', '--update-env'],
    },
    {
      id: 'start_stack',
      label: 'Iniciar plataforma',
      argv: ['__start_stack__'],
    },
    {
      id: 'start_telegram_ingress',
      label: 'Solo Tailscale + webhooks Telegram',
      argv: ['__start_telegram_ingress__'],
    },
    {
      id: 'pm2_start_db_writer',
      label: 'Iniciar DuckClaw-DB-Writer',
      argv: ['pm2', 'start', 'config/ecosystem.db-writer.config.cjs', '--update-env'],
    },
    {
      id: 'pm2_start_gateway',
      label: 'Iniciar DuckClaw-Gateway',
      argv: ['pm2', 'start', 'config/ecosystem.api.config.cjs', '--only', 'DuckClaw-Gateway', '--update-env'],
    },
    {
      id: 'pm2_logs_gateway',
      label: 'Últimas líneas log Gateway',
      argv: ['pm2', 'logs', 'DuckClaw-Gateway', '--lines', '40', '--nostream'],
    },
    {
      id: 'pm2_start_mcp',
      label: 'Iniciar DuckClaw-MCP',
      argv: ['pm2', 'start', 'config/ecosystem.mcp.config.cjs'],
    },
    {
      id: 'pm2_restart_mcp',
      label: 'Reiniciar DuckClaw-MCP',
      argv: ['pm2', 'restart', 'DuckClaw-MCP', '--update-env'],
    },
    {
      id: 'pm2_logs_mcp',
      label: 'Últimas líneas log MCP',
      argv: ['pm2', 'logs', 'DuckClaw-MCP', '--lines', '40', '--nostream'],
    },
    {
      id: 'pm2_start_comfyui',
      label: 'Iniciar ComfyUI',
      argv: ['pm2', 'start', 'config/ecosystem.comfyui.config.cjs', '--update-env'],
    },
    {
      id: 'pm2_restart_comfyui',
      label: 'Reiniciar ComfyUI',
      argv: ['pm2', 'restart', 'ComfyUI', '--update-env'],
    },
    {
      id: 'pm2_logs_comfyui',
      label: 'Últimas líneas log ComfyUI',
      argv: ['pm2', 'logs', 'ComfyUI', '--lines', '40', '--nostream'],
    },
    { id: 'doctor', label: 'Diagnóstico local (doctor.py)', argv: ['uv', 'run', 'python', 'scripts/doctor.py'] },
    {
      id: 'bootstrap_dbs',
      label: 'Bootstrap DuckDB',
      argv: ['uv', 'run', 'python', 'scripts/bootstrap_dbs.py'],
    },
  ],
  _fallback: true,
  _gateway_stale: true,
};

const WRITE_METHODS = new Set(['PUT', 'PATCH', 'POST', 'DELETE']);
const LOCAL_OPS_ALLOWLIST: Record<string, string[]> = {
  pm2_restart_db_writer: ['pm2', 'restart', 'DuckClaw-DB-Writer', '--update-env'],
  pm2_restart_gateway: ['pm2', 'restart', 'DuckClaw-Gateway', '--update-env'],
  pm2_start_gateway: ['pm2', 'start', 'config/ecosystem.api.config.cjs', '--only', 'DuckClaw-Gateway', '--update-env'],
};

function userWriteAllowed(sub: string, method: string): boolean {
  if (method === 'POST' && sub === 'projects') return true;
  if (sub.startsWith('playground/')) return true;
  if (sub.startsWith('conversations')) return true;
  return false;
}

function isWorkspaceProjectDetailPath(segments: string[]): boolean {
  return segments.length === 3 && segments[0] === 'workspace' && segments[1] === 'projects' && Boolean(segments[2]);
}

async function projectDetailFallbackFromList(
  base: string,
  headers: Record<string, string>,
  projectId: string
): Promise<Record<string, unknown> | null> {
  const listRes = await fetch(`${base}/api/v1/admin/workspace/projects?status=all&limit=200`, {
    method: 'GET',
    headers,
    cache: 'no-store',
  });
  if (!listRes.ok) return null;

  const listJson = await listRes.json();
  const projects = Array.isArray(listJson?.projects) ? listJson.projects : [];
  const project = projects.find((item: { project_id?: string }) => item.project_id === projectId);
  if (!project) return null;

  const agentsRes = await fetch(`${base}/api/v1/admin/workspace/projects/${encodeURIComponent(projectId)}/agents`, {
    method: 'GET',
    headers,
    cache: 'no-store',
  });
  const agentsJson = agentsRes.ok ? await agentsRes.json() : {};
  const agents = Array.isArray(agentsJson?.agents) ? agentsJson.agents : project.agents ?? [];

  return {
    project: { ...project, agents },
    agents,
    _fallback: true,
    _gateway_stale: true,
  };
}

async function localOpsRunFallback(sub: string, method: string, bodyText: string): Promise<NextResponse | null> {
  if (sub !== 'ops/run' || method !== 'POST') return null;
  let opId = '';
  try {
    const parsed = JSON.parse(bodyText || '{}') as { op_id?: string };
    opId = String(parsed.op_id || '').trim();
  } catch {
    return NextResponse.json({ detail: 'Payload ops/run inválido' }, { status: 400 });
  }
  const argv = LOCAL_OPS_ALLOWLIST[opId];
  if (!argv) {
    return NextResponse.json({ detail: 'Comando local no permitido', op_id: opId }, { status: 403 });
  }

  const { execFile } = await import('node:child_process');
  const cwd = process.env.DUCKCLAW_REPO_ROOT?.trim() || process.cwd();
  return new Promise((resolve) => {
    execFile(
      argv[0],
      argv.slice(1),
      { cwd, timeout: 30_000, maxBuffer: 1024 * 1024 },
      (error, stdout, stderr) => {
        const exitCode =
          typeof (error as NodeJS.ErrnoException | null)?.code === 'number'
            ? Number((error as NodeJS.ErrnoException).code)
            : error
              ? 1
              : 0;
        resolve(
          NextResponse.json({
            ok: exitCode === 0,
            op_id: opId,
            exit_code: exitCode,
            stdout: String(stdout || ''),
            stderr: String(stderr || ''),
            executed_via: 'bff-local',
            _gateway_stale: true,
          })
        );
      }
    );
  });
}

async function proxy(req: NextRequest, segments: string[]) {
  const base = gatewayBase();
  const key = adminApiKey();
  if (!base) {
    return NextResponse.json({ detail: 'DUCKCLAW_GATEWAY_URL no configurada' }, { status: 503 });
  }
  if (!key) {
    return NextResponse.json({ detail: 'DUCKCLAW_ADMIN_API_KEY no configurada' }, { status: 503 });
  }

  const sub = segments.join('/');
  const isHealth = sub === 'health';

  const auth = await requireAdminRouteAuth(req);
  if (!auth.ok && !isHealth) {
    return auth.response;
  }

  const role = auth.ok ? auth.role : 'admin';
  if (segments[0] === 'audit' && role !== 'admin') {
    return NextResponse.json({ detail: 'Auditoría solo para rol admin' }, { status: 403 });
  }
  if (segments[0] === 'ops' && role !== 'admin') {
    return NextResponse.json({ detail: 'Operaciones solo para rol admin' }, { status: 403 });
  }
  if (role === 'user' && WRITE_METHODS.has(req.method) && !userWriteAllowed(sub, req.method)) {
    return NextResponse.json({ detail: 'Operación reservada para admin' }, { status: 403 });
  }

  const url = new URL(req.url);
  const target = `${base}/api/v1/admin/${sub}${url.search}`;

  const headers = gatewayProxyHeaders({ 'X-Admin-Key': key });
  const actor = auth.ok ? auth.actor : '';
  if (actor) headers['X-Duckclaw-Actor'] = actor;
  const ct = req.headers.get('content-type');
  if (ct) headers['Content-Type'] = ct;
  const isMultipart = ct?.toLowerCase().includes('multipart/form-data') ?? false;

  let bodyText = '';
  const init: RequestInit = { method: req.method, headers, cache: 'no-store' };
  if (req.method !== 'GET' && req.method !== 'HEAD') {
    if (isMultipart) {
      init.body = await req.arrayBuffer();
    } else {
      bodyText = await req.text();
      init.body = bodyText;
    }
  }

  let res: Response;
  let text: string;
  try {
    res = await fetch(target, init);
    text = await res.text();
  } catch (err) {
    const msg = err instanceof Error ? err.message : 'fetch failed';
    const localOps = await localOpsRunFallback(sub, req.method, bodyText);
    if (localOps) return localOps;
    if (sub === 'health') {
      return NextResponse.json(
        {
          detail: 'El API Gateway no responde en este equipo.',
          code: 'gateway_unreachable',
          gateway_url: base,
        },
        { status: 503 }
      );
    }
    return NextResponse.json(
      { detail: `No se pudo contactar el gateway: ${msg}`, code: 'gateway_unreachable' },
      { status: 503 }
    );
  }

  if (sub === 'health' && (res.status === 502 || res.status === 503 || res.status === 504)) {
    return NextResponse.json(
      {
        detail: 'El API Gateway no está disponible.',
        code: 'gateway_unreachable',
        gateway_url: base,
      },
      { status: 503 }
    );
  }

  if (
    req.method === 'GET' &&
    isWorkspaceProjectDetailPath(segments) &&
    (res.status === 404 || res.status === 405)
  ) {
    const projectDetail = await projectDetailFallbackFromList(base, headers, decodeURIComponent(segments[2]));
    if (projectDetail) {
      return NextResponse.json(projectDetail, {
        headers: { 'X-Duckclaw-Admin-Fallback': 'project-detail' },
      });
    }
  }

  if (res.status === 404 && req.method === 'GET') {
    const catalog = catalogFallbackResponse(sub, url.searchParams);
    if (catalog) {
      return NextResponse.json(catalog, {
        headers: { 'X-Duckclaw-Admin-Fallback': 'catalog' },
      });
    }
    if (sub === 'ops/commands') {
      return NextResponse.json(OPS_COMMANDS_FALLBACK, {
        headers: { 'X-Duckclaw-Admin-Fallback': 'ops' },
      });
    }
  }

  if (res.status === 404 && sub === 'playground/config') {
    return NextResponse.json(
      {
        detail: 'El Gateway no expone /api/v1/admin/playground/config. Configuración DB-first requerida.',
        code: 'gateway_stale',
      },
      { status: 503 }
    );
  }

  if (res.status === 404 && sub.startsWith('workspace/orchestrator/')) {
    return NextResponse.json(
      {
        detail:
          'El Gateway no expone Platform Orchestrator todavía. Reinicia DuckClaw-Gateway con PM2 para cargar las rutas DB-first nuevas.',
        code: 'gateway_stale',
      },
      { status: 503 }
    );
  }

  if (res.status === 404 && sub.startsWith('knowledge/')) {
    return NextResponse.json(
      {
        detail:
          'El Gateway no expone Knowledge/RAG todavía. Reinicia DuckClaw-Gateway con PM2 para cargar las rutas DB-first nuevas.',
        code: 'gateway_stale',
      },
      { status: 503 }
    );
  }

  return new NextResponse(text, {
    status: res.status,
    headers: { 'Content-Type': res.headers.get('content-type') || 'application/json' },
  });
}

type Ctx = { params: { path: string[] } };

export async function GET(req: NextRequest, ctx: Ctx) {
  return proxy(req, ctx.params.path ?? []);
}
export async function POST(req: NextRequest, ctx: Ctx) {
  return proxy(req, ctx.params.path ?? []);
}
export async function PUT(req: NextRequest, ctx: Ctx) {
  return proxy(req, ctx.params.path ?? []);
}
export async function PATCH(req: NextRequest, ctx: Ctx) {
  return proxy(req, ctx.params.path ?? []);
}
export async function DELETE(req: NextRequest, ctx: Ctx) {
  return proxy(req, ctx.params.path ?? []);
}
