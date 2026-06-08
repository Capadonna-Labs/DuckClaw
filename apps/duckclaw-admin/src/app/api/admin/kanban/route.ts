import { NextRequest, NextResponse } from 'next/server';
import { requireAdminRouteAuth } from '@/lib/adminRouteAuth';
import { adminApiKey, gatewayBase, gatewayProxyHeaders } from '@/lib/gatewayProxy';

function gatewayStale() {
  return NextResponse.json(
    {
      detail: 'Kanban DB-first requiere endpoint Gateway /api/v1/admin/kanban.',
      code: 'gateway_stale',
    },
    { status: 503 }
  );
}

async function proxyKanban(req: NextRequest, roles: ('admin' | 'user')[]) {
  const auth = await requireAdminRouteAuth(req, { roles });
  if (!auth.ok) return auth.response;

  const base = gatewayBase();
  const key = adminApiKey();
  if (!base || !key) return gatewayStale();

  const url = new URL(req.url);
  const target = `${base}/api/v1/admin/kanban${url.search}`;
  const headers = gatewayProxyHeaders({ 'X-Admin-Key': key });
  if (auth.actor) headers['X-Duckclaw-Actor'] = auth.actor;
  const contentType = req.headers.get('content-type');
  if (contentType) headers['Content-Type'] = contentType;

  const init: RequestInit = { method: req.method, headers, cache: 'no-store' };
  if (req.method !== 'GET' && req.method !== 'HEAD') {
    init.body = await req.text();
  }

  let response: Response;
  let text: string;
  try {
    response = await fetch(target, init);
    text = await response.text();
  } catch {
    return NextResponse.json(
      {
        detail: 'No se pudo contactar el Gateway para Kanban DB-first.',
        code: 'gateway_unreachable',
      },
      { status: 503 }
    );
  }

  if (response.status === 404) return gatewayStale();

  return new NextResponse(text, {
    status: response.status,
    headers: {
      'Content-Type': response.headers.get('content-type') || 'application/json',
      'X-Duckclaw-Kanban-Via': 'gateway',
    },
  });
}

export async function GET(req: NextRequest) {
  return proxyKanban(req, ['admin', 'user']);
}

export async function POST(req: NextRequest) {
  return proxyKanban(req, ['admin']);
}

export async function PATCH(req: NextRequest) {
  return proxyKanban(req, ['admin']);
}

export async function DELETE(req: NextRequest) {
  return proxyKanban(req, ['admin']);
}
