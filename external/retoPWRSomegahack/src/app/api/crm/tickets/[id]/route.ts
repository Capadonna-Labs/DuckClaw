import { NextRequest, NextResponse } from 'next/server';
import { TICKETS_MOCK } from '@/services/mockData';
import { crmUsesDuckDb } from '@/lib/crm/crm-mode';
import { ensureCrmReady } from '@/lib/crm/bootstrap';
import { readTicketByIdFromDuckDb } from '@/lib/crm/duck-read';

export async function GET(
  req: NextRequest,
  ctx: { params: { id: string } }
) {
  const { id: idTicket } = ctx.params;
  const idSecretaria = req.nextUrl.searchParams.get('idSecretaria');
  if (!idSecretaria?.trim()) {
    return NextResponse.json({ error: 'idSecretaria es requerido' }, { status: 400 });
  }

  if (!crmUsesDuckDb()) {
    const ticket = TICKETS_MOCK.find((t) => t.idTicket === idTicket);
    if (!ticket) {
      return NextResponse.json(
        { data: null, total: 0, timestamp: new Date().toISOString(), error: 'NOT_FOUND' },
        { status: 404 }
      );
    }
    if (ticket.idSecretaria !== idSecretaria) {
      return NextResponse.json(
        { data: null, total: 0, timestamp: new Date().toISOString(), error: 'ACCESO_DENEGADO' },
        { status: 403 }
      );
    }
    return NextResponse.json({ data: ticket, total: 1, timestamp: new Date().toISOString() });
  }

  const boot = await ensureCrmReady();
  if (!boot.ok) {
    return NextResponse.json(
      { error: boot.detail ?? 'Bootstrap CRM falló' },
      { status: 503 }
    );
  }

  const r = await readTicketByIdFromDuckDb(idTicket, idSecretaria);
  if (!r.ok) {
    if (r.code === 'NOT_FOUND') {
      return NextResponse.json(
        { data: null, total: 0, timestamp: new Date().toISOString(), error: 'NOT_FOUND' },
        { status: 404 }
      );
    }
    return NextResponse.json({ error: r.detail }, { status: 502 });
  }
  return NextResponse.json({ data: r.ticket, total: 1, timestamp: new Date().toISOString() });
}
