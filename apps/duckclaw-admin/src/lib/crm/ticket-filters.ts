import type { Ticket, TicketsFilter } from '@/types';

export function applyTicketFilters(tickets: Ticket[], filters?: TicketsFilter): Ticket[] {
  if (!filters) return tickets;
  let out = tickets;
  if (filters.estado && filters.estado !== 'Todos') {
    out = out.filter((t) => t.estado === filters.estado);
  }
  if (filters.tipoSolicitud && filters.tipoSolicitud !== 'Todos') {
    out = out.filter((t) => t.tipoSolicitud === filters.tipoSolicitud);
  }
  if (filters.searchQuery) {
    const q = filters.searchQuery.toLowerCase();
    out = out.filter(
      (t) =>
        t.nombreCiudadano.toLowerCase().includes(q) || t.contenidoRaw.toLowerCase().includes(q)
    );
  }
  return out;
}
