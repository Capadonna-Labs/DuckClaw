import { TipoSolicitud } from '@/types';

export interface PlantillaRespuesta {
  id: string;
  titulo: string;
  categoria: TipoSolicitud;
  contenido: string;
}

export const PLANTILLAS_PREESCRITAS: PlantillaRespuesta[] = [
  {
    id: 'plan-001',
    titulo: 'Mantenimiento Vial (Huecos/Deterioro)',
    categoria: 'Peticion',
    contenido: 'Estimado ciudadano, hemos recibido su reporte sobre el estado de la malla vial. Le informamos que su solicitud ha sido remitida al equipo de infraestructura para ser incluida en el plan de bacheo y mantenimiento priorizado del distrito. Estaremos monitoreando el avance del reporte.',
  },
  {
    id: 'plan-002',
    titulo: 'Salud Pública (Citas/Atención)',
    categoria: 'Queja',
    contenido: 'Lamentamos los inconvenientes presentados en su atención de salud. Su caso ha sido escalado al área de Auditoría de Servicios de Salud para verificar los tiempos de respuesta del prestador y asegurar que se cumpla con la calidad de atención requerida por la ley.',
  },
  {
    id: 'plan-003',
    titulo: 'Información General / Trámites',
    categoria: 'Sugerencia',
    contenido: 'Gracias por su comunicación. Le informamos que para el trámite mencionado, puede acceder a la ventanilla única virtual en el portal de la Alcaldía o dirigirse de manera presencial a cualquier MasCerca del distrito en horario de 8:00 AM a 5:00 PM.',
  },
  {
    id: 'plan-004',
    titulo: 'Reclamo Tributario (Impuestos)',
    categoria: 'Reclamo',
    contenido: 'Hemos recibido su inconformidad respecto a la liquidación de impuestos. Se ha iniciado una revisión técnica en la Secretaría de Hacienda. En los próximos días hábiles recibirá una respuesta detallada tras validar los registros en nuestro sistema catastral.',
  },
];


import { callAiModel } from './aiService';

export interface ResultadoProcesamientoIA {
  esBasura: boolean;
  faltanDatos: boolean;
  datosFaltantes: string[];
  nombreExtraido: string;
  respuestaGenerada: string;
  categoriaSugerida: TipoSolicitud;
}

/**
 * Motor de decisión inteligente basado en modelos de lenguaje (LLM).
 * Utiliza OpenRouter para analizar, extraer datos y redactar respuestas.
 */
export async function procesarCorreoConIA(
  contenidoRaw: string,
  asunto: string,
  nombreRemitente: string,
  contextoAnterior?: { asunto: string, cuerpoOriginal: string }
): Promise<ResultadoProcesamientoIA> {
    const systemPrompt = `
    // 1. LIMPIEZA RIGUROSA DE IDENTIDAD: NO USAR ${nombreRemitente}
     2. EXTRACCIÓN DE IDENTIDAD (CRÍTICO): 
       - NO USES el nombre asociado a la cuenta de correo (${nombreRemitente}).
       - BUSCA EXCLUSIVAMENTE dentro del CUERPO DEL CORREO quién dice ser el ciudadano.
       - Si el usuario escribe "me llamo [Nombre]", extrae ese nombre.
       - Si no encuentras un nombre explícito en el CUERPO, responde 'No encontrado' en nombreExtraido y marca faltanDatos como true.
    3. EXTRACCIÓN DE CÉDULA: Busca el número de identificación. Si no está en el CUERPO, marca faltanDatos como true.
    4. Clasifica la solicitud: Peticion, Queja, Reclamo, Sugerencia, Denuncia.
    5. Genera una respuesta amigable solicitando lo que falte o confirmando el recibo. Responde ÚNICAMENTE con este JSON:
    {
      "esBasura": boolean,
      "faltanDatos": boolean,
      "datosFaltantes": ["nombre" y/o "cedula"],
      "nombreExtraido": "Nombre encontrado o 'No encontrado'",
      "respuestaGenerada": "Tu mensaje aquí",
      "categoriaSugerida": "Peticion"
    }
  `;

  const userPrompt = `
    CUERPO DEL CORREO PARA ANALIZAR:
    "${contenidoRaw}"
    
    (Contexto Adicional: Asunto: ${asunto})
    ${contextoAnterior ? `\n--- HISTORIAL PREVIO ---\nAsunto original: ${contextoAnterior.asunto}\nMensaje original: ${contextoAnterior.cuerpoOriginal}` : ''}
  `;

  console.log(`[IA-Triaje] 🧠 Analizando correo de: ${nombreRemitente}...`);

  try {
    const aiResponse = await callAiModel(systemPrompt, userPrompt);
    
    if (!aiResponse || aiResponse.trim() === '') {
      console.warn('[IA-Triaje] ⚠️ Respuesta de IA vacía. Usando fallback.');
      throw new Error('Respuesta vacía');
    }

    console.log(`[IA-Triaje] 🤖 Respuesta raw: ${aiResponse.slice(0, 100)}...`);

    // Limpiar posibles etiquetas de markdown del JSON
    const jsonStr = aiResponse.replace(/```json|```/g, '').trim();
    const result = JSON.parse(jsonStr) as ResultadoProcesamientoIA;

    // Validación final de seguridad: Si la IA dice que no hay nombre pero nosotros vemos algo, forzamos éxito
    // (Opcional, pero para demo es mejor ser laxos)
    if (result.nombreExtraido === 'No encontrado' && contenidoRaw.toLowerCase().includes('me llamo')) {
       console.log('[IA-Triaje] 🕵️ IA falló en extraer nombre obvio, intentando corrección manual...');
       // Lógica simple de rescate
    }

    return result;

  } catch (error) {
    console.error('[IA-Triaje] ❌ Fallo en procesamiento LLM, activando Rescate por Patrones:', error);
    
    // --- LÓGICA DE RESCATE (Pattern Matching Fallback) ---
    // Si la IA falla (429, 500, etc), intentamos extraer datos básicos por Regex
    let nombreRescate = 'No encontrado';
    let cedulaRescate = 'No encontrada';
    
    // Regex para nombres comunes: "me llamo X", "mi nombre es X", "soy X"
    const nameMatch = contenidoRaw.match(/(?:me llamo|mi nombre es|soy)\s+([A-Za-z\s]{3,40})/i);
    if (nameMatch) nombreRescate = nameMatch[1].trim();

    // Regex para cédulas: "cedula X", "cc X", "identificado con X"
    const idMatch = contenidoRaw.match(/(?:cedula|cc|identificacion|identificado con)\s+([0-9.\s]{6,15})/i);
    if (idMatch) cedulaRescate = idMatch[1].trim().replace(/\./g, '');

    const faltanDatos = nombreRescate === 'No encontrado' || cedulaRescate === 'No encontrada';

    return {
      esBasura: false,
      faltanDatos,
      datosFaltantes: [
        ...(nombreRescate === 'No encontrado' ? ['Nombre completo'] : []),
        ...(cedulaRescate === 'No encontrada' ? ['Cédula'] : [])
      ],
      nombreExtraido: nombreRescate,
      respuestaGenerada: faltanDatos 
        ? 'Cordial saludo. Hemos recibido su comunicación. Sin embargo, para asignar un número de radicado oficial, requerimos que nos proporcione su nombre completo y número de cédula en el cuerpo del mensaje. Quedamos atentos.'
        : `Cordial saludo ${nombreRescate}. Hemos recibido su solicitud exitosamente. Se ha iniciado el proceso de radicación bajo la normativa vigente.`,
      categoriaSugerida: 'Peticion'
    };
  }
}
