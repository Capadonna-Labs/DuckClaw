import { spawn } from 'child_process';

import { isSafeExternalHttpUrl } from '@/lib/safeExternalHttpUrl';

/** Launch the OS default browser for an http(s) URL. */
export function openExternalUrlOnHost(raw: string): Promise<void> {
  const url = (raw || '').trim();
  if (!isSafeExternalHttpUrl(url)) {
    return Promise.reject(new Error('URL externa no válida'));
  }

  return new Promise((resolve, reject) => {
    let child;
    if (process.platform === 'win32') {
      // `start` is a cmd builtin; empty title arg avoids swallowing the URL.
      child = spawn('cmd', ['/c', 'start', '', url], {
        detached: true,
        stdio: 'ignore',
        windowsHide: true,
      });
    } else if (process.platform === 'darwin') {
      child = spawn('open', [url], { detached: true, stdio: 'ignore' });
    } else {
      child = spawn('xdg-open', [url], { detached: true, stdio: 'ignore' });
    }

    child.once('error', reject);
    child.unref();
    resolve();
  });
}
