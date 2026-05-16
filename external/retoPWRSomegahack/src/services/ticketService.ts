import {
  TICKETS_MOCK,
  SECRETARIAS_MOCK,
  DELAY_SIMULADO_MS,
} from './mockData';
import {
  Ticket,
  TicketsFilter,
  ApiResponse,
  Secretaria,
  TicketEstado,
} from '@/types';
import { DataMode } from '@/store/authStore';

function buildTicketsQuery(idSecretaria: string, filters?: TicketsFilter): string {
  const sp = new URLSearchParams({ idSecretaria });
  if (filters?.estado && filters.estado !== 'Todos') sp.set('estado', filters.estado);
  if (filters?.tipoSolicitud && filters.tipoSolicitud !== 'Todos') {
    sp.set('tipoSolicitud', filters.tipoSolicitud);
  }
  if (filters?.searchQuery?.trim()) sp.set('searchQuery', filters.searchQuery.trim());
  return `/api/crm/tickets?${sp.toString()}`;
}

// ──────────────────────────────────────────────────
// CAPA LIVE: API CRM (DuckDB o mock vía /api/crm)
// ──────────────────────────────────────────────────

async function liveGetTickets(
  idSecretaria: string,
  filters?: TicketsFilter
): Promise<ApiResponse<Ticket[]>> {
  try {
    await new Promise((resolve) => setTimeout(resolve, DELAY_SIMULADO_MS));

    const res = await fetch(buildTicketsQuery(idSecretaria, filters), {
      cache: 'no-store',
    });
    const json = (await res.json()) as ApiResponse<Ticket[]> & { error?: string };

    if (!res.ok) {
      return {
        data: [],
        total: 0,
        timestamp: new Date().toISOString(),
        error: json.error ?? `Error ${res.status}`,
      };
    }

    return {
      data: json.data ?? [],
      total: json.total ?? 0,
      timestamp: json.timestamp ?? new Date().toISOString(),
    };
  } catch (error) {
    return {
      data: [],
      total: 0,
      timestamp: new Date().toISOString(),
      error: error instanceof Error ? error.message : 'Error desconocido',
    };
  }
}

async function liveGetTicketById(
  idTicket: string,
  idSecretariaUsuario: string
): Promise<ApiResponse<Ticket | null>> {
  try {
    await new Promise((resolve) => setTimeout(resolve, DELAY_SIMULADO_MS));

    const sp = new URLSearchParams({ idSecretaria: idSecretariaUsuario });
    const res = await fetch(
      `/api/crm/tickets/${encodeURIComponent(idTicket)}?${sp}`,
      { cache: 'no-store' }
    );
    const json = (await res.json()) as ApiResponse<Ticket | null> & { error?: string };

    if (res.status === 403) {
      return {
        data: null,
        total: 0,
        timestamp: new Date().toISOString(),
        error: 'ACCESO_DENEGADO',
      };
    }
    if (res.status === 404) {
      return {
        data: null,
        total: 0,
        timestamp: new Date().toISOString(),
        error: 'NOT_FOUND',
      };
    }
    if (!res.ok) {
      return {
        data: null,
        total: 0,
        timestamp: new Date().toISOString(),
        error: json.error ?? `Error ${res.status}`,
      };
    }

    return {
      data: json.data ?? null,
      total: json.total ?? 0,
      timestamp: json.timestamp ?? new Date().toISOString(),
    };
  } catch (error) {
    return {
      data: null,
      total: 0,
      timestamp: new Date().toISOString(),
      error: error instanceof Error ? error.message : 'Error en el servidor',
    };
  }
}

async function liveActualizarRespuesta(
  idTicket: string,
  respuestaFinal: string,
  idSecretariaUsuario: string
): Promise<ApiResponse<{ success: boolean }>> {
  try {
    await new Promise((resolve) => setTimeout(resolve, DELAY_SIMULADO_MS));

    const res = await fetch(`/api/crm/tickets/${encodeURIComponent(idTicket)}/respond`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        respuestaFinal,
        idSecretaria: idSecretariaUsuario,
      }),
      cache: 'no-store',
    });
    const json = (await res.json()) as ApiResponse<{ success: boolean }> & { error?: string };

    if (!res.ok) {
      return {
        data: { success: false },
        total: 0,
        timestamp: new Date().toISOString(),
        error: json.error ?? `Error ${res.status}`,
      };
    }

    return {
      data: json.data ?? { success: true },
      total: json.total ?? 1,
      timestamp: json.timestamp ?? new Date().toISOString(),
      error: json.error,
    };
  } catch (error) {
    return {
      data: { success: false },
      total: 0,
      timestamp: new Date().toISOString(),
      error: error instanceof Error ? error.message : 'Error al procesar respuesta',
    };
  }
}

async function liveActualizarEstado(
  idTicket: string,
  nuevoEstado: TicketEstado,
  idSecretariaUsuario: string
): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, 300));

  const res = await fetch(`/api/crm/tickets/${encodeURIComponent(idTicket)}/state`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ idSecretaria: idSecretariaUsuario, estado: nuevoEstado }),
    cache: 'no-store',
  });
  if (!res.ok) {
    const j = (await res.json().catch(() => ({}))) as { error?: string };
    throw new Error(j.error ?? `HTTP ${res.status}`);
  }
}

