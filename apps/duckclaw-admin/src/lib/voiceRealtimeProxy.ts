/**
 * BFF proxy helpers for Pipecat SmallWebRTC signaling (same-origin from admin UI).
 */

export type VoiceSessionRequestData = {
  worker_id?: string;
  chat_id?: string;
  tenant_id?: string;
  session_id?: string;
  actor_email?: string;
};

export function voiceInternalBase(): string | null {
  const explicit = (process.env.DUCKCLAW_VOICE_INTERNAL_URL || '').trim();
  if (explicit) return explicit.replace(/\/$/, '');
  const port = (process.env.DUCKCLAW_VOICE_PORT || '8012').trim();
  const host = (process.env.DUCKCLAW_VOICE_HOST || '127.0.0.1').trim() || '127.0.0.1';
  if (/^\d+$/.test(port)) return `http://${host}:${port}`;
  return null;
}

export function voiceConnectHint(): string {
  const base = voiceInternalBase();
  if (base) return base;
  return 'DUCKCLAW_VOICE_INTERNAL_URL o DUCKCLAW_VOICE_PORT en apps/duckclaw-admin/.env.local';
}

/** Merge playground session context into Pipecat offer request_data (server-side trust). */
export function mergeVoiceOfferRequestData(
  body: Record<string, unknown>,
  session: VoiceSessionRequestData
): Record<string, unknown> {
  const merged = { ...body };
  const snake =
    merged.request_data && typeof merged.request_data === 'object' && !Array.isArray(merged.request_data)
      ? (merged.request_data as Record<string, unknown>)
      : {};
  const camel =
    merged.requestData && typeof merged.requestData === 'object' && !Array.isArray(merged.requestData)
      ? (merged.requestData as Record<string, unknown>)
      : {};
  const existing = { ...snake, ...camel };

  const workerId = (session.worker_id || '').trim();
  const chatId = (session.chat_id || '').trim();
  const tenantId = (session.tenant_id || '').trim();
  const actorEmail = (session.actor_email || '').trim();

  if (workerId) existing.worker_id = workerId;
  if (tenantId) existing.tenant_id = tenantId;
  if (actorEmail) existing.actor_email = actorEmail;
  if (chatId) {
    existing.chat_id = chatId;
    existing.session_id = chatId;
  }

  merged.request_data = existing;
  delete merged.requestData;
  return merged;
}

export function parseVoiceSessionFromSearchParams(
  searchParams: URLSearchParams
): VoiceSessionRequestData {
  return {
    worker_id: (searchParams.get('worker_id') || '').trim() || undefined,
    chat_id: (searchParams.get('chat_id') || '').trim() || undefined,
    tenant_id: (searchParams.get('tenant_id') || '').trim() || undefined,
  };
}
