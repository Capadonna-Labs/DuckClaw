import { NextRequest, NextResponse } from 'next/server';
import { TICKETS_MOCK } from '@/services/mockData';
import { crmUsesDuckDb } from '@/lib/crm/crm-mode';
import { ensureCrmReady } from '@/lib/crm/bootstrap';
import { respondTicketInDuckDb } from '@/lib/crm/duck-respond';
import { readTicketByIdFromDuckDb } from '@/lib/crm/duck-read';

export async function POST(
  req: NextRequest,
  ctx: { params: { id: string } }
) {
  const { id: idTicket } = ctx.params;
  let body: { respuestaFinal?: string; idSecretaria?: string };
  try {
    body = (await req.json()) as { respuestaFinal?: string; idSecretaria?: string };
  } catch {
    return NextResponse.json({ error: 'JSON inválido' }, { status: 400 });
  }

  const respuestaFinal = (body.respuestaFinal ?? '').trim();
  const idSecretaria = (body.idSecretaria ?? '').trim();
  if (!respuestaFinal || !idSecretaria) {
    return NextResponse.json({ error: 'respuestaFinal e idSecretaria son requeridos' }, { status: 400 });
  }

  if (!crmUsesDuckDb()) {
    const ticket = TICKETS_MOCK.find((t) => t.idTicket === idTicket);
    if (!ticket || ticket.idSecretaria !== idSecretaria) {
      return NextResponse.json(
        {
          data: { success: false },
          total: 0,
          timestamp: new Date().toISOString(),
          error: 'No tienes permisos para responder este ticket',
        },
        { status: 403 }
      );
    }
    ticket.estado = 'Resuelto';
    ticket.respuestaSugerida = respuestaFinal;
    return NextResponse.json({
      data: { success: true },
      total: 1,
      timestamp: new Date().toISOString(),
    });
  }

  const boot = await ensureCrmReady();
  if (!boot.ok) {
    return NextResponse.json(
      { error: boot.detail ?? 'Bootstrap CRM falló' },
      { status: 503 }
    );
  }

  const found = await readTicketByIdFromDuckDb(idTicket, idSecretaria);
  if (!found.ok) {
    if (found.code === 'NOT_FOUND') {
      return NextResponse.json(
        {
          data: { success: false },
          total: 0,
          timestamp: new Date().toISOString(),
          error: 'NOT_FOUND',
        },
        { status: 404 }
      );
    }
    return NextResponse.json(
      {
        data: { success: false },
        total: 0,
        timestamp: new Date().toISOString(),
        error: found.detail,
      },
      { status: 502 }
    );
  }

  const r = await respondTicketInDuckDb(idTicket, idSecretaria, respuestaFinal);
  if (!r.ok) {
    return NextResponse.json(
      {
        data: { success: false },
        total: 0,
        timestamp: new Date().toISOString(),
        error: r.detail,
      },
      { status: 502 }
    );
  }

  return NextResponse.json({
    data: { success: true },
    total: 1,
    timestamp: new Date().toISOString(),
  });
}
