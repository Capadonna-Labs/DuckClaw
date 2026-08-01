export type ChatImagePreview = {
  url: string;
  name: string;
  /** Para descarga con nombre estable (ComfyUI / artifacts). */
  artifactId?: string;
  tenantId?: string;
};

export type ToolHeartbeatPhase = 'start' | 'running' | 'done' | 'error';

export type ChatMsg = {
  role: 'user' | 'assistant' | 'error' | 'heartbeat';
  text: string;
  streaming?: boolean;
  interrupted?: boolean;
  heartbeatKind?: 'plan' | 'tool' | 'status' | 'visual' | 'loop_tick';
  /** Worker activo en heartbeat (SSE). */
  workerId?: string;
  /** Instancia swarm 1..n. */
  swarmSlot?: number;
  /** Heartbeat de tool: nombre estable para fusionar start/done. */
  toolName?: string;
  /** Identidad única por invocación (p. ej. varios fetch_market_data en el mismo turno). */
  toolInvocationId?: string;
  toolPhase?: ToolHeartbeatPhase;
  toolStartedAt?: number;
  toolElapsedMs?: number;
  /** Turno (usuarios previos) para reinsertar heartbeats tras reload. */
  turnUserIndex?: number;
  imagePreviews?: ChatImagePreview[];
  /** Mensaje de usuario originado por nota de voz. */
  voiceNote?: boolean;
  /** Audio TTS (base64) en respuesta del asistente. */
  audioBase64?: string;
  audioFormat?: 'ogg' | 'wav';
  audioUnavailable?: boolean;
  audioPlayError?: string;
};
