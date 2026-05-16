import { NextRequest, NextResponse } from 'next/server';
import { query, ensureSchema } from '@/lib/motherduck';
import { generarNumeroRadicado } from '@/lib/radicado';
import { sendConfirmationEmail } from '@/services/emailService';
import { extraerEmail } from '@/lib/utils';

const T = 'pqrsd_crm.tickets';

interface ManualTicketInput {
  idSecretaria?: string;
  nombreCiudadano?: string;
  documento?: string;
  emailCiudadano?: string;
  telefono?: string;
  tipoSolicitud?: string;
  asunto?: string;
  contenidoRaw: string;
}

export async function POST(req: NextRequest) {
  try {
    const { tickets }: { tickets: ManualTicketInput[] } = await req.json();

    if (!Array.isArray(tickets) || tickets.length === 0) {
      return NextResponse.json({ error: 'Se requiere un array de tickets' }, { status: 400 });
    }

    await ensureSchema();

    const results = [];

    for (const t of tickets) {
      const idTicket = `tk-manual-${Date.now()}-${Math.floor(Math.random() * 1000)}`;
      const secId = t.idSecretaria || 'sec-salud';
      const emailCiudadanoLimpio = extraerEmail(t.emailCiudadano || '');
      const numeroRadicado = generarNumeroRadicado(secId);
      const fechaCreacion = new Date().toISOString();
      const fechaLimite = new Date(Date.now() + 15 * 24 * 60 * 60 * 1000).toISOString();

      console.log(`[Batch-Insert] ℹ️ Procesando ticket para secretaría: ${secId}`);

      await query(
        `INSERT INTO ${T} (
          id_ticket, numero_radicado, id_secretaria, nombre_ciudadano,
          documento_ciudadano, email_ciudadano, telefono_ciudadano, tipo_solicitud, asunto, contenido_raw,
          estado, canal_origen, fecha_creacion, fecha_limite, fecha_actualizacion
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)`,
        [
          idTicket,
          numeroRadicado,
          secId,
          t.nombreCiudadano || 'Anónimo',
          t.documento?.trim() || null,
          emailCiudadanoLimpio || null,
          t.telefono?.trim() || null,
          t.tipoSolicitud || 'Peticion',
          t.asunto || 'Radicación Manual (Físico)',
          t.contenidoRaw,
          'Pendiente',
          'Presencial',
          fechaCreacion,
          fechaLimite,
        ]
      );
      
      if (emailCiudadanoLimpio && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(emailCiudadanoLimpio)) {
        try {
          await sendConfirmationEmail(
            emailCiudadanoLimpio,
            numeroRadicado,
            t.nombreCiudadano || 'Ciudadano',
            t.contenidoRaw,
            idTicket
          );
          console.log(`[Batch-Email] ✅ Confirmación enviada a ${emailCiudadanoLimpio}`);
        } catch (mailErr) {
          console.error(`[Batch-Email] ❌ Fallo al enviar a ${emailCiudadanoLimpio}:`, mailErr);
        }
      }
      
      results.push({ idTicket, numeroRadicado });
    }

    console.log(`[Batch-Insert] ✅ ${results.length} tickets manuales creados`);

    return NextResponse.json({ 
      success: true, 
      created: results.length, 
      data: results 
    });

  } catch (error) {
    console.error('[Batch-Insert-Error]', error);
    return NextResponse.json({ 
      error: 'Error al procesar el lote de tickets',
      details: error instanceof Error ? error.message : 'Unknown'
    }, { status: 500 });
  }
}
