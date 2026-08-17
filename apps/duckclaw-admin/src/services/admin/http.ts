import { friendlyGatewayError, parseApiErrorDetail } from '@/lib/adminErrors';
import { mutationHeaders } from '@/lib/csrfClient';
import {
  isUnauthorizedDetail,
  isUnauthorizedStatus,
  redirectToLoginOnUnauthorized,
} from '@/lib/sessionExpired';

export function sessionHeaders(method = 'GET'): HeadersInit {
  return mutationHeaders(method);
}

/** Coalesce concurrent identical GETs (React Strict Mode / doble mount). */
const inflightAdminGets = new Map<string, Promise<unknown>>();
/** Evita ráfagas secuenciales del mismo GET (bucle de effects). */
const recentAdminGets = new Map<string, { at: number; value: Promise<unknown> }>();
const ADMIN_GET_THROTTLE_MS = 2_000;

export function coalesceAdminGet<T>(key: string, run: () => Promise<T>): Promise<T> {
  const existing = inflightAdminGets.get(key);
  if (existing) return existing as Promise<T>;
  const recent = recentAdminGets.get(key);
  if (recent && Date.now() - recent.at < ADMIN_GET_THROTTLE_MS) {
    return recent.value as Promise<T>;
  }
  const pending = run().finally(() => {
    inflightAdminGets.delete(key);
  });
  // Marcar ya: si el effect reentra en <2s no vuelve a pegarle a la red.
  recentAdminGets.set(key, { at: Date.now(), value: pending });
  inflightAdminGets.set(key, pending);
  return pending;
}

function throwAdminError(res: Response, data: unknown): never {
  const raw = parseApiErrorDetail(data, res.status);
  if (isUnauthorizedStatus(res.status) || isUnauthorizedDetail(raw)) {
    redirectToLoginOnUnauthorized();
    // Tras redirigir, no dejes el mensaje en paneles (chat / ops) como estado “colgado”.
    throw new Error('No autenticado');
  }
  const detail =
    (data as { code?: string } | null)?.code === 'gateway_unreachable' || res.status === 503
      ? friendlyGatewayError(raw || 'gateway_unreachable')
      : friendlyGatewayError(raw || `Error ${res.status}`);
  throw new Error(detail);
}

export async function adminFetchOptional<T>(path: string, init?: RequestInit): Promise<T | null> {
  const method = init?.method || 'GET';
  const res = await fetch(`/api/admin${path}`, {
    ...init,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...sessionHeaders(method),
      ...(init?.headers ?? {}),
    },
    cache: 'no-store',
  });
  if (res.status === 404) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throwAdminError(res, data);
  }
  return data as T;
}

export async function adminFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const method = init?.method || 'GET';
  const res = await fetch(`/api/admin${path}`, {
    ...init,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...sessionHeaders(method),
      ...(init?.headers ?? {}),
    },
    cache: 'no-store',
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throwAdminError(res, data);
  }
  return data as T;
}

export async function adminFormFetch<T>(path: string, formData: FormData, method = 'POST'): Promise<T> {
  const res = await fetch(`/api/admin${path}`, {
    method,
    credentials: 'include',
    headers: {
      ...sessionHeaders(method),
    },
    body: formData,
    cache: 'no-store',
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throwAdminError(res, data);
  }
  return data as T;
}
