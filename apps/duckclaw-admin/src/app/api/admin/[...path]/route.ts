import { NextRequest, NextResponse } from 'next/server';
import { catalogFallbackResponse } from '@/lib/adminCatalogFallback';
import { fallbackPlaygroundConfig } from '@/lib/playgroundFallback';
import { adminApiKey, gatewayBase, gatewayProxyHeaders } from '@/lib/gatewayProxy';

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
      label: 'Iniciar plataforma (PM2 + Telegram)',
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

async function proxy(req: NextRequest, segments: string[]) {
  const base = gatewayBase();
  const key = adminApiKey();
  if (!base) {
    return NextResponse.json({ detail: 'DUCKCLAW_GATEWAY_URL no configurada' }, { status: 503 });
  }
  if (!key) {
    return NextResponse.json({ detail: 'DUCKCLAW_ADMIN_API_KEY no configurada' }, { status: 503 });
  }

  const role = req.headers.get('x-duckclaw-role') || 'admin';
  const sub = segments.join('/');
  if (segments[0] === 'audit' && role !== 'admin') {
    return NextResponse.json({ detail: 'Auditoría solo para rol admin' }, { status: 403 });
  }
  if (segments[0] === 'ops' && role !== 'admin') {
    return NextResponse.json({ detail: 'Operaciones solo para rol admin' }, { status: 403 });
  }
  if (role === 'viewer' && WRITE_METHODS.has(req.method)) {
    return NextResponse.json({ detail: 'Solo lectura (rol viewer)' }, { status: 403 });
  }

  const url = new URL(req.url);
  const target = `${base}/api/v1/admin/${sub}${url.search}`;

  const headers = gatewayProxyHeaders({ 'X-Admin-Key': key });
  const actor = req.headers.get('x-duckclaw-actor');
  if (actor) headers['X-Duckclaw-Actor'] = actor;
  const ct = req.headers.get('content-type');
  if (ct) headers['Content-Type'] = ct;

  const init: RequestInit = { method: req.method, headers, cache: 'no-store' };
  if (req.method !== 'GET' && req.method !== 'HEAD') {
    init.body = await req.text();
  }

  let res: Response;
  let text: string;
  try {
    res = await fetch(target, init);
    text = await res.text();
  } catch (err) {
    const msg = err instanceof Error ? err.message : 'fetch failed';
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
    if (sub === 'playground/config') {
      return NextResponse.json(fallbackPlaygroundConfig(), {
        headers: { 'X-Duckclaw-Admin-Fallback': 'playground' },
      });
    }
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
