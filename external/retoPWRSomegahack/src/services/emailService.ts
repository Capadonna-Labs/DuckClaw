import type { EmailSendResult, TipoEmail } from '@/types';
import nodemailer, { Transporter } from 'nodemailer';
import { extraerEmail } from '@/lib/utils';

export interface EmailOptions {
  to:       string;
  toName?:  string;
  subject:  string;
  html:     string;
  text:     string;
  // Metadata para el registro en DuckDB (futuro)
  idTicket?:       string;
  numeroRadicado?: string;
  tipoEmail?:      TipoEmail;
}

export interface IEmailTransporter {
  send(options: EmailOptions): Promise<EmailSendResult>;
  verify(): Promise<boolean>;
}

/**
 * IMPLEMENTACIÓN 1: MockTransporter
 * Simula el envío (logs en consola, sin Nodemailer real)
 */
class MockTransporter implements IEmailTransporter {
  async send(options: EmailOptions): Promise<EmailSendResult> {
    const messageId = `<mock-${Date.now()}@crm-pqrsd.medellin.gov.co>`;

    // Log estructurado — visible en la terminal de Next.js durante la demo
    const separator = '═'.repeat(65);
    console.log(`\n${separator}`);
    console.log('📬  CRM PQRSD — EMAIL SIMULADO (SMTP_MODE=mock)');
    console.log(separator);
    console.log(`  ▶ Para:      ${options.toName ? `${options.toName} <${options.to}>` : options.to}`);
    console.log(`  ▶ Asunto:    ${options.subject}`);
    console.log(`  ▶ Radicado:  ${options.numeroRadicado ?? 'N/A'}`);
    console.log(`  ▶ Tipo:      ${options.tipoEmail ?? 'N/A'}`);
    console.log(`  ▶ Message-ID: ${messageId}`);
    console.log(`  ▶ Timestamp:  ${new Date().toISOString()}`);
    console.log(`${separator}\n`);

    // Simula latencia de red para que la UI muestre el spinner
    await new Promise(resolve => setTimeout(resolve, 600 + Math.random() * 400));

    return {
      success:   true,
      messageId,
      simulado:  true,
      registro: {
        idRegistro:     `reg-mock-${Date.now()}`,
        idTicket:        options.idTicket        ?? '',
        numeroRadicado:  options.numeroRadicado  ?? '',
        tipoEmail:       options.tipoEmail       ?? 'confirmacion_radicado',
        destinatario:    options.to,
        asunto:          options.subject,
        fechaEnvio:      new Date().toISOString(),
        estado:          'simulado',
        messageId,
      },
    };
  }

  async verify(): Promise<boolean> {
    console.log('[MockTransporter] Conexión verificada (modo simulado)');
    return true;
  }
}

/**
 * IMPLEMENTACIÓN 2: NodemailerTransporter
 * Usa Nodemailer con las credenciales de Gmail configuradas
 */
class NodemailerTransporter implements IEmailTransporter {
  private transporter: Transporter;
  private from: string;

  constructor() {
    // Validar variables de entorno
    const required = ['SMTP_HOST', 'SMTP_PORT', 'SMTP_USER', 'SMTP_PASS'] as const;
    for (const key of required) {
      if (!process.env[key]) {
        throw new Error(
          `[EmailService] Falta la variable de entorno: ${key}. ` +
          `Configúrala en .env.local o usa SMTP_MODE=mock para desarrollo.`
        );
      }
    }

    this.from = process.env.SMTP_FROM_EMAIL || process.env.SMTP_USER!;
    const isGmail = process.env.SMTP_HOST?.includes('gmail.com');
    
    console.log(`[EmailService] 🛠️ Inicializando Nodemailer (${isGmail ? 'Servicio: GMAIL' : `Host: ${process.env.SMTP_HOST}`})`);

    const config = isGmail ? {
      service: 'gmail',
      auth: {
        user: process.env.SMTP_USER!,
        pass: process.env.SMTP_PASS!,
      },
    } : {
      host:   process.env.SMTP_HOST!,
      port:   parseInt(process.env.SMTP_PORT!),
      secure: process.env.SMTP_SECURE === 'true',
      auth: {
        user: process.env.SMTP_USER!,
        pass: process.env.SMTP_PASS!,
      },
      tls: {
        rejectUnauthorized: false,
      },
    };

    this.transporter = nodemailer.createTransport(config);
  }

