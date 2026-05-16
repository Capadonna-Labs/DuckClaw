import { NextRequest, NextResponse } from 'next/server';

interface ResumenEjecutivoBody {
  contenidoRaw: string;
  tipoSolicitud: string;
  secretariaNombre: string;
  idTicket: string;
  duckclawUserId: string;
  duckclawUsername: string;
}

/** Quita prefijos tipo etiqueta de subagente al inicio del resumen. */
function stripExecutiveSummaryNoise(raw: string): string {
  let t = (raw || '').trim();
  if (!t) return t;
  t = t.replace(/^(?:PQRSD-Assistant|[\w][\w\s-]*)\s+\d+\s*[\r\n]+/im, '');
  t = t.replace(/^\s*#{1,6}\s*[^\n]+\n+/m, '');
  return t.trim();
}

function buildResumenPrompt(body: ResumenEjecutivoBody): string {
  return [
    '[Modo: resumen ejecutivo CRM GovTech para funcionario público — solo lectura]',
    'Produce un resumen ejecutivo en español (Colombia), 2 a 4 oraciones como máximo.',
    'Audiencia: funcionario que gestiona PQRSD. Tono neutro e institucional.',
    `Secretaría: ${body.secretariaNombre}`,
    `Tipo de solicitud: ${body.tipoSolicitud}`,
    '',
    '--- Texto de la solicitud del ciudadano ---',
    body.contenidoRaw,
    '',
    'Restricciones:',
    '- No redactes carta de respuesta al ciudadano ni uses "Respetado/a ciudadano/a".',
    '- Sin título "RESPUESTA OFICIAL", sin bloques Radicado:/Fecha:/Asunto:.',
    '- Sin listas numeradas largas; prosa continua o dos párrafos cortos como máximo.',
    '- No incluyas frases meta tipo "Basándome en" o "Aquí tienes". Entrega solo el resumen.',
    '- Evita invocar herramientas externas si el texto del ciudadano ya es suficiente.',
  ].join('\n');
}

/** Fallback directo a OpenRouter cuando el gateway no está disponible */
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
        { role: 'system', content: 'Eres un asistente de la Alcaldía de Medellín especializado en PQRSD. Responde siempre en español colombiano.' },
        { role: 'user', content: prompt },
      ],
      max_tokens: 500,
      temperature: 0.3,
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
async function tryGateway(body: ResumenEjecutivoBody): Promise<{ text: string; source: string }> {
  const { gatewayBaseUrl, postPqrsAssistantChat, crmGatewayUserId, responseTextFromGatewayPayload } =
    await import('@/lib/duckclaw-gateway');
  const gatewayUrl = gatewayBaseUrl();

  if (gatewayUrl) {
    try {

      const chatRequest = {
        message: buildResumenPrompt(body),
        chat_id: `crm-resumen-${body.idTicket}`,
        user_id: crmGatewayUserId(body.duckclawUserId ?? ''),
        username: (body.duckclawUsername || 'Usuario').trim() || 'Usuario',
        chat_type: 'private',
        tenant_id: 'PQRS',
        stream: false,
      };

      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 8000); // 8s timeout

      const { ok, payload } = await postPqrsAssistantChat(gatewayUrl, chatRequest);
      clearTimeout(timeout);

      if (ok) {
        const text = responseTextFromGatewayPayload(payload);
        if (text.trim()) {
          return { text: stripExecutiveSummaryNoise(text), source: 'gateway' };
        }
      }
    } catch (e) {
      console.warn('[RESUMEN] Gateway no disponible, usando OpenRouter directo:', e instanceof Error ? e.message : e);
    }
  }

  // Fallback: OpenRouter directo
  const prompt = buildResumenPrompt(body);
  const text = await callOpenRouterDirect(prompt);
  return { text: stripExecutiveSummaryNoise(text), source: 'openrouter' };
}

export async function POST(request: NextRequest) {
  try {
    const body = (await request.json()) as ResumenEjecutivoBody;

    if (!body.contenidoRaw?.trim() || !body.secretariaNombre?.trim()) {
      return NextResponse.json({ error: 'Faltan contenido o secretaría' }, { status: 400 });
    }

    const { text, source } = await tryGateway(body);

    if (!text.trim()) {
      return NextResponse.json({ error: 'No se obtuvo texto del modelo' }, { status: 502 });
    }

    return NextResponse.json({ text, source });
  } catch (err: unknown) {
    console.error('[IA_RESUMEN_EJECUTIVO]:', err);
    const message = err instanceof Error ? err.message : 'Error desconocido';
    return NextResponse.json({ error: 'Error del servidor', detail: message }, { status: 500 });
  }
}
