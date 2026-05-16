const C = {
  azulOscuro:   '#001E4E',
  azulMedio:    '#003DA5',
  azulClaro:    '#0057B8',
  cian:         '#00A3E0',
  dorado:       '#D4A017',
  fondo:        '#F4F6F9',
  blanco:       '#FFFFFF',
  textoPrinc:   '#1A2332',
  textoSecund:  '#3D4A5C',
  textoTert:    '#6B7A90',
  borde:        '#E8ECF2',
  verde:        '#00875A',
  verdeBg:      '#ECFDF5',
  rojo:         '#DC2626',
  rojoBg:       '#FEF2F2',
  doradoBg:     '#FDF3D0',
} as const;

export function generateConfirmacionTemplate(data: {
  nombreCiudadano:      string;
  numeroRadicado:       string;
  tipoSolicitud:        string;
  secretariaNombre:     string;
  fechaRadicacion:      string;
  fechaLimiteRespuesta: string;
}): { subject: string; html: string; text: string } {
  const subject = `[Radicado ${data.numeroRadicado}] Confirmación de recepción — ${data.tipoSolicitud}`;

  const html = `
    <!DOCTYPE html>
    <html lang="es">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>${subject}</title>
    </head>
    <body style="margin: 0; padding: 0; font-family: 'Segoe UI', Arial, sans-serif; background-color: ${C.fondo}; color: ${C.textoPrinc};">
      <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: ${C.fondo}; padding: 20px 0;">
        <tr>
          <td align="center">
            <table border="0" cellpadding="0" cellspacing="0" width="600" style="background-color: ${C.blanco}; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
              <!-- HEADER -->
              <tr>
                <td style="background-color: ${C.azulOscuro}; padding: 24px 32px;">
                  <table border="0" cellpadding="0" cellspacing="0" width="100%">
                    <tr>
                      <td>
                        <div style="background-color: ${C.cian}; color: ${C.azulOscuro}; display: inline-block; padding: 4px 12px; border-radius: 4px; font-size: 10px; font-weight: bold; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 1px;">
                          Distrito Especial de C, T e I
                        </div>
                        <div style="color: ${C.blanco}; font-size: 22px; font-weight: bold; margin: 0;">Alcaldía de Medellín</div>
                        <div style="color: ${C.cian}; font-size: 12px; margin-top: 4px;">Medellín Te Quiere · Atención al Ciudadano</div>
                      </td>
                      <td align="right" valign="middle">
                        <div style="background-color: ${C.verde}; width: 40px; height: 40px; border-radius: 50%; text-align: center; line-height: 40px; color: white; font-size: 20px;">✓</div>
                      </td>
                    </tr>
                  </table>
                </td>
              </tr>

              <!-- BODY -->
              <tr>
                <td style="padding: 32px; background-color: ${C.blanco};">
                  <p style="font-size: 16px; margin: 0 0 16px 0;">Apreciado/a <strong>${data.nombreCiudadano}</strong>:</p>
                  <p style="font-size: 14px; line-height: 1.6; color: ${C.textoSecund}; margin-bottom: 24px;">
                    Hemos recibido correctamente su <strong>${data.tipoSolicitud}</strong> a través de nuestros canales digitales. 
                    A partir de este momento, nuestro equipo técnico comenzará el trámite correspondiente bajo los términos de ley.
                  </p>

                  <div style="background-color: ${C.fondo}; border: 1px solid ${C.azulMedio}; border-radius: 6px; padding: 20px; text-align: center; margin-bottom: 24px;">
                    <div style="font-size: 12px; color: ${C.azulMedio}; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px; font-weight: bold;">Su Número de Radicado Oficial</div>
                    <div style="font-family: 'Courier New', Courier, monospace; font-size: 28px; font-weight: bold; color: ${C.azulOscuro};">${data.numeroRadicado}</div>
                  </div>

                  <table border="0" cellpadding="10" cellspacing="0" width="100%" style="border-collapse: collapse; margin-bottom: 24px; font-size: 13px;">
                    <tr style="border-bottom: 1px solid ${C.borde};">
                      <td style="color: ${C.textoTert}; width: 40%;">Dependencia responsable:</td>
                      <td style="font-weight: bold; color: ${C.textoPrinc};">${data.secretariaNombre}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid ${C.borde};">
                      <td style="color: ${C.textoTert};">Fecha de radicación:</td>
                      <td style="color: ${C.textoPrinc};">${data.fechaRadicacion}</td>
                    </tr>
                    <tr>
                      <td style="color: ${C.textoTert};">Fecha límite respuesta:</td>
                      <td style="font-weight: bold; color: ${C.rojo};">${data.fechaLimiteRespuesta} <span style="font-size: 11px;">(15 días hábiles)</span></td>
                    </tr>
                  </table>

                  <div style="border-left: 4px solid ${C.azulMedio}; padding-left: 16px; margin-bottom: 24px;">
                    <p style="font-size: 12px; line-height: 1.5; color: ${C.textoTert}; font-style: italic; margin: 0;">
                      De acuerdo con la <strong>Ley 1755 de 2015</strong>, el Distrito cuenta con un plazo máximo de quince (15) días hábiles 
                      para dar respuesta de fondo a su solicitud de petición.
                    </p>
                  </div>

                  <p style="font-size: 13px; color: ${C.textoPrinc}; margin: 0 0 12px 0;">Puede hacer seguimiento a su trámite a través de:</p>
                  <ul style="font-size: 13px; color: ${C.textoSecund}; line-height: 1.8; margin: 0 0 24px 0; padding-left: 20px;">
                    <li><strong>Web:</strong> <a href="https://www.medellin.gov.co/es/pqrsd/" style="color: ${C.azulClaro}; text-decoration: none;">medellin.gov.co/es/pqrsd</a></li>
                    <li><strong>Línea Única:</strong> 604 44 44 144</li>
                    <li><strong>WhatsApp Flor:</strong> 301 604 44 44</li>
                  </ul>

                  <p style="font-size: 13px; margin: 32px 0 0 0; color: ${C.textoTert}; line-height: 1.4;">
                    Cordialmente,<br>
                    <strong>${data.secretariaNombre}</strong><br>
                    Alcaldía de Medellín<br>
                    Distrito de Ciencia, Tecnología e Innovación
                  </p>
                </td>
              </tr>

              <!-- FOOTER -->
              <tr>
                <td style="background-color: ${C.azulOscuro}; padding: 24px 32px; text-align: center;">
                  <p style="font-size: 11px; color: #8B949E; margin: 0 0 8px 0;">
                    Este es un mensaje generado automáticamente. Por favor no responda a este correo.
                  </p>
                  <p style="font-size: 11px; color: #8B949E; margin: 0;">
                    Carrera 50 Nº 52-25 · Centro Administrativo Municipal CAM · Medellín, Colombia<br>
                    <a href="https://www.medellin.gov.co" style="color: ${C.cian}; text-decoration: none;">www.medellin.gov.co</a>
                  </p>
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>
    </body>
    </html>
  `;

  const text = `
DISTRITO ESPECIAL DE C, T e I
ALCALDÍA DE MEDELLÍN
Confirmación de Recepción - ${data.tipoSolicitud}

Apreciado/a ${data.nombreCiudadano}:

Hemos recibido correctamente su ${data.tipoSolicitud} a través de nuestros canales digitales.

NÚMERO DE RADICADO OFICIAL: ${data.numeroRadicado}

DETALLES DEL TRÁMITE:
--------------------------------------------------
Dependencia: ${data.secretariaNombre}
Fecha radicación: ${data.fechaRadicacion}
Fecha límite: ${data.fechaLimiteRespuesta} (15 días hábiles)
--------------------------------------------------

De acuerdo con la Ley 1755 de 2015, el Distrito cuenta con un plazo máximo de quince (15) días hábiles para dar respuesta de fondo a su solicitud.

Seguimiento:
- Web: www.medellin.gov.co/es/pqrsd
- Línea Única: 604 44 44 144
- WhatsApp Flor: 301 604 44 44

Cordialmente,
${data.secretariaNombre}
Alcaldía de Medellín
  `.trim();

  return { subject, html, text };
}

