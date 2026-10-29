export type BotStatus = 'unknown' | 'starting' | 'online' | 'offline' | 'error';

export interface WorldBot {
  id: string;
  world_id: string;
  name: string;
  worker_id: string;
  settings: Record<string, unknown>;
  enabled: boolean;
  /** What to show: a runner that stopped reporting is offline whatever it last said. */
  status: BotStatus;
  reported_status: string;
  status_detail: string;
  last_seen_at: string | null;
  seconds_since_report: number | null;
}

export interface World {
  id: string;
  name: string;
  kind: string;
  host: string;
  port: number | null;
  config: Record<string, unknown>;
  enabled: boolean;
  bots: WorldBot[];
}

export interface WorldDraft {
  name: string;
  kind: string;
  host: string;
  port: string;
  config: string;
  enabled: boolean;
}

export interface BotDraft {
  name: string;
  worker_id: string;
  settings: string;
  enabled: boolean;
}

/** Parses a JSON object typed by the user; returns the object or an error message in Spanish. */
export function parseJsonObject(text: string): { value: Record<string, unknown> } | { error: string } {
  const trimmed = text.trim();
  if (!trimmed) return { value: {} };
  try {
    const parsed = JSON.parse(trimmed);
    if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return { error: 'Debe ser un objeto JSON, por ejemplo {"clave": "valor"}.' };
    }
    return { value: parsed as Record<string, unknown> };
  } catch (e) {
    return { error: `JSON inválido: ${e instanceof Error ? e.message : 'revisa la sintaxis'}` };
  }
}

export function worldDraftOf(world?: World): WorldDraft {
  return {
    name: world?.name ?? '',
    kind: world?.kind ?? 'generic',
    host: world?.host ?? '',
    port: world?.port != null ? String(world.port) : '',
    config: JSON.stringify(world?.config ?? {}, null, 2),
    enabled: world?.enabled ?? true,
  };
}

export function botDraftOf(bot?: WorldBot): BotDraft {
  return {
    name: bot?.name ?? '',
    worker_id: bot?.worker_id ?? '',
    settings: JSON.stringify(bot?.settings ?? {}, null, 2),
    enabled: bot?.enabled ?? true,
  };
}

export function ageLabel(seconds: number | null): string {
  if (seconds == null) return 'sin reportes';
  if (seconds < 60) return `hace ${seconds}s`;
  if (seconds < 3600) return `hace ${Math.floor(seconds / 60)} min`;
  return `hace ${Math.floor(seconds / 3600)} h`;
}
