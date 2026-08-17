import { sessionHeaders } from '@/services/admin/http';
import { isTauriDesktop } from '@/lib/tauriRuntime';

export type DesktopLocalFilePayload = {
  name: string;
  mime_type: string;
  data_base64: string;
  size: number;
};

/** Lee rutas locales vía BFF (drop nativo de Tauri entrega paths, no File). */
export async function fetchDesktopLocalFiles(
  paths: string[]
): Promise<DesktopLocalFilePayload[]> {
  const cleaned = paths.map((p) => (p || '').trim()).filter(Boolean);
  if (cleaned.length === 0) return [];
  const res = await fetch('/api/admin/desktop-local-files', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...sessionHeaders('POST'),
    },
    credentials: 'include',
    body: JSON.stringify({ paths: cleaned }),
    cache: 'no-store',
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail =
      typeof data?.detail === 'string'
        ? data.detail
        : data?.detail?.detail ?? data?.title ?? res.statusText;
    throw new Error(detail || `Error ${res.status}`);
  }
  const files = Array.isArray(data?.files) ? data.files : [];
  return files
    .map((item: Record<string, unknown>) => ({
      name: String(item.name || '').trim(),
      mime_type: String(item.mime_type || 'application/octet-stream'),
      data_base64: String(item.data_base64 || ''),
      size: Number(item.size || 0),
    }))
    .filter((item: DesktopLocalFilePayload) => item.name && item.data_base64);
}

export function desktopLocalFileToFile(payload: DesktopLocalFilePayload): File {
  const binary = atob(payload.data_base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return new File([bytes], payload.name, {
    type: payload.mime_type || 'application/octet-stream',
  });
}

export async function desktopLocalPathsToFiles(paths: string[]): Promise<File[]> {
  if (!isTauriDesktop() || paths.length === 0) return [];
  const payloads = await fetchDesktopLocalFiles(paths);
  return payloads.map(desktopLocalFileToFile);
}
