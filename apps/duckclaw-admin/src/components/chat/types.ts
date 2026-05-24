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
  heartbeatKind?: 'plan' | 'tool' | 'status' | 'visual';
  /** Worker activo en heartbeat (SSE). */
  workerId?: string;
  /** Instancia swarm 1..n. */
  swarmSlot?: number;
  /** Heartbeat de tool: nombre estable para fusionar start/done. */
  toolName?: string;
  toolPhase?: ToolHeartbeatPhase;
  toolStartedAt?: number;
  toolElapsedMs?: number;
  imagePreviews?: ChatImagePreview[];
};
