import { friendlyGatewayError, parseApiErrorDetail } from '@/lib/adminErrors';
import { mutationHeaders } from '@/lib/csrfClient';

export function sessionHeaders(method = 'GET'): HeadersInit {
  return mutationHeaders(method);
}

/** Coalesce concurrent identical GETs (React Strict Mode / doble mount). */
const inflightAdminGets = new Map<string, Promise<unknown>>();

export function coalesceAdminGet<T>(key: string, run: () => Promise<T>): Promise<T> {
  const existing = inflightAdminGets.get(key);
  if (existing) return existing as Promise<T>;
  const pending = run().finally(() => {
    inflightAdminGets.delete(key);
  });
  inflightAdminGets.set(key, pending);
  return pending;
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
    const raw = parseApiErrorDetail(data, res.status);
    const detail =
      data?.code === 'gateway_unreachable' || res.status === 503
        ? friendlyGatewayError(raw || 'gateway_unreachable')
        : friendlyGatewayError(raw || `Error ${res.status}`);
    throw new Error(detail);
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
    const raw = parseApiErrorDetail(data, res.status);
    const detail =
      data?.code === 'gateway_unreachable' || res.status === 503
        ? friendlyGatewayError(raw || 'gateway_unreachable')
        : friendlyGatewayError(raw || `Error ${res.status}`);
    throw new Error(detail);
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
    const raw = parseApiErrorDetail(data, res.status);
    throw new Error(friendlyGatewayError(raw || `Error ${res.status}`));
  }
  return data as T;
}
