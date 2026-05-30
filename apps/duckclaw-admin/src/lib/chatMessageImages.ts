import type { ChatImagePreview, ChatMsg } from '@/components/chat/types';
import {
  artifactPreviewApiPath,
  parseArtifactIdFromPath,
} from '@/lib/artifactPreview';

const ARTIFACT_ID_RE =
  /(?:artifact[_-]?id\s*[=:]\s*|visual_artifact_id\s*[=:]\s*)([0-9a-f-]{36})/i;

export function userPreviewsFromPayload(
  payload: { mime_type: string; data_base64: string }[],
  names: string[] = []
): ChatImagePreview[] {
  return payload.map((p, i) => ({
    url: `data:${p.mime_type};base64,${p.data_base64}`,
    name: names[i]?.trim() || `imagen-${i + 1}.png`,
  }));
}

export function artifactIdFromMessageText(text: string): string | null {
  const trimmed = (text || '').trim();
  if (!trimmed) return null;
  return parseArtifactIdFromPath(trimmed) || trimmed.match(ARTIFACT_ID_RE)?.[1] || null;
}

export function artifactPreviewFromMessage(
  text: string,
  tenantId: string
): ChatImagePreview[] | undefined {
  const aid = artifactIdFromMessageText(text);
  if (!aid) return undefined;
  const tid = (tenantId || 'default').trim() || 'default';
  return [
    {
      url: artifactPreviewApiPath(tid, aid),
      name: `${aid}.png`,
      artifactId: aid,
      tenantId: tid,
    },
  ];
}

/** Reaplica miniaturas locales cuando el historial Redis no trae binarios/metadata. */
export function preserveImagePreviewsFromPrevious(
  server: ChatMsg[],
  previous: ChatMsg[]
): ChatMsg[] {
  if (!previous.some((m) => m.imagePreviews?.length)) return server;
  return server.map((m, i) => {
    if (m.imagePreviews?.length) return m;
    const prev = previous[i];
    if (prev?.role === m.role && prev.imagePreviews?.length) {
      return { ...m, imagePreviews: prev.imagePreviews };
    }
    return m;
  });
}

export function historyToChatMessages(
  raw: { role: string; content: string }[] | undefined,
  tenantId = 'default'
): ChatMsg[] {
  if (!raw?.length) return [];
  const tid = (tenantId || 'default').trim() || 'default';
  const out: ChatMsg[] = [];
  for (const m of raw) {
    const role = m.role === 'user' ? 'user' : m.role === 'assistant' ? 'assistant' : null;
    const text = (m.content || '').trim();
    if (!role || !text) continue;
    const imagePreviews =
      role === 'assistant' ? artifactPreviewFromMessage(text, tid) : undefined;
    out.push({ role, text, ...(imagePreviews ? { imagePreviews } : {}) });
  }
  return out;
}
