import { NextRequest, NextResponse } from 'next/server';
import {
  INVALID_INSTRUCCION_FUNCIONARIO_TEXT,
  validateInstruccionFuncionario,
} from '@/lib/ia/validate-instruccion-funcionario';

interface RegenerarRequestBody {
  contenidoRaw: string;
  resumenIa: string | null;
  respuestaActual: string;
  instruccionFuncionario: string;
  secretariaNombre: string;
  tipoSolicitud: string;
  idTicket: string;
  duckclawUserId: string;
  duckclawUsername: string;
}

function extractCrmOfficialPqrsText(raw: string): string {
  let t = (raw || '').trim();
  if (!t) return t;
  t = t.replace(/^(?:PQRSD-Assistant|[\w][\w\s-]*)\s+\d+\s*[\r\n]+/im, '');
  const startM = /\bRESPUESTA OFICIAL\b/i.exec(t);
  if (startM && typeof startM.index === 'number') {
    t = t.slice(startM.index);
  }
  t = t.replace(/^\s*RESPUESTA OFICIAL[^\n]*\n+/i, '');
  t = t.replace(
    /^(?:Radicado\s*:[^\n]*\n+|Fecha\s*:[^\n]*\n+|Asunto\s*:[^\n]*\n+)+/i,
    ''
  );
  t = t.replace(/^\s*\n+/, '');
  const caractHr = /\n---\s*\n\s*Características de esta redacción/im.exec(t);
  if (caractHr) {
    t = t.slice(0, caractHr.index).trim();
  } else {
    const caract = /\nCaracterísticas de esta redacción\s*:/im.exec(t);
    if (caract) {
      t = t.slice(0, caract.index).trim();
    }
  }
  t = t.replace(/\n---\s*$/m, '').trim();
  return t;
}

function buildCrmUserMessage(body: RegenerarRequestBody): string {
  return [
    '[Modo: redacción de respuesta institucional CRM para funcionario público]',
    'Ayuda a redactar o ajustar la comunicación oficial de respuesta al ciudadano (PQRSD), en español de Colombia.',
    `Secretaría: ${body.secretariaNombre}`,
    `Tipo de solicitud: ${body.tipoSolicitud}`,
    '',
    '--- Contenido de la solicitud del ciudadano ---',
    body.contenidoRaw,
    body.resumenIa ? `\nResumen:\n${body.resumenIa}` : '',
    body.respuestaActual ? `\nBorrador actual:\n${body.respuestaActual}` : '',
    '',
    '--- Instrucción del funcionario ---',
    body.instruccionFuncionario,
    '',
    'Entrega el texto de la carta o respuesta formal. Tono institucional, uso de "Usted".',
    'Encabezado sugerido: "Respetado/a ciudadano/a:". Cierra mencionando la dependencia cuando aplique.',
    '',
    'Salida: empieza con el saludo al ciudadano ("Respetado/a ciudadano/a:"). Sin línea de título "RESPUESTA OFICIAL - …", sin bloque Radicado:/Fecha:/Asunto: salvo que el funcionario lo pida. Sin párrafos introductorios del asistente. Sin sección "Características de esta redacción" ni listas meta al final.',
  ]
    .filter(Boolean)
    .join('\n');
}

/** Llamada directa a OpenRouter cuando el gateway no está disponible */
async function callOpenRouterDirect(prompt: string): Promise<string> {
  const apiKey = process.env.OPENROUTER_API_KEY;
  const model = process.env.NEXT_PUBLIC_OPENROUTER_MODEL || 'arcee-ai/trinity-large-preview:free';

  if (!apiKey) {
    throw new Error('OPENROUTER_API_KEY no configurada');
  }

  const res = await fetch('https://openrouter.ai/api/v1/chat/completions', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${apiKey}`,
      'HTTP-Referer': process.env.NEXT_PUBLIC_APP_URL || 'http://localhost:3000',
      'X-Title': 'CRM PQRSD Medellín',
    },
    body: JSON.stringify({
      model,
      messages: [
        { role: 'system', content: 'Eres un asistente de la Alcaldía de Medellín especializado en PQRSD. Redacta respuestas oficiales en español colombiano con tono institucional.' },
        { role: 'user', content: prompt },
      ],
      max_tokens: 1500,
      temperature: 0.4,
    }),
  });

  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`OpenRouter ${res.status}: ${errText.slice(0, 200)}`);
  }

  const data = await res.json() as { choices?: { message?: { content?: string } }[] };
  return data.choices?.[0]?.message?.content?.trim() || '';
}

/** Intenta gateway DuckClaw; si falla, usa OpenRouter directo */
async function tryGateway(body: RegenerarRequestBody): Promise<{ text: string; source: string }> {
  const { gatewayBaseUrl, postPqrsAssistantChat, crmGatewayUserId, responseTextFromGatewayPayload } =
    await import('@/lib/duckclaw-gateway');
  const gatewayUrl = gatewayBaseUrl();

  if (gatewayUrl) {
    try {

      const chatRequest = {
        message: buildCrmUserMessage(body),
        chat_id: `crm-ticket-${body.idTicket}`,
        user_id: crmGatewayUserId(body.duckclawUserId ?? ''),
        username: (body.duckclawUsername || 'Usuario').trim() || 'Usuario',
        chat_type: 'private',
        tenant_id: 'PQRS',
        stream: false,
      };

      const { ok, payload } = await postPqrsAssistantChat(gatewayUrl, chatRequest);

      if (ok) {
        const text = responseTextFromGatewayPayload(payload);
        if (text.trim()) {
          return { text: extractCrmOfficialPqrsText(text), source: 'gateway' };
        }
      }
    } catch (e) {
      console.warn('[REGENERAR] Gateway no disponible, usando OpenRouter directo:', e instanceof Error ? e.message : e);
    }
  }

  // Fallback: OpenRouter directo
  const prompt = buildCrmUserMessage(body);
  const text = await callOpenRouterDirect(prompt);
  return { text: extractCrmOfficialPqrsText(text), source: 'openrouter' };
}

export async function POST(request: NextRequest) {
  try {
    const body = (await request.json()) as RegenerarRequestBody;

    if (!body.contenidoRaw || !body.instruccionFuncionario || !body.secretariaNombre) {
      return NextResponse.json({ error: 'Faltan campos requeridos' }, { status: 400 });
    }

    const v = validateInstruccionFuncionario(body.instruccionFuncionario);
    if (!v.ok) {
      return NextResponse.json({
        text: INVALID_INSTRUCCION_FUNCIONARIO_TEXT,
        invalid_request: true,
        elapsed_ms: 0,
        usage_tokens: { total_tokens: 0, input_tokens: 0, output_tokens: 0 },
      });
    }

    const { text, source } = await tryGateway(body);

    if (!text.trim()) {
      return NextResponse.json({ error: 'Respuesta vacía del modelo' }, { status: 502 });
    }

    return NextResponse.json({ text, source });
  } catch (err: unknown) {
    console.error('[IA_REGENERAR]:', err);
    const message = err instanceof Error ? err.message : 'Error desconocido';
    return NextResponse.json({ error: 'Error del servidor', detail: message }, { status: 500 });
  }
}
