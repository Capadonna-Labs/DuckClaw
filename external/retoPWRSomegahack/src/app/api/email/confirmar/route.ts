import { NextRequest, NextResponse } from 'next/server';
import { getEmailTransporter } from '@/services/emailService';
import { generateConfirmacionTemplate } from '@/lib/emailTemplates';
import type { ConfirmacionEmailPayload } from '@/types';
import { format, parseISO } from 'date-fns';
import { es } from 'date-fns/locale';

export async function POST(req: NextRequest): Promise<NextResponse> {
  try {
    const body: ConfirmacionEmailPayload = await req.json();

    // Validar campos requeridos
    const required: (keyof ConfirmacionEmailPayload)[] = [
      'idTicket', 'numeroRadicado', 'emailCiudadano',
      'nombreCiudadano', 'tipoSolicitud', 'secretariaNombre', 'fechaLimiteRespuesta',
    ];
    for (const field of required) {
      if (!body[field]) {
        return NextResponse.json(
          { error: `Campo requerido faltante: ${field}` },
          { status: 400 }
        );
      }
    }

    // Validar formato de email
    const emailCiudadano = body.emailCiudadano.trim();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(emailCiudadano)) {
      return NextResponse.json({ error: 'Formato de email inválido' }, { status: 400 });
    }

    // Formatear fechas en español colombiano para el template
    const formatoFecha = "d 'de' MMMM 'de' yyyy";
    const fechaRadicacion = format(new Date(), formatoFecha, { locale: es });
    const fechaLimite     = format(parseISO(body.fechaLimiteRespuesta), formatoFecha, { locale: es });

    // Generar template HTML
    const { subject, html, text } = generateConfirmacionTemplate({
      nombreCiudadano:      body.nombreCiudadano,
      numeroRadicado:       body.numeroRadicado,
      tipoSolicitud:        body.tipoSolicitud,
      secretariaNombre:     body.secretariaNombre,
      fechaRadicacion,
      fechaLimiteRespuesta: fechaLimite,
    });

    // Enviar vía el transporter configurado (mock o Gmail)
    const transporter = getEmailTransporter();
    const result = await transporter.send({
      to:             body.emailCiudadano,
      toName:         body.nombreCiudadano,
      subject,
      html,
      text,
      idTicket:       body.idTicket,
      numeroRadicado: body.numeroRadicado,
      tipoEmail:      'confirmacion_radicado',
    });

    return NextResponse.json(result, { status: result.success ? 200 : 500 });

  } catch (err) {
    const msg = err instanceof Error ? err.message : 'Error interno del servidor';
    console.error('[POST /api/email/confirmar]', msg);
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}
