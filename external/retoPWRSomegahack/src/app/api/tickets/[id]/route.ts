import { NextRequest, NextResponse } from 'next/server';
import { query, queryOne, ensureSchema } from '@/lib/motherduck';
import { mapRowToTicket } from '@/lib/ticketMapper';

const T = 'pqrsd_crm.tickets';

/**
 * GET /api/tickets/[id] — Detalle de un ticket
 */
export async function GET(
  _req: NextRequest,
  { params }: { params: { id: string } }
) {
  try {
    await ensureSchema();

    const row = await queryOne(
      `SELECT * FROM ${T} WHERE id_ticket = ?`,
      [params.id]
    );

    if (!row) {
      return NextResponse.json(
        { data: null, total: 0, timestamp: new Date().toISOString(), error: 'NOT_FOUND' },
        { status: 404 }
      );
    }

    return NextResponse.json({
      data: mapRowToTicket(row),
      total: 1,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error('[API /tickets/[id] GET]', error);
    return NextResponse.json(
      { data: null, total: 0, timestamp: new Date().toISOString(), error: 'Error al obtener ticket' },
      { status: 500 }
    );
  }
}

/**
 * PATCH /api/tickets/[id] — Actualiza campos de un ticket
 */
export async function PATCH(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  try {
    await ensureSchema();

    const body = await req.json();
    const updates: string[] = [];
    const values: unknown[] = [];

    const allowedFields: Record<string, string> = {
      estado: 'estado',
      respuestaSugerida: 'respuesta_sugerida',
      resumenIa: 'resumen_ia',
      nombreCiudadano: 'nombre_ciudadano',
      emailCiudadano: 'email_ciudadano',
      telefonoCiudadano: 'telefono_ciudadano',
      tipoSolicitud: 'tipo_solicitud',
    };

    for (const [camelKey, snakeKey] of Object.entries(allowedFields)) {
      if (body[camelKey] !== undefined) {
        updates.push(`${snakeKey} = ?`);
        values.push(body[camelKey]);
      }
    }

    if (updates.length === 0) {
      return NextResponse.json({ error: 'No hay campos para actualizar' }, { status: 400 });
    }

    updates.push('fecha_actualizacion = CURRENT_TIMESTAMP');
    values.push(params.id);

    const sql = `UPDATE ${T} SET ${updates.join(', ')} WHERE id_ticket = ?`;
    await query(sql, values);

    return NextResponse.json({
      data: { success: true },
      total: 1,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error('[API /tickets/[id] PATCH]', error);
    return NextResponse.json(
      { error: 'Error al actualizar ticket' },
      { status: 500 }
    );
  }
}
