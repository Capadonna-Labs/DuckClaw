import { NextRequest, NextResponse } from 'next/server';
import { HOST_ONLY_OPS, isLocalOpId, listOpsCommands, runOpsLocal } from '@/lib/localOps';

const WRITE_METHODS = new Set(['POST']);

function gatewayBase(): string | null {
  const raw =
    process.env.DUCKCLAW_GATEWAY_URL?.trim() ||
    process.env.NEXT_PUBLIC_DUCKCLAW_GATEWAY_URL?.trim() ||
    '';
  return raw ? raw.replace(/\/$/, '') : null;
}

function adminKey(): string {
  return (process.env.DUCKCLAW_ADMIN_API_KEY || '').trim();
}

/** Ejecuta ops en el host del admin cuando el gateway aún no expone POST /ops/run. */
export async function POST(req: NextRequest) {
  const role = req.headers.get('x-duckclaw-role') || 'admin';
  if (role !== 'admin') {
    return NextResponse.json({ detail: 'Operaciones solo para rol admin' }, { status: 403 });
  }

  let body: { op_id?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ detail: 'JSON inválido' }, { status: 400 });
  }

  const opId = (body.op_id || '').trim();
  if (!opId) {
    return NextResponse.json({ detail: 'op_id requerido' }, { status: 400 });
  }

  const base = gatewayBase();
  const key = adminKey();

  if (HOST_ONLY_OPS.has(opId)) {
    try {
      const result = await runOpsLocal(opId);
      return NextResponse.json(result, {
        headers: { 'X-Duckclaw-Ops-Via': 'local-host-only' },
      });
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Error ejecutando comando';
      return NextResponse.json({ detail: msg }, { status: 400 });
    }
  }

  if (base && key) {
    try {
      const headers: Record<string, string> = {
        'X-Admin-Key': key,
        Accept: 'application/json',
        'Content-Type': 'application/json',
      };
      const actor = req.headers.get('x-duckclaw-actor');
      if (actor) headers['X-Duckclaw-Actor'] = actor;

      const res = await fetch(`${base}/api/v1/admin/ops/run`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ op_id: opId }),
        cache: 'no-store',
      });

      const useGateway =
        res.status !== 404 && !(res.status === 400 && isLocalOpId(opId));
      if (useGateway) {
        const text = await res.text();
        return new NextResponse(text, {
          status: res.status,
          headers: {
            'Content-Type': res.headers.get('content-type') || 'application/json',
            'X-Duckclaw-Ops-Via': 'gateway',
          },
        });
      }
    } catch {
      /* gateway caído → local */
    }
  }

  try {
    const result = await runOpsLocal(opId);
    return NextResponse.json(result, {
      headers: { 'X-Duckclaw-Ops-Via': 'local' },
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : 'Error ejecutando comando';
    return NextResponse.json({ detail: msg }, { status: 400 });
  }
}

export async function GET() {
  return NextResponse.json(listOpsCommands());
}
