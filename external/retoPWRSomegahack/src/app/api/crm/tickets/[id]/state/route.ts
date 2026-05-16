import { NextRequest, NextResponse } from 'next/server';
import { TICKETS_MOCK } from '@/services/mockData';
import { crmUsesDuckDb } from '@/lib/crm/crm-mode';
import { ensureCrmReady } from '@/lib/crm/bootstrap';
import { updateTicketEstadoInDuckDb } from '@/lib/crm/duck-state';
import type { TicketEstado } from '@/types';

export async function PATCH(
  req: NextRequest,
  ctx: { params: { id: string } }
) {
  const { id: idTicket } = ctx.params;
  let body: { idSecretaria?: string; estado?: TicketEstado };
  try {
    body = (await req.json()) as { idSecretaria?: string; estado?: TicketEstado };
  } catch {
    return NextResponse.json({ error: 'JSON inválido' }, { status: 400 });
  }

  const idSecretaria = (body.idSecretaria ?? '').trim();
  const estado = body.estado;
  if (!idSecretaria || !estado) {
    return NextResponse.json({ error: 'idSecretaria y estado son requeridos' }, { status: 400 });
  }

  if (!crmUsesDuckDb()) {
    const idx = TICKETS_MOCK.findIndex((t) => t.idTicket === idTicket);
    if (idx < 0) {
      return NextResponse.json({ error: 'Ticket no encontrado' }, { status: 404 });
    }
    if (TICKETS_MOCK[idx].idSecretaria !== idSecretaria) {
      return NextResponse.json({ error: 'ACCESO_DENEGADO' }, { status: 403 });
    }
    TICKETS_MOCK[idx].estado = estado;
    return NextResponse.json({ ok: true });
  }

  const boot = await ensureCrmReady();
  if (!boot.ok) {
    return NextResponse.json({ error: boot.detail ?? 'Bootstrap CRM falló' }, { status: 503 });
  }

  const r = await updateTicketEstadoInDuckDb(idTicket, idSecretaria, estado);
  if (!r.ok) {
    return NextResponse.json({ error: r.detail }, { status: 502 });
  }
  return NextResponse.json({ ok: true });
}
