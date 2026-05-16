import { NextRequest, NextResponse } from 'next/server';
import { TICKETS_MOCK } from '@/services/mockData';
import { applyTicketFilters } from '@/lib/crm/ticket-filters';
import { crmUsesDuckDb } from '@/lib/crm/crm-mode';
import { ensureCrmReady } from '@/lib/crm/bootstrap';
import { readTicketsFromDuckDb } from '@/lib/crm/duck-read';
import type { TicketsFilter, TicketEstado, TipoSolicitud } from '@/types';

function parseFilters(req: NextRequest): TicketsFilter | undefined {
  const sp = req.nextUrl.searchParams;
  const estado = sp.get('estado');
  const tipoSolicitud = sp.get('tipoSolicitud');
  const searchQuery = sp.get('searchQuery') ?? undefined;
  if (!estado && !tipoSolicitud && !searchQuery) return undefined;
  return {
    ...(estado ? { estado: estado as TicketEstado | 'Todos' } : {}),
    ...(tipoSolicitud ? { tipoSolicitud: tipoSolicitud as TipoSolicitud | 'Todos' } : {}),
    ...(searchQuery ? { searchQuery } : {}),
  };
}

export async function GET(req: NextRequest) {
  const idSecretaria = req.nextUrl.searchParams.get('idSecretaria');
  if (!idSecretaria?.trim()) {
    return NextResponse.json({ error: 'idSecretaria es requerido' }, { status: 400 });
  }
  const filters = parseFilters(req);

  if (!crmUsesDuckDb()) {
    let list = TICKETS_MOCK.filter((t) => t.idSecretaria === idSecretaria);
    list = applyTicketFilters(list, filters);
    return NextResponse.json({
      data: list,
      total: list.length,
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

  const r = await readTicketsFromDuckDb(idSecretaria, filters);
  if (!r.ok) {
    return NextResponse.json({ error: r.detail }, { status: 502 });
  }
  return NextResponse.json({
    data: r.tickets,
    total: r.tickets.length,
    timestamp: new Date().toISOString(),
  });
}
