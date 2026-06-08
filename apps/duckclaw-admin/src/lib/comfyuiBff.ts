export function comfyuiApiUrl(): string {
  return (
    process.env.COMFYUI_API_URL?.trim() ||
    'http://127.0.0.1:8188'
  ).replace(/\/$/, '');
}

function comfyuiTimeoutSec(): string {
  const raw = (process.env.COMFYUI_TIMEOUT_SEC || '300').trim();
  return /^\d{1,5}(\.\d+)?$/.test(raw) ? raw : '300';
}

export async function comfyuiStatusLocal(): Promise<{
  ok: boolean;
  url: string;
  latency_ms?: number;
  error?: string;
  system?: Record<string, unknown>;
  checkpoints?: string[];
  checkpoints_ready?: boolean;
  source?: string;
  runtime_key?: string;
  timeout_sec?: string;
  timeout_source?: string;
}> {
  const base = comfyuiApiUrl();
  const source = process.env.COMFYUI_API_URL ? 'env' : 'default';
  const timeout_sec = comfyuiTimeoutSec();
  const timeout_source = process.env.COMFYUI_TIMEOUT_SEC ? 'env' : 'default';
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
        source,
        runtime_key: 'comfyui.api_url',
        timeout_sec,
        timeout_source,
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
      source,
      runtime_key: 'comfyui.api_url',
      timeout_sec,
      timeout_source,
    };
  } catch (e) {
    return {
      ok: false,
      url: base,
      error: e instanceof Error ? e.message : 'No se pudo conectar con ComfyUI',
      checkpoints: [],
      checkpoints_ready: false,
      source,
      runtime_key: 'comfyui.api_url',
      timeout_sec,
      timeout_source,
    };
  }
}
