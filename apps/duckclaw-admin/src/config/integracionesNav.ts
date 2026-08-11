/** Pestañas del hub Integraciones — sidebar + contenido en /integraciones?tab= */

export const INTEGRACIONES_TABS = [
  { id: 'keys', label: 'API keys', hint: 'Tavily, Fal, Higgsfield y secretos de integración (DB-first)' },
  {
    id: 'dispositivos',
    label: 'Dispositivos',
    hint: 'Monitoreo físico Android (ADB) e infra VPS de producción',
  },
  { id: 'sensory', label: 'Sensory node', hint: 'STT/TTS y laboratorio de voz' },
  { id: 'telegram', label: 'Telegram', hint: 'Canal opcional y webhook ingress' },
] as const;

export type IntegracionesTabId = (typeof INTEGRACIONES_TABS)[number]['id'];

const TAB_IDS = new Set<string>(INTEGRACIONES_TABS.map((t) => t.id));

export function parseIntegracionesTab(raw: string | null): IntegracionesTabId {
  if (raw === 'edge') return 'dispositivos';
  if (raw && TAB_IDS.has(raw)) return raw as IntegracionesTabId;
  return 'keys';
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