  async send(options: EmailOptions): Promise<EmailSendResult> {
    try {
      const fromName = process.env.SMTP_FROM_NAME || 'Alcaldía de Medellín';
      
      const info = await this.transporter.sendMail({
        from:    `"${fromName}" <${this.from}>`,
        to:      options.toName ? `"${options.toName}" <${extraerEmail(options.to)}>` : extraerEmail(options.to),
        subject: options.subject,
        html:    options.html,
        text:    options.text,
        headers: {
          'X-Mailer':           'CRM-PQRSD-MedellinGovTech/1.0',
          'X-Radicado-System':  'Distrito-CTI-Medellin',
          'X-Ticket-ID':        options.idTicket ?? '',
        },
      });

      console.log(`[EmailService] ✅ Email enviado → ${options.to} | ID: ${info.messageId}`);

      return {
        success:   true,
        messageId: info.messageId,
        simulado:  false,
        registro: {
          idRegistro:    `reg-${Date.now()}`,
          idTicket:       options.idTicket       ?? '',
          numeroRadicado: options.numeroRadicado ?? '',
          tipoEmail:      options.tipoEmail      ?? 'confirmacion_radicado',
          destinatario:   options.to,
          asunto:         options.subject,
          fechaEnvio:     new Date().toISOString(),
          estado:         'enviado',
          messageId:      info.messageId,
        },
      };
    } catch (err) {
      const errorObj = err as { message?: string; code?: string; response?: string };
      const msg = errorObj.message || 'Error SMTP desconocido';
      const code = errorObj.code || 'N/A';
      
      console.error(`[EmailService] ❌ Error SMTP [${code}] → ${msg}`);
      if (errorObj.response) {
        console.error(`[EmailService] ❌ Respuesta Servidor: ${errorObj.response}`);
      }

      return {
        success:  false,
        simulado: false,
        error:    `${msg} (Código: ${code})`,
        registro: {
          idRegistro:    `reg-err-${Date.now()}`,
          idTicket:       options.idTicket       ?? '',
          numeroRadicado: options.numeroRadicado ?? '',
          tipoEmail:      options.tipoEmail      ?? 'confirmacion_radicado',
          destinatario:   options.to,
          asunto:         options.subject,
          fechaEnvio:     new Date().toISOString(),
          estado:         'fallido',
          errorMensaje:   msg,
        },
      };
    }
  }

  async verify(): Promise<boolean> {
    try {
      await this.transporter.verify();
      console.log('[EmailService] ✅ Conexión SMTP verificada correctamente');
      return true;
    } catch (err) {
      console.error('[EmailService] ❌ Verificación SMTP fallida:', err);
      return false;
    }
  }
}

/**
 * FUNCIONES DE ALTO NIVEL PARA NEGOCIO
 */

