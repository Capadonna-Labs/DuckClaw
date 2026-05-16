import { NextRequest, NextResponse } from 'next/server';
import { queryOne, ensureSchema } from '@/lib/motherduck';

const T = 'pqrsd_crm.tickets';

/**
 * GET /api/tickets/[id]/public — Datos públicos para seguimiento del ciudadano.
 * NO requiere autenticación. Solo expone campos seguros.
 */
export async function GET(
  _req: NextRequest,
  { params }: { params: { id: string } }
) {
  try {
    await ensureSchema();

    const row = await queryOne<{
      id_ticket: string;
      numero_radicado: string;
      tipo_solicitud: string;
      asunto: string;
      estado: string;
      nombre_ciudadano: string;
      fecha_creacion: string | Date;
      fecha_limite: string | Date;
      fecha_actualizacion: string | Date;
    }>(
      `SELECT 
        id_ticket, numero_radicado, tipo_solicitud, asunto,
        estado, nombre_ciudadano, fecha_creacion, fecha_limite, fecha_actualizacion
       FROM ${T} 
       WHERE id_ticket = ?`,
      [params.id]
    );

    if (!row) {
      return NextResponse.json(
        { error: 'Ticket no encontrado', data: null },
        { status: 404 }
      );
    }

    return NextResponse.json({
      data: {
        idTicket: row.id_ticket,
        numeroRadicado: row.numero_radicado,
        tipoSolicitud: row.tipo_solicitud,
        asunto: row.asunto,
        estado: row.estado,
        nombreCiudadano: row.nombre_ciudadano,
        fechaCreacion: typeof row.fecha_creacion === 'object' 
          ? (row.fecha_creacion as Date).toISOString() 
          : row.fecha_creacion,
        fechaLimite: typeof row.fecha_limite === 'object' 
          ? (row.fecha_limite as Date).toISOString() 
          : row.fecha_limite,
        fechaActualizacion: typeof row.fecha_actualizacion === 'object' 
          ? (row.fecha_actualizacion as Date).toISOString() 
          : row.fecha_actualizacion,
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error('[API /tickets/[id]/public GET]', error);
    return NextResponse.json(
      { error: 'Error al consultar ticket' },
      { status: 500 }
    );
  }
}
