/** Timeout de ociosidad SSE: keepalive gateway es ~25s; 3× sin bytes → stream muerto. */
export const SSE_IDLE_TIMEOUT_MS = 90_000;

export class SseIdleTimeoutError extends Error {
  readonly name = 'SseIdleTimeoutError';
  constructor(message = 'SSE idle timeout') {
    super(message);
  }
}

export function isSseIdleTimeoutError(err: unknown): boolean {
  return err instanceof SseIdleTimeoutError || (err instanceof Error && err.name === 'SseIdleTimeoutError');
}
