import { friendlyGatewayError } from '@/lib/adminErrors';
import type { KanbanCard, KanbanStatus } from '@/lib/kanbanTypes';

import { adminFetch, sessionHeaders } from './http';

export interface OpsCommand {
  id: string;
  label: string;
  argv: string[];
}

export const opsApi = {
  listOpsCommands: () => adminFetch<{ commands: OpsCommand[] }>('/ops/commands'),
  runOps: (opId: string) =>
    adminFetch<{
      ok: boolean;
      op_id: string;
      exit_code: number;
      stdout: string;
      stderr: string;
      executed_via?: 'local' | string;
    }>('/ops/run', { method: 'POST', body: JSON.stringify({ op_id: opId }) }),
  getComfyuiStatus: () =>
    adminFetch<{
      ok: boolean;
      url: string;
      source?: string;
      runtime_key?: string;
      timeout_sec?: string;
      timeout_source?: string;
      latency_ms?: number;
      error?: string;
      system?: Record<string, unknown>;
      checkpoints?: string[];
      checkpoints_ready?: boolean;
    }>('/comfyui/status'),
  listComfyuiTemplates: () =>
    adminFetch<{
      templates: { id: string; label: string; aspect_ratios: string[] }[];
      default: string;
    }>('/comfyui/templates'),
  generateComfyuiImage: (body: {
    prompt: string;
    negative_prompt?: string;
    aspect_ratio?: string;
    template?: string;
    tenant_id?: string;
  }) =>
    fetch('/api/admin/comfyui/generate', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...sessionHeaders('POST'),
      },
      credentials: 'include',
      body: JSON.stringify(body),
      cache: 'no-store',
    }).then(async (res) => {
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const raw =
          typeof data?.detail === 'string'
            ? data.detail
            : data?.detail?.detail ?? data?.title ?? res.statusText;
        throw new Error(friendlyGatewayError(raw || `Error ${res.status}`));
      }
      return data as {
        ok: boolean;
        file_path?: string;
        artifact_id?: string;
        figure_base64?: string;
        prompt_id?: string;
        aspect_ratio?: string;
        message?: string;
        error?: string;
      };
    }),

  /** Carga imagen del vault local vía BFF (cuando figure_base64 no viene por tamaño). */
  fetchArtifactPreviewBlob: async (tenantId: string, artifactId: string) => {
    const res = await fetch(
      `/api/admin/artifacts/${encodeURIComponent(tenantId)}/${encodeURIComponent(artifactId)}`,
      { headers: sessionHeaders('GET'), credentials: 'include', cache: 'no-store' }
    );
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      const raw =
        typeof data?.detail === 'string' ? data.detail : `Error ${res.status} al cargar imagen`;
      throw new Error(raw);
    }
    const blob = await res.blob();
    return URL.createObjectURL(blob);
  },
  getKanbanCards: () => adminFetch<{ cards: KanbanCard[] }>('/kanban'),
  createKanbanCard: (body: {
    title: string;
    description?: string;
    status?: KanbanStatus;
    worker_id?: string;
  }) =>
    adminFetch<{ ok: boolean; card: KanbanCard }>('/kanban', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  updateKanbanCard: (body: {
    id: string;
    title?: string;
    description?: string;
    status?: KanbanStatus;
    worker_id?: string;
  }) =>
    adminFetch<{ ok: boolean; card: KanbanCard }>('/kanban', {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  deleteKanbanCard: (id: string) =>
    adminFetch<{ ok: boolean }>(`/kanban?id=${encodeURIComponent(id)}`, { method: 'DELETE' }),
};
