const STORAGE_KEY = 'duckclaw-admin-developer-mode';
export const DEVELOPER_MODE_EVENT = 'duckclaw-developer-mode-change';

export function readDeveloperMode(): boolean {
  if (typeof window === 'undefined') return false;
  return window.localStorage.getItem(STORAGE_KEY) === '1';
}

export function writeDeveloperMode(enabled: boolean): void {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(STORAGE_KEY, enabled ? '1' : '0');
  window.dispatchEvent(new CustomEvent(DEVELOPER_MODE_EVENT));
}
