export type ChatImagePreview = {
  url: string;
  name: string;
  /** Para descarga con nombre estable (ComfyUI / artifacts). */
  artifactId?: string;
  tenantId?: string;
};

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
  imagePreviews?: ChatImagePreview[];
};
