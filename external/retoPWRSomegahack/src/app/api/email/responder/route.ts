import { NextRequest, NextResponse } from 'next/server';
import { getEmailTransporter } from '@/services/emailService';
import { generateRespuestaTemplate } from '@/lib/emailTemplates';
import type { RespuestaEmailPayload } from '@/types';

export async function POST(req: NextRequest): Promise<NextResponse> {
  try {
    const body: RespuestaEmailPayload = await req.json();

    // Validar campos requeridos
    const required: (keyof RespuestaEmailPayload)[] = [
      'idTicket', 'numeroRadicado', 'emailCiudadano', 'nombreCiudadano',
      'tipoSolicitud', 'secretariaNombre', 'nombreFuncionario', 'cargoFuncionario',
      'textoRespuesta', 'fechaRespuesta'
    ];
    for (const field of required) {
      if (!body[field]) {
        return NextResponse.json(
          { error: `Campo requerido faltante: ${field}` },
          { status: 400 }
        );
      }
    }

    // Validar longitud de la respuesta oficial
    const responseText = body.textoRespuesta.trim();
    if (responseText.length < 50) {
      return NextResponse.json(
        { error: 'La respuesta debe tener al menos 50 caracteres.' },
        { status: 400 }
      );
    }
    if (responseText.length > 5000) {
      return NextResponse.json(
        { error: 'La respuesta no puede superar los 5.000 caracteres.' },
        { status: 400 }
      );
    }

    // Validar formato de email
    const emailCiudadano = body.emailCiudadano.trim();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(emailCiudadano)) {
      return NextResponse.json({ error: 'Formato de email inválido' }, { status: 400 });
    }

    // Generar tracking URL - Limpiar de posibles subrutas accidentales
    const appUrl = (process.env.NEXT_PUBLIC_APP_URL || 'https://crm-pqrsd.vercel.app')
      .replace(/\/dashboard\/?$/, '')
      .replace(/\/+$/, '');
      
    const trackingUrl = body.idTicket ? `${appUrl}/seguimiento/${body.idTicket}` : null;

    // Generar template HTML
    const { subject, html, text } = generateRespuestaTemplate({
      nombreCiudadano:  body.nombreCiudadano,
      numeroRadicado:   body.numeroRadicado,
      tipoSolicitud:    body.tipoSolicitud,
      secretariaNombre: body.secretariaNombre,
      nombreFuncionario: body.nombreFuncionario,
      cargoFuncionario:  body.cargoFuncionario,
      fechaRespuesta:   body.fechaRespuesta,
      textoRespuesta:   body.textoRespuesta,
      trackingUrl,
    });

    // Enviar vía el transporter configurado (mock o Gmail)
    const transporter = getEmailTransporter();
    
    // Verificación de conexión (ayuda a depurar en Vercel)
    const isReady = await transporter.verify();
    if (!isReady && process.env.SMTP_MODE === 'live') {
      console.error('[POST /api/email/responder] ❌ Transporter no está listo');
      return NextResponse.json(
        { error: 'El servidor SMTP no está respondiendo. Verifique credenciales.' },
        { status: 503 }
      );
    }

    const result = await transporter.send({
      to:             body.emailCiudadano,
      toName:         body.nombreCiudadano,
      subject,
      html,
      text,
      idTicket:       body.idTicket,
      numeroRadicado: body.numeroRadicado,
      tipoEmail:      'respuesta_oficial',
    });

    return NextResponse.json(result, { status: result.success ? 200 : 500 });

  } catch (err) {
    const msg = err instanceof Error ? err.message : 'Error interno del servidor';
    console.error('[POST /api/email/responder]', msg);
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}