export async function sendConfirmationEmail(
  emailDestino: string, 
  numeroRadicado: string,
  nombreCiudadano: string = 'Ciudadano(a)',
  contenidoOriginal: string = '',
  idTicket?: string
): Promise<EmailSendResult> {
  const transporter = getEmailTransporter();
  const subject = `Confirmación de Recibido - PQRSD Radicado: ${numeroRadicado}`;
  // Limpiar appUrl de posibles subrutas como /dashboard o slashes finales que rompan el ruteo
  const appUrl = (process.env.NEXT_PUBLIC_APP_URL || 'https://crm-pqrsd.vercel.app')
    .replace(/\/dashboard\/?$/, '') 
    .replace(/\/+$/, '');

  const trackingUrl = idTicket ? `${appUrl}/seguimiento/${idTicket}` : null;
  
  const html = `
    <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #1A2332; max-width: 600px; margin: 0 auto; border: 1px solid #E8ECF2; border-radius: 12px; overflow: hidden;">
      <div style="background-color: #003DA5; padding: 24px; text-align: center;">
        <h1 style="color: #FFFFFF; margin: 0; font-size: 20px; text-transform: uppercase; letter-spacing: 1px;">Alcaldía de Medellín</h1>
      </div>
      <div style="padding: 32px;">
        <h2 style="color: #003DA5; margin-top: 0;">Confirmación de Radicado</h2>
        <p>Estimado(a) <strong>${nombreCiudadano}</strong>,</p>
        <p>Hemos recibido su solicitud de manera exitosa. Se le ha asignado el siguiente número de radicado oficial para realizar su seguimiento:</p>
        
        <div style="background-color: #F4F6F9; border-radius: 8px; padding: 20px; text-align: center; margin: 24px 0; border: 1px dashed #003DA5;">
          <span style="font-family: monospace; font-size: 24px; font-bold; color: #001E4E;">${numeroRadicado}</span>
        </div>

        <div style="margin: 24px 0; padding: 16px; background-color: #F8FAFC; border-left: 4px solid #003DA5; border-radius: 4px;">
          <p style="margin: 0 0 8px 0; font-size: 12px; font-weight: bold; color: #64748B; text-transform: uppercase;">Resumen de su solicitud:</p>
          <p style="margin: 0; font-size: 14px; font-style: italic; color: #334155;">"${contenidoOriginal}"</p>
        </div>

        ${trackingUrl ? `
        <div style="text-align: center; margin: 24px 0;">
          <a href="${trackingUrl}" 
             style="display: inline-block; background-color: #003DA5; color: #FFFFFF; font-weight: bold; font-size: 14px; padding: 14px 32px; border-radius: 8px; text-decoration: none; letter-spacing: 0.5px;">
            📋 Consultar estado de mi solicitud
          </a>
          <p style="font-size: 11px; color: #94A3B8; margin-top: 8px;">
            O copie este enlace: <a href="${trackingUrl}" style="color: #003DA5;">${trackingUrl}</a>
          </p>
        </div>
        ` : ''}
        
        <p style="font-size: 14px; color: #6B7A90; line-height: 1.6;">
          De acuerdo con la Ley 1755 de 2015, daremos respuesta a su PQRSD en un plazo máximo de <strong>15 días hábiles</strong>. Usted podrá consultar el estado de su trámite en cualquier momento con el enlace anterior.
        </p>
        
        <div style="margin-top: 32px; padding-top: 24px; border-top: 1px solid #E8ECF2;">
          <p style="font-size: 12px; color: #B8C2D0; margin: 0;">
            Este es un correo automático, por favor no responda a este mensaje.<br>
            <strong>Distrito Especial de Ciencia, Tecnología e Innovación de Medellín.</strong>
          </p>
        </div>
      </div>
    </div>
  `;

  const text = `
    Alcaldía de Medellín - Confirmación de Radicado
    Estimado(a) ${nombreCiudadano},
    Hemos recibido su solicitud. Su número de radicado es: ${numeroRadicado}.
    Contenido recibido: "${contenidoOriginal}"
    ${trackingUrl ? `Consulte el estado de su solicitud en: ${trackingUrl}` : ''}
    Responderemos en un plazo máximo de 15 días hábiles.
  `;

  return transporter.send({
    to: emailDestino,
    subject,
    html,
    text,
    idTicket,
    numeroRadicado,
    tipoEmail: 'confirmacion_radicado'
  });
}

/**
 * FACTORY + SINGLETON
 * Crea el transporter correcto según SMTP_MODE.
 */
export function createEmailTransporter(): IEmailTransporter {
  const mode = process.env.SMTP_MODE ?? 'mock';
  console.log(`[EmailService] 📧 Modo de envío configurado: ${mode.toUpperCase()}`);
  if (mode === 'live') return new NodemailerTransporter();
  return new MockTransporter();
}

// Singleton — reutiliza la misma instancia entre requests de Next.js
let _instance: IEmailTransporter | null = null;

export function getEmailTransporter(): IEmailTransporter {
  if (!_instance) _instance = createEmailTransporter();
  return _instance;
}
