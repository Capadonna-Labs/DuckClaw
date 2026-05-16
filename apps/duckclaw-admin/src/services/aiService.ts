/**
 * Servicio centralizado para llamadas a modelos de IA: DuckClaw API Gateway (PQRSD-Assistant) primero;
 * OpenRouter opcional como fallback.
 */
import {
  crmGatewayUserId,
  gatewayBaseUrl,
  postPqrsAssistantChat,
  responseTextFromGatewayPayload,
} from '@/lib/duckclaw-gateway';

const CRM_EMAIL_TRIAGE_CHAT_ID = 'crm-email-triage';

function openRouterFallbackEnabled(): boolean {
  const v = (process.env.CRM_IA_OPENROUTER_FALLBACK ?? 'true').trim().toLowerCase();
  return v !== 'false' && v !== '0' && v !== 'no';
}

async function callOpenRouterDirect(
  systemPrompt: string,
  userPrompt: string,
  temperature: number
): Promise<string> {
  const apiKey = process.env.OPENROUTER_API_KEY;
  const model = process.env.NEXT_PUBLIC_OPENROUTER_MODEL || 'google/gemini-2.0-flash-lite-preview-02-05:free';

  if (!apiKey) {
    console.error('[AI-SERVICE] OpenRouter: OPENROUTER_API_KEY no configurada');
    return '';
  }

  try {
    const res = await fetch('https://openrouter.ai/api/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${apiKey}`,
        'HTTP-Referer': process.env.NEXT_PUBLIC_APP_URL || 'http://localhost:3000',
        'X-Title': 'CRM PQRSD Medellín',
      },
      body: JSON.stringify({
        model,
        messages: [
          { role: 'system', content: systemPrompt },
          { role: 'user', content: userPrompt },
        ],
        max_tokens: 1000,
        temperature,
      }),
    });

    if (!res.ok) {
      const err = await res.text();
      console.warn(`[AI-SERVICE] OpenRouter error: ${res.status} - ${err.slice(0, 100)}`);
      return '';
    }

    const data = (await res.json()) as {
      choices?: { message?: { content?: string } }[];
    };
    return data.choices?.[0]?.message?.content?.trim() || '';
  } catch (error) {
    console.error('[AI-SERVICE] OpenRouter error de red:', error);
    return '';
  }
}

/**
 * Triaje / extracción (p. ej. ingesta de correo). Prioriza el mismo gateway PM2 que el panel IA.
 */
export async function callAiModel(
  systemPrompt: string,
  userPrompt: string,
  temperature: number = 0.3
): Promise<string> {
  const base = gatewayBaseUrl();

  if (base) {
    try {
      const message = [
        '[Modo: triaje CRM ingesta correo — salida JSON según instrucciones siguientes; ignorar flujo conversacional Telegram]',
        '',
        '--- Instrucciones del sistema ---',
        systemPrompt.trim(),
        '',
        '--- Entrada del usuario ---',
        userPrompt.trim(),
      ].join('\n');

      const { ok, payload } = await postPqrsAssistantChat(base, {
        message,
        chat_id: CRM_EMAIL_TRIAGE_CHAT_ID,
        user_id: crmGatewayUserId('crm-email-ingesta'),
        username: 'CRM-Ingesta',
        chat_type: 'private',
        tenant_id: 'PQRS',
        stream: false,
      });

      if (ok) {
        const text = responseTextFromGatewayPayload(payload).trim();
        if (text) {
          return text;
        }
        console.warn('[AI-SERVICE] Gateway devolvió respuesta vacía');
      } else {
        console.warn('[AI-SERVICE] Gateway respondió sin éxito; evaluar fallback OpenRouter');
      }
    } catch (e) {
      console.warn('[AI-SERVICE] Gateway error:', e instanceof Error ? e.message : e);
    }
  } else {
    console.warn('[AI-SERVICE] Sin DUCKCLAW_GATEWAY_URL / NEXT_PUBLIC_API_URL; usando fallback si aplica');
  }

  if (openRouterFallbackEnabled()) {
    return callOpenRouterDirect(systemPrompt, userPrompt, temperature);
  }

  console.error('[AI-SERVICE] Sin respuesta del gateway y CRM_IA_OPENROUTER_FALLBACK desactiva o sin OPENROUTER_API_KEY');
  return '';
}
