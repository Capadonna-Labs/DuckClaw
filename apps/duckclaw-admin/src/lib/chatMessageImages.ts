import type { ChatImagePreview, ChatMsg } from '@/components/chat/types';
import {
  artifactPreviewApiPath,
  parseArtifactIdFromPath,
} from '@/lib/artifactPreview';

const CONTEXT_BLOCK_TAGS = ['PROJECT_CONTEXT', 'RAG_SOURCE_INVENTORY', 'RAG_CONTEXT'] as const;

/** Quita bloques de contexto inyectados (playground/RAG) antes de mostrar en el hilo. */
export function stripContextBlocksForDisplay(text: string): string {
  let out = text || '';
  for (const tag of CONTEXT_BLOCK_TAGS) {
    out = out.replace(new RegExp(`\\[${tag}\\][\\s\\S]*?\\[\\/${tag}\\]`, 'g'), '');
  }
  return out.replace(/\n{3,}/g, '\n\n').trim();
}

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

/** Reconstruye el payload API desde miniaturas data-URL guardadas en el hilo (reintento). */
export function payloadImagesFromPreviews(
  previews: ChatImagePreview[] | undefined
): { mime_type: string; data_base64: string }[] {
  if (!previews?.length) return [];
  const out: { mime_type: string; data_base64: string }[] = [];
  for (const img of previews) {
    const url = (img.url || '').trim();
    if (!url.startsWith('data:')) continue;
    const match = /^data:([^;,]+);base64,(.+)$/i.exec(url);
    if (!match?.[1] || !match[2]) continue;
    out.push({ mime_type: match[1].toLowerCase(), data_base64: match[2] });
  }
  return out;
}

export function artifactIdsFromMessageText(text: string): string[] {
  const trimmed = (text || '').trim();
  if (!trimmed) return [];
  const ids: string[] = [];
  const re = /(?:artifact[_-]?id\s*[=:]\s*|visual_artifact_id\s*[=:]\s*)([0-9a-f-]{36})/gi;
  let match: RegExpExecArray | null;
  while ((match = re.exec(trimmed)) !== null) {
    const aid = match[1];
    if (aid && !ids.includes(aid)) ids.push(aid);
  }
  const pathId = parseArtifactIdFromPath(trimmed);
  if (pathId && !ids.includes(pathId)) ids.push(pathId);
  return ids;
}

export function artifactIdFromMessageText(text: string): string | null {
  const ids = artifactIdsFromMessageText(text);
  return ids[0] ?? null;
}

export function artifactPreviewFromMessage(
  text: string,
  tenantId: string
): ChatImagePreview[] | undefined {
  const aids = artifactIdsFromMessageText(text);
  if (!aids.length) return undefined;
  const tid = (tenantId || 'default').trim() || 'default';
  return aids.map((aid) => ({
    url: artifactPreviewApiPath(tid, aid),
    name: `${aid}.png`,
    artifactId: aid,
    tenantId: tid,
  }));
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
    const rawText = (m.content || '').trim();
    const text = role === 'user' ? stripContextBlocksForDisplay(rawText) : rawText;
    if (!role || !text) continue;
    const imagePreviews =
      role === 'assistant' ? artifactPreviewFromMessage(text, tid) : undefined;
    out.push({ role, text, ...(imagePreviews ? { imagePreviews } : {}) });
  }
  return out;
}
