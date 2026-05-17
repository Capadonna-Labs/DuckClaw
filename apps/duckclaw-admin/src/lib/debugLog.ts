/** Instrumentación NDJSON (sesión debug dc7091). */

type DebugPayload = {
  location: string;
  message: string;
  data?: Record<string, unknown>;
  hypothesisId?: string;
  runId?: string;
};

export function debugLog(payload: DebugPayload): void {
  // #region agent log
  fetch('http://127.0.0.1:7477/ingest/4cb00f05-d949-473c-91c2-92e570fd43ec', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Debug-Session-Id': 'dc7091',
    },
    body: JSON.stringify({
      sessionId: 'dc7091',
      timestamp: Date.now(),
      ...payload,
    }),
  }).catch(() => {});
  // #endregion
}
