import { readFileSync, readdirSync } from 'fs';
import { join } from 'path';
import { repoRoot } from '@/lib/localOps';

export function comfyuiApiUrl(): string {
  return (
    process.env.COMFYUI_API_URL?.trim() ||
    process.env.NEXT_PUBLIC_COMFYUI_API_URL?.trim() ||
    'http://127.0.0.1:8188'
  ).replace(/\/$/, '');
}

export async function comfyuiStatusLocal(): Promise<{
  ok: boolean;
  url: string;
  latency_ms?: number;
  error?: string;
  system?: Record<string, unknown>;
  checkpoints?: string[];
  checkpoints_ready?: boolean;
}> {
  const base = comfyuiApiUrl();
  const url = `${base}/system_stats`;
  const started = Date.now();
  try {
    const res = await fetch(url, { cache: 'no-store', signal: AbortSignal.timeout(8000) });
    if (!res.ok) {
      return {
        ok: false,
        url: base,
        error: `ComfyUI HTTP ${res.status}`,
        checkpoints: [],
        checkpoints_ready: false,
      };
    }
    const data = (await res.json()) as Record<string, unknown>;
    let checkpoints: string[] = [];
    try {
      const oi = await fetch(`${base}/object_info/CheckpointLoaderSimple`, {
        cache: 'no-store',
        signal: AbortSignal.timeout(8000),
      });
      if (oi.ok) {
        const body = (await oi.json()) as {
          CheckpointLoaderSimple?: { input?: { required?: { ckpt_name?: unknown } } };
        };
        const ckptCfg = body.CheckpointLoaderSimple?.input?.required?.ckpt_name;
        if (Array.isArray(ckptCfg) && Array.isArray(ckptCfg[0])) {
          checkpoints = ckptCfg[0].map(String).filter(Boolean);
        }
      }
    } catch {
      checkpoints = [];
    }
    return {
      ok: true,
      url: base,
      latency_ms: Date.now() - started,
      system: data,
      checkpoints,
      checkpoints_ready: checkpoints.length > 0,
    };
  } catch (e) {
    return {
      ok: false,
      url: base,
      error: e instanceof Error ? e.message : 'No se pudo conectar con ComfyUI',
      checkpoints: [],
      checkpoints_ready: false,
    };
  }
}

export function listComfyuiTemplatesLocal(): {
  templates: { id: string; label: string; aspect_ratios: string[] }[];
  default: string;
} {
  const workflowsDir = join(
    repoRoot(),
    'packages',
    'agents',
    'src',
    'duckclaw',
    'forge',
    'templates',
    'workflows'
  );
  const fallback = ['1:1', '16:9', '9:16', '4:3', '3:4'];
  const templates: { id: string; label: string; aspect_ratios: string[] }[] = [];
  try {
    for (const name of readdirSync(workflowsDir)) {
      if (!name.endsWith('.json') || name.endsWith('.meta.json')) continue;
      const stem = name.replace(/\.json$/, '');
      const metaPath = join(workflowsDir, `${stem}.meta.json`);
      let aspect_ratios = fallback;
      try {
        const meta = JSON.parse(readFileSync(metaPath, 'utf8')) as {
          aspect_presets?: Record<string, number[]>;
        };
        if (meta.aspect_presets && typeof meta.aspect_presets === 'object') {
          aspect_ratios = Object.keys(meta.aspect_presets).sort();
        }
      } catch {
        /* sin meta */
      }
      templates.push({
        id: stem,
        label: stem.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()),
        aspect_ratios,
      });
    }
  } catch {
    templates.push({ id: 'comfy_default', label: 'Comfy Default', aspect_ratios: fallback });
  }
  templates.sort((a, b) => a.id.localeCompare(b.id));
  return { templates, default: 'comfy_default' };
}