// ──────────────────────────────────────────────────
// CAPA MOCK: datos locales
// ──────────────────────────────────────────────────

async function mockGetTickets(
  idSecretaria: string,
  filters?: TicketsFilter
): Promise<ApiResponse<Ticket[]>> {
  await new Promise(resolve => setTimeout(resolve, DELAY_SIMULADO_MS));

  let tickets = TICKETS_MOCK.filter(t => t.idSecretaria === idSecretaria);

  if (filters) {
    if (filters.estado && filters.estado !== 'Todos') {
      tickets = tickets.filter(t => t.estado === filters.estado);
    }
    if (filters.tipoSolicitud && filters.tipoSolicitud !== 'Todos') {
      tickets = tickets.filter(t => t.tipoSolicitud === filters.tipoSolicitud);
    }
    if (filters.searchQuery) {
      const q = filters.searchQuery.toLowerCase();
      tickets = tickets.filter(
        t =>
          t.nombreCiudadano.toLowerCase().includes(q) ||
          t.contenidoRaw.toLowerCase().includes(q)
      );
    }
  }

  return { data: tickets, total: tickets.length, timestamp: new Date().toISOString() };
}

async function mockGetTicketById(
  idTicket: string,
  idSecretaria: string
): Promise<ApiResponse<Ticket | null>> {
  await new Promise(resolve => setTimeout(resolve, DELAY_SIMULADO_MS));

  const ticket = TICKETS_MOCK.find(t => t.idTicket === idTicket);
  if (!ticket) {
    return { data: null, total: 0, timestamp: new Date().toISOString(), error: 'NOT_FOUND' };
  }
  if (ticket.idSecretaria !== idSecretaria) {
    return { data: null, total: 0, timestamp: new Date().toISOString(), error: 'ACCESO_DENEGADO' };
  }
  return { data: ticket, total: 1, timestamp: new Date().toISOString() };
}

async function mockActualizarRespuesta(
  idTicket: string,
  respuestaFinal: string,
  idSecretaria: string
): Promise<ApiResponse<{ success: boolean }>> {
  await new Promise(resolve => setTimeout(resolve, DELAY_SIMULADO_MS));

  const ticket = TICKETS_MOCK.find(t => t.idTicket === idTicket);
  if (!ticket || ticket.idSecretaria !== idSecretaria) {
    throw new Error('No tienes permisos para responder este ticket');
  }

  ticket.respuestaSugerida = respuestaFinal;
  ticket.estado = 'Resuelto';

  return { data: { success: true }, total: 1, timestamp: new Date().toISOString() };
}

async function mockActualizarEstado(idTicket: string, nuevoEstado: TicketEstado): Promise<void> {
  await new Promise(resolve => setTimeout(resolve, 300));
  const idx = TICKETS_MOCK.findIndex(t => t.idTicket === idTicket);
  if (idx !== -1) {
    TICKETS_MOCK[idx].estado = nuevoEstado;
  } else {
    throw new Error('Ticket no encontrado');
  }
}

// ──────────────────────────────────────────────────
// FUNCIONES PÚBLICAS — Despachan según DataMode
// ──────────────────────────────────────────────────

export async function getTicketsBySecretaria(
  idSecretaria: string,
  mode: DataMode,
  filters?: TicketsFilter
): Promise<ApiResponse<Ticket[]>> {
  return mode === 'live'
    ? liveGetTickets(idSecretaria, filters)
    : mockGetTickets(idSecretaria, filters);
}

export async function getTicketById(
  idTicket: string,
  idSecretaria: string,
  mode: DataMode
): Promise<ApiResponse<Ticket | null>> {
  return mode === 'live'
    ? liveGetTicketById(idTicket, idSecretaria)
    : mockGetTicketById(idTicket, idSecretaria);
}

export async function actualizarRespuesta(
  idTicket: string,
  respuestaFinal: string,
  idSecretaria: string,
  mode: DataMode
): Promise<ApiResponse<{ success: boolean }>> {
  return mode === 'live'
    ? liveActualizarRespuesta(idTicket, respuestaFinal, idSecretaria)
    : mockActualizarRespuesta(idTicket, respuestaFinal, idSecretaria);
}

export async function getSecretarias(): Promise<ApiResponse<Secretaria[]>> {
  return {
    data: SECRETARIAS_MOCK,
    total: SECRETARIAS_MOCK.length,
    timestamp: new Date().toISOString(),
  };
}

export async function actualizarEstadoTicket(
  idTicket: string,
  nuevoEstado: TicketEstado,
  idSecretaria: string,
  mode: DataMode
): Promise<void> {
  return mode === 'live'
    ? liveActualizarEstado(idTicket, nuevoEstado, idSecretaria)
    : mockActualizarEstado(idTicket, nuevoEstado);
}