export function generateRespuestaTemplate(data: {
  nombreCiudadano:  string;
  numeroRadicado:   string;
  tipoSolicitud:    string;
  secretariaNombre: string;
  nombreFuncionario: string;
  cargoFuncionario:  string;
  fechaRespuesta:   string;
  textoRespuesta:   string;
  trackingUrl?:     string | null;
}): { subject: string; html: string; text: string } {
  const subject = `[Radicado ${data.numeroRadicado}] Respuesta oficial a su ${data.tipoSolicitud}`;

  const html = `
    <!DOCTYPE html>
    <html lang="es">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>${subject}</title>
    </head>
    <body style="margin: 0; padding: 0; font-family: 'Segoe UI', Arial, sans-serif; background-color: ${C.fondo}; color: ${C.textoPrinc};">
      <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: ${C.fondo}; padding: 20px 0;">
        <tr>
          <td align="center">
            <table border="0" cellpadding="0" cellspacing="0" width="600" style="background-color: ${C.blanco}; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
              <!-- HEADER -->
              <tr>
                <td style="background-color: ${C.azulOscuro}; padding: 24px 32px;">
                  <table border="0" cellpadding="0" cellspacing="0" width="100%">
                    <tr>
                      <td>
                        <div style="background-color: ${C.cian}; color: ${C.azulOscuro}; display: inline-block; padding: 4px 12px; border-radius: 4px; font-size: 10px; font-weight: bold; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 1px;">
                          Distrito Especial de C, T e I
                        </div>
                        <div style="color: ${C.blanco}; font-size: 22px; font-weight: bold; margin: 0;">Alcaldía de Medellín</div>
                        <div style="color: ${C.cian}; font-size: 12px; margin-top: 4px;">Notificación de Respuesta Oficial</div>
                      </td>
                      <td align="right" valign="middle">
                        <div style="color: white; font-size: 32px;">✉️</div>
                      </td>
                    </tr>
                  </table>
                </td>
              </tr>

              <!-- STATUS BADGE -->
              <tr>
                <td style="padding: 16px 32px 0 32px;">
                  <div style="background-color: ${C.verdeBg}; color: ${C.verde}; border: 1px solid ${C.verde}; padding: 6px 16px; border-radius: 20px; font-size: 12px; font-weight: bold; display: inline-block;">
                    ✅ Solicitud Atendida y Resuelta
                  </div>
                </td>
              </tr>

              <!-- BODY -->
              <tr>
                <td style="padding: 24px 32px 32px 32px; background-color: ${C.blanco};">
                  <p style="font-size: 16px; margin: 0 0 16px 0;">Respetado/a ciudadano/a <strong>${data.nombreCiudadano}</strong>:</p>
                  <p style="font-size: 14px; line-height: 1.6; color: ${C.textoSecund}; margin-bottom: 24px;">
                    En cumplimiento de lo dispuesto por la Ley 1755 de 2015, nos permitimos notificarle la respuesta oficial 
                    a su solicitud radicada bajo el número <strong>${data.numeroRadicado}</strong>.
                  </p>

                  <!-- CARTA DE RESPUESTA -->
                  <div style="background-color: ${C.blanco}; border: 1px solid ${C.borde}; border-radius: 6px; padding: 24px; margin-bottom: 24px;">
                    <div style="font-size: 14px; line-height: 1.8; color: ${C.textoPrinc}; white-space: pre-wrap;">${data.textoRespuesta}</div>
                  </div>

                  ${data.trackingUrl ? `
                  <div style="text-align: center; margin: 24px 0;">
                    <a href="${data.trackingUrl}" 
                       style="display: inline-block; background-color: ${C.azulMedio}; color: ${C.blanco}; font-weight: bold; font-size: 14px; padding: 14px 32px; border-radius: 8px; text-decoration: none; letter-spacing: 0.5px;">
                      📋 Ver detalles del trámite
                    </a>
                  </div>
                  ` : ''}

                  <table border="0" cellpadding="8" cellspacing="0" width="100%" style="border-collapse: collapse; margin-bottom: 24px; font-size: 12px; background-color: ${C.fondo}; border-radius: 6px;">
                    <tr>
                      <td style="color: ${C.textoTert}; border-bottom: 1px solid ${C.blanco};">Radicado:</td>
                      <td style="font-weight: bold; border-bottom: 1px solid ${C.blanco};">${data.numeroRadicado}</td>
                    </tr>
                    <tr>
                      <td style="color: ${C.textoTert}; border-bottom: 1px solid ${C.blanco};">Tipo:</td>
                      <td style="border-bottom: 1px solid ${C.blanco};">${data.tipoSolicitud}</td>
                    </tr>
                    <tr>
                      <td style="color: ${C.textoTert}; border-bottom: 1px solid ${C.blanco};">Dependencia:</td>
                      <td style="border-bottom: 1px solid ${C.blanco};">${data.secretariaNombre}</td>
                    </tr>
                    <tr>
                      <td style="color: ${C.textoTert};">Fecha de respuesta:</td>
                      <td>${data.fechaRespuesta}</td>
                    </tr>
                  </table>

                  <!-- FIRMA FUNCIONARIO -->
                  <div style="border-top: 1px solid ${C.borde}; padding-top: 24px; margin-top: 32px;">
                    <p style="margin: 0; font-size: 15px; font-weight: bold; color: ${C.textoPrinc};">${data.nombreFuncionario}</p>
                    <p style="margin: 4px 0 0 0; font-size: 13px; color: ${C.textoSecund};">${data.cargoFuncionario}</p>
                    <p style="margin: 4px 0 0 0; font-size: 13px; color: ${C.azulClaro}; font-weight: bold;">
                      ${data.secretariaNombre} · Alcaldía de Medellín
                    </p>
                    <p style="margin: 2px 0 0 0; font-size: 11px; color: ${C.textoTert};">
                      Distrito Especial de Ciencia, Tecnología e Innovación
                    </p>
                  </div>

                  <!-- AVISO DORADO -->
                  <div style="background-color: ${C.doradoBg}; border-left: 4px solid ${C.dorado}; padding: 16px; margin-top: 32px; border-radius: 0 4px 4px 0;">
                    <p style="font-size: 12px; line-height: 1.5; color: ${C.textoPrinc}; margin: 0;">
                      <strong>Nota Legal:</strong> Este correo constituye la respuesta oficial de la Alcaldía de Medellín 
                      a su solicitud radicada. Puede conservar este mensaje como constancia de la atención brindada 
                      dentro de los términos legales.
                    </p>
                  </div>
                </td>
              </tr>

              <!-- FOOTER -->
              <tr>
                <td style="background-color: ${C.azulOscuro}; padding: 24px 32px; text-align: center;">
                  <p style="font-size: 11px; color: #8B949E; margin: 0 0 8px 0;">
                    Este es un mensaje generado automáticamente. Por favor no responda a este correo.
                  </p>
                  <p style="font-size: 11px; color: #8B949E; margin: 0;">
                    Carrera 50 Nº 52-25 · Centro Administrativo Municipal CAM · Medellín, Colombia<br>
                    <a href="https://www.medellin.gov.co" style="color: ${C.cian}; text-decoration: none;">www.medellin.gov.co</a>
                  </p>
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>
    </body>
    </html>
  `;

  const text = `
DISTRITO ESPECIAL DE C, T e I
ALCALDÍA DE MEDELLÍN
Respuesta Oficial a su Solicitud - ${data.numeroRadicado}

Respetado/a ciudadano/a ${data.nombreCiudadano}:

En cumplimiento de la Ley 1755 de 2015, le notificamos la respuesta oficial a su ${data.tipoSolicitud}.

TEXTO DE LA RESPUESTA:
--------------------------------------------------
${data.textoRespuesta}
--------------------------------------------------

DETALLES DEL RADICADO:
- Número: ${data.numeroRadicado}
- Dependencia: ${data.secretariaNombre}
- Fecha de Respuesta: ${data.fechaRespuesta}

Atentamente,

${data.nombreFuncionario}
${data.cargoFuncionario}
${data.secretariaNombre}
Alcaldía de Medellín
Distrito de Ciencia, Tecnología e Innovación

AVISO LEGAL: Este correo constituye la respuesta oficial de la Alcaldía de Medellín a su solicitud.
  `.trim();

  return { subject, html, text };
}
