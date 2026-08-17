/** Open https URLs in the system browser (desktop webview cannot use target=_blank). */

import { mutationHeaders } from '@/lib/csrfClient';
import { isSafeExternalHttpUrl } from '@/lib/safeExternalHttpUrl';
import { isDesktopBuild, isTauriDesktop } from '@/lib/tauriRuntime';

export { isSafeExternalHttpUrl } from '@/lib/safeExternalHttpUrl';

/**
 * Opens a URL in the OS default browser.
 * Desktop: BFF host opener (works without Tauri shell:allow-open).
 * Browser: window.open.
 */
export async function openExternalUrl(raw: string): Promise<void> {
  const url = (raw || '').trim();
  if (!isSafeExternalHttpUrl(url)) {
    throw new Error('URL externa no válida');
  }

  if (isDesktopBuild() || isTauriDesktop()) {
    const res = await fetch('/api/admin/open-external', {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        ...mutationHeaders('POST'),
      },
      body: JSON.stringify({ url }),
      cache: 'no-store',
    });
    if (!res.ok) {
      const data = (await res.json().catch(() => ({}))) as { detail?: string };
      throw new Error(data.detail || `No se pudo abrir el enlace (${res.status})`);
    }
    return;
  }

  const opened = window.open(url, '_blank', 'noopener,noreferrer');
  if (!opened) {
    window.location.assign(url);
  }
}
