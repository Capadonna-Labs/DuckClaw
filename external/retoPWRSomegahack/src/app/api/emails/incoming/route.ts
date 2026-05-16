import { NextRequest, NextResponse } from 'next/server';
import { generarNumeroRadicado } from '@/lib/radicado';
import { procesarCorreoConIA } from '@/services/iaTemplateService';
import { sendConfirmationEmail } from '@/services/emailService';
import { MEMORIA_HILOS_MOCK } from '@/services/mockData';
import { Ticket } from '@/types';
import { query, ensureSchema } from '@/lib/motherduck';
import { extraerEmail } from '@/lib/utils';

/**
 * API ENDPOINT: Ingesta de Correos Electrónicos
 * Sistema con Memoria de Continuidad: Detecta si es una respuesta a una solicitud anterior.
 * 
 * Persiste tickets tanto en MOCK (memoria) como en DuckDB local (pqrsd_crm.tickets).
 */
export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { remitente: remitenteRaw, nombre, asunto, cuerpo } = body;
    const remitente = extraerEmail(remitenteRaw || '');

    // --- FILTRO DE SEGURIDAD Y RELEVANCIA ---
    const dominiosBloqueados = ['instagram.com', 'facebookmail.com', 'twitter.com', 'linkedin.com', 'pinterest.com'];
    const keywordsBloqueadas = ['noreply', 'no-reply', 'notification', 'alert', 'newsletter', 'donotreply'];
    
    const esIrrelevante = 
      dominiosBloqueados.some(dom => remitente.toLowerCase().endsWith(dom)) ||
      keywordsBloqueadas.some(key => remitente.toLowerCase().includes(key)) ||
      (asunto && keywordsBloqueadas.some(key => asunto.toLowerCase().includes(key)));

    if (esIrrelevante) {
      console.log(`[Filtro-Spam] 🚫 Correo ignorado de: ${remitente}`);
      return NextResponse.json({ 
        success: false, 
        error: 'El remitente o contenido no parece ser una solicitud ciudadana válida (posible sistema automatizado).' 
      }, { status: 200 }); // Status 200 para que el webhook no reintente
    }

    if (!remitente || !cuerpo) {
      return NextResponse.json({ error: 'Faltan campos obligatorios' }, { status: 400 });
    }

    // 1. BUSCAR CONTINUIDAD (¿El ciudadano está respondiendo a una petición de datos anterior?)
    const contextoAnterior = MEMORIA_HILOS_MOCK[remitente];
    if (contextoAnterior) {
      console.log(`[IA-Continuidad] 🧵 Detectado hilo anterior para: ${remitente}`);
    }

    // 2. ANÁLISIS CON IA (Enviando contexto si existe)
    const analisis = await procesarCorreoConIA(
      cuerpo, 
      asunto || '', 
      nombre || 'Ciudadano', 
      contextoAnterior
    );

    // ESCENARIO A: BASURA
    if (analisis.esBasura) {
      return NextResponse.json({ success: false, error: 'Contenido no válido', esBasura: true });
    }

    // 2. GENERACIÓN DE RADICADO (Se genera desde el inicio para dar seguridad al ciudadano)
    const idSecretaria = 'sec-salud'; // Default para demo
    const numeroRadicadoReal = generarNumeroRadicado(idSecretaria);
    const idTicket = `tk-${Date.now()}`;

    const nombreParaTicket = (analisis.nombreExtraido && analisis.nombreExtraido !== 'No encontrado') 
      ? analisis.nombreExtraido 
      : 'Ciudadano por identificar';

    try {
      await ensureSchema();
      console.log('[DuckDB] Conexión validada para ingesta');
    } catch (dbErr) {
      console.error('[DuckDB] Error de conexión:', dbErr);
    }

    // ESCENARIO B: FALTAN DATOS (Nombre/Cédula)
    if (analisis.faltanDatos) {
      console.log(`[IA-Ingesta] ⚠️ Faltan datos: ${analisis.datosFaltantes.join(', ')}`);
      
      // 1. Guardar en memoria para mantener continuidad
      MEMORIA_HILOS_MOCK[remitente] = {
        asunto: asunto || 'Sin asunto',
        cuerpoOriginal: cuerpo,
        nombre: nombreParaTicket
      };

      try {
        await query(
          `INSERT INTO pqrsd_crm.tickets (
            id_ticket, numero_radicado, id_secretaria, nombre_ciudadano,
            email_ciudadano, documento_ciudadano, telefono_ciudadano, tipo_solicitud, asunto, contenido_raw,
            resumen_ia, respuesta_sugerida, estado, canal_origen,
            fecha_creacion, fecha_limite, fecha_actualizacion
          ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)`,
          [
            idTicket, numeroRadicadoReal, idSecretaria, nombreParaTicket, 
            remitente, null, null, analisis.categoriaSugerida, 
            asunto || 'Solicitud Incompleta', cuerpo, null, 
            analisis.respuestaGenerada, 'Pendiente', 'Email',
            new Date().toISOString(), new Date(Date.now() + 15 * 24 * 60 * 60 * 1000).toISOString()
          ]
        );
      } catch (dbErr) {
        console.error('[DuckDB] Error al persistir ticket incompleto:', dbErr);
      }

      // Enviamos correo pidiendo los datos
      await sendConfirmationEmail(
        remitente, 
        numeroRadicadoReal, 
        nombreParaTicket, 
        `${analisis.respuestaGenerada}\n\n---\nTU MENSAJE RECIBIDO:\n${cuerpo}`,
        idTicket
      );

      return NextResponse.json({ 
        success: true, 
        mensaje: 'Radicado generado (Pendiente Datos)',
        numeroRadicado: numeroRadicadoReal,
        faltanDatos: true 
      });
    }

    // ESCENARIO C: ÉXITO (Datos completos)
    const contenidoFinal = contextoAnterior 
      ? `--- SOLICITUD INICIAL ---\n${contextoAnterior.cuerpoOriginal}\n\n--- DATOS COMPLETADOS ---\n${cuerpo}`
      : cuerpo;

    const nuevoTicket: Ticket = {
      idTicket,
      numeroRadicado: numeroRadicadoReal,
      idSecretaria,
      nombreCiudadano: nombreParaTicket,
      emailCiudadano: remitente,
      tipoSolicitud: analisis.categoriaSugerida,
      asunto: asunto || contextoAnterior?.asunto || 'Sin asunto',
      contenidoRaw: contenidoFinal,
      resumenIa: null,
      respuestaSugerida: analisis.respuestaGenerada,
      estado: 'Pendiente',
      fechaCreacion: new Date().toISOString(),
      fechaLimite: new Date(Date.now() + 15 * 24 * 60 * 60 * 1000).toISOString(),
      canalOrigen: 'Email',
    };

    try {
      await ensureSchema();

      const duplicateCheck = await query<{ cnt: bigint | number }>(
        `SELECT COUNT(*)::BIGINT AS cnt FROM pqrsd_crm.tickets 
         WHERE email_ciudadano = ? 
         AND asunto = ? 
         AND fecha_creacion > (CURRENT_TIMESTAMP - INTERVAL 2 MINUTES)`,
        [nuevoTicket.emailCiudadano, nuevoTicket.asunto]
      );
      
      const count = Number(duplicateCheck[0]?.cnt || 0);
      if (count > 0) {
        console.log(`[DuckDB] Ticket duplicado detectado para ${remitente}, ignorando.`);
        return NextResponse.json({ success: true, duplicated: true, message: 'Ticket ya procesado recientemente' });
      }

      await query(
        `INSERT INTO pqrsd_crm.tickets (
          id_ticket, numero_radicado, id_secretaria, nombre_ciudadano,
          email_ciudadano, documento_ciudadano, telefono_ciudadano, tipo_solicitud, asunto, contenido_raw,
          resumen_ia, respuesta_sugerida, estado, canal_origen,
          fecha_creacion, fecha_limite, fecha_actualizacion
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)`,
        [
          nuevoTicket.idTicket, nuevoTicket.numeroRadicado, nuevoTicket.idSecretaria,
          nuevoTicket.nombreCiudadano, nuevoTicket.emailCiudadano, null, null, nuevoTicket.tipoSolicitud,
          nuevoTicket.asunto, nuevoTicket.contenidoRaw, nuevoTicket.resumenIa,
          nuevoTicket.respuestaSugerida, nuevoTicket.estado, nuevoTicket.canalOrigen,
          nuevoTicket.fechaCreacion, nuevoTicket.fechaLimite,
        ]
      );
      console.log(`[DuckDB] Ticket ${idTicket} persistido`);
    } catch (dbErr) {
      console.error('[DuckDB] No se pudo persistir en DB (el ticket existe en mock):', dbErr);
    }
    
    // LIMPIAR MEMORIA (La conversación ha concluido con un radicado)
    delete MEMORIA_HILOS_MOCK[remitente];
    console.log(`[IA-Continuidad] ✅ Hilo cerrado y ticket creado: ${numeroRadicadoReal}`);

    // Enviar respuesta humana final con link de seguimiento
    await sendConfirmationEmail(
      remitente, 
      numeroRadicadoReal, 
      nombreParaTicket, 
      analisis.respuestaGenerada,
      idTicket  // ← Para generar el link de seguimiento
    );

    return NextResponse.json({ success: true, numeroRadicado: numeroRadicadoReal, idTicket });

  } catch (error) {
    console.error('[Ingesta-Error]', error);
    return NextResponse.json({ 
      error: 'Error interno al procesar el correo',
      details: error instanceof Error ? error.message : 'Unknown'
    }, { status: 500 });
  }
}
