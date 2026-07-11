/** Pestañas del hub Integraciones — sidebar + contenido en /integraciones?tab= */

export const INTEGRACIONES_TABS = [
  { id: 'edge', label: 'Edge devices', hint: 'Telemetría libedgecore y dashboard Streamlit' },
  { id: 'sensory', label: 'Sensory node', hint: 'STT/TTS y laboratorio de voz' },
  { id: 'telegram', label: 'Telegram', hint: 'Canal opcional y webhook ingress' },
] as const;

export type IntegracionesTabId = (typeof INTEGRACIONES_TABS)[number]['id'];

const TAB_IDS = new Set<string>(INTEGRACIONES_TABS.map((t) => t.id));

export function parseIntegracionesTab(raw: string | null): IntegracionesTabId {
  if (raw && TAB_IDS.has(raw)) return raw as IntegracionesTabId;
  return 'telegram';
}

export function integracionesTabHref(tabId: IntegracionesTabId): string {
  return `/integraciones?tab=${tabId}`;
}

export function isIntegracionesPath(pathname: string): boolean {
  return (
    pathname === '/integraciones' ||
    pathname.startsWith('/integraciones/') ||
    pathname === '/integrations' ||
    pathname.startsWith('/integrations/') ||
    pathname === '/telegram' ||
    pathname.startsWith('/telegram/')
  );
}
