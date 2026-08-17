/** True when admin runs inside the Tauri desktop webview. */
export function isTauriDesktop(): boolean {
  if (typeof window === 'undefined') return false;
  const w = window as Window & { __TAURI_INTERNALS__?: unknown; __TAURI__?: unknown };
  return Boolean(w.__TAURI_INTERNALS__ ?? w.__TAURI__);
}

/** True when built for desktop bundle (may lack Tauri IPC in browser dev). */
export function isDesktopBuild(): boolean {
  return (process.env.NEXT_PUBLIC_DUCKCLAW_DESKTOP || '').trim() === '1';
}
