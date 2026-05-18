export type ChatImagePreview = {
  url: string;
  name: string;
};

export type ChatMsg = {
  role: 'user' | 'assistant' | 'error' | 'heartbeat';
  text: string;
  streaming?: boolean;
  interrupted?: boolean;
  heartbeatKind?: 'plan' | 'tool' | 'status';
  /** Worker activo en heartbeat (SSE). */
  workerId?: string;
  /** Instancia swarm 1..n. */
  swarmSlot?: number;
  imagePreviews?: ChatImagePreview[];
};
