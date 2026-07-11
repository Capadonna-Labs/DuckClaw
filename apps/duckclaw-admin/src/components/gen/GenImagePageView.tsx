'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { adminService } from '@/services/adminService';
import { friendlyGatewayError } from '@/lib/adminErrors';
import { parseArtifactIdFromPath } from '@/lib/artifactPreview';
import { useAuthStore } from '@/store/authStore';
import { RefreshCw } from 'lucide-react';
import { ViewChrome, type EmbeddedViewProps } from '@/components/admin/embeddedView';

const ASPECT_FALLBACK = ['1:1', '16:9', '9:16', '4:3', '3:4'];

function formatElapsedSec(ms: number): string {
  return `${(ms / 1000).toFixed(2)} s`;
}

export default function GenImagePageView({ embedded = false }: EmbeddedViewProps) {
  const { usuario } = useAuthStore();
  const canWriteSettings = usuario?.rol === 'admin';
  const [status, setStatus] = useState<Awaited<
    ReturnType<typeof adminService.getComfyuiStatus>
  > | null>(null);
  const [templates, setTemplates] = useState<
    { id: string; label: string; aspect_ratios: string[] }[]
  >([]);
  const [defaultTemplate, setDefaultTemplate] = useState('comfy_default');
  const [prompt, setPrompt] = useState('');
  const [negativePrompt, setNegativePrompt] = useState('');
  const [aspectRatio, setAspectRatio] = useState('1:1');
  const [template, setTemplate] = useState('comfy_default');
  const [tenantId, setTenantId] = useState('default');
  const [loading, setLoading] = useState(false);
  const [opsBusy, setOpsBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [settingsMsg, setSettingsMsg] = useState<string | null>(null);
  const [settingsSaving, setSettingsSaving] = useState(false);
  const [comfyApiUrl, setComfyApiUrl] = useState('http://127.0.0.1:8188');
  const [comfySource, setComfySource] = useState('default');
  const [comfyTimeoutSec, setComfyTimeoutSec] = useState('300');
  const [comfyTimeoutSource, setComfyTimeoutSource] = useState('default');
  const [result, setResult] = useState<{
    file_path?: string;
    artifact_id?: string;
    figure_base64?: string;
    prompt_id?: string;
    elapsedMs?: number;
  } | null>(null);
  const [previewBlobUrl, setPreviewBlobUrl] = useState<string | null>(null);
  const [generatingElapsedMs, setGeneratingElapsedMs] = useState(0);

  const aspectOptions = useMemo(() => {
    const t = templates.find((x) => x.id === template);
    return t?.aspect_ratios?.length ? t.aspect_ratios : ASPECT_FALLBACK;
  }, [templates, template]);

  const previewSrc = useMemo(() => {
    if (previewBlobUrl) return previewBlobUrl;
    if (!result?.figure_base64) return null;
    const raw = result.figure_base64.trim();
    if (raw.startsWith('data:')) return raw;
    return `data:image/png;base64,${raw}`;
  }, [result, previewBlobUrl]);

  useEffect(() => {
    return () => {
      if (previewBlobUrl?.startsWith('blob:')) {
        URL.revokeObjectURL(previewBlobUrl);
      }
    };
  }, [previewBlobUrl]);

  const loadMeta = useCallback(async () => {
    try {
      const [st, tpl, cfg] = await Promise.all([
        adminService.getComfyuiStatus(),
        adminService.listComfyuiTemplates(),
        adminService.getPlaygroundConfig(),
      ]);
      setStatus(st);
      setComfyApiUrl(st.url || 'http://127.0.0.1:8188');
      setComfySource(st.source || 'default');
      setComfyTimeoutSec(st.timeout_sec || '300');
      setComfyTimeoutSource(st.timeout_source || 'default');
      setTemplates(tpl.templates);
      setDefaultTemplate(tpl.default || 'comfy_default');
      setTemplate((prev) => prev || tpl.default || 'comfy_default');
      if (cfg.effective_tenant_id) setTenantId(cfg.effective_tenant_id);
      setError(null);
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Error al cargar';
      setError(
        msg.includes('404') || msg.includes('502')
          ? `${friendlyGatewayError(msg)} Recarga la página o reinicia el Gateway si Generar falla.`
          : friendlyGatewayError(msg)
      );
    }
  }, []);

  useEffect(() => {
    void loadMeta();
  }, [loadMeta]);

  useEffect(() => {
    if (!loading) {
      setGeneratingElapsedMs(0);
      return;
    }
    const started = Date.now();
    setGeneratingElapsedMs(0);
    const timer = window.setInterval(() => {
      setGeneratingElapsedMs(Date.now() - started);
    }, 100);
    return () => window.clearInterval(timer);
  }, [loading]);

  const runOp = async (opId: string) => {
    setOpsBusy(opId);
    setError(null);
    try {
      const out = await adminService.runOps(opId);
      if (out.exit_code !== 0) {
        setError(out.stderr || out.stdout || `Ops ${opId} falló`);
      }
      await loadMeta();
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Error en operación PM2';
      setError(
        msg === opId || msg.includes('Comando no permitido')
          ? `PM2 local: ${msg}`
          : msg
      );
    } finally {
      setOpsBusy(null);
    }
  };

  const saveComfySettings = async () => {
    if (!canWriteSettings) return;
    const apiUrl = comfyApiUrl.trim().replace(/\/$/, '');
    const timeoutSec = comfyTimeoutSec.trim();
    if (!/^https?:\/\/.+/.test(apiUrl)) {
      setSettingsMsg('URL inválida. Usa http:// o https://.');
      return;
    }
    if (!/^\d{1,5}(\.\d+)?$/.test(timeoutSec)) {
      setSettingsMsg('Timeout inválido.');
      return;
    }
    setSettingsSaving(true);
    setSettingsMsg(null);
    try {
      await adminService.patchRuntimeSettings([
        { domain: 'comfyui', key: 'api_url', value: apiUrl, scope: 'global' },
        { domain: 'comfyui', key: 'timeout_sec', value: timeoutSec, scope: 'global' },
      ]);
      setSettingsMsg('Configuración ComfyUI guardada en DuckDB.');
      await loadMeta();
    } catch (e) {
      setSettingsMsg(e instanceof Error ? e.message : 'No se pudo guardar ComfyUI');
    } finally {
      setSettingsSaving(false);
    }
  };

  const onGenerate = async () => {
    const text = prompt.trim();
    if (!text) {
      setError('Escribe un prompt.');
      return;
    }
    setLoading(true);
    setError(null);
    setResult(null);
    if (previewBlobUrl?.startsWith('blob:')) {
      URL.revokeObjectURL(previewBlobUrl);
    }
    setPreviewBlobUrl(null);
    const started = Date.now();
    try {
      const payload = await adminService.generateComfyuiImage({
        prompt: text,
        negative_prompt: negativePrompt.trim(),
        aspect_ratio: aspectRatio,
        template,
        tenant_id: tenantId,
      });
      const artifactId =
        payload.artifact_id ||
        parseArtifactIdFromPath(payload.file_path) ||
        undefined;
      setResult({
        file_path: payload.file_path,
        artifact_id: artifactId,
        figure_base64: payload.figure_base64,
        prompt_id: payload.prompt_id,
        elapsedMs: Date.now() - started,
      });
      if (!payload.figure_base64 && artifactId) {
        const url = await adminService.fetchArtifactPreviewBlob(tenantId, artifactId);
        setPreviewBlobUrl(url);
      }
    } catch (e) {
      setError(friendlyGatewayError(e instanceof Error ? e.message : 'Error al generar'));
    } finally {
      setLoading(false);
    }
  };

  const comfyOnline = Boolean(status?.ok);
  const checkpointsReady = status?.checkpoints_ready !== false && (status?.checkpoints?.length ?? 0) > 0;
  const canGenerate = comfyOnline && checkpointsReady;

  return (
    <ViewChrome embedded={embedded}>
      <div className="space-y-4">
        {!embedded && (
          <header className="border-b border-gov-gray-200 pb-4 dark:border-dark-border">
            <h1 className="text-2xl font-bold text-gov-gray-900 dark:text-dark-text">Imágenes</h1>
            <p className="mt-1 text-sm text-gov-gray-600 dark:text-dark-muted">
              Generación txt2img vía ComfyUI
            </p>
          </header>
        )}

        <div className="flex flex-wrap items-center justify-end gap-2">
          <button
            type="button"
            onClick={() => void loadMeta()}
            className="inline-flex items-center gap-2 rounded-lg border border-gov-gray-200 px-3 py-1.5 text-xs font-semibold text-gov-gray-700 dark:border-dark-border dark:text-dark-muted"
          >
            <RefreshCw size={14} />
            Actualizar
          </button>
        </div>

        {error && (
          <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600 dark:bg-red-950/40 dark:text-red-400">
            {error}
          </p>
        )}

        <div className="grid gap-4 lg:grid-cols-12">
          <div className="space-y-4 lg:col-span-8">
            <section className="rounded-xl border border-gov-gray-200 bg-white dark:border-dark-border dark:bg-dark-surface">
              <div className="border-b border-gov-gray-100 px-4 py-3 dark:border-dark-border">
                <h2 className="text-base font-semibold text-gov-gray-900 dark:text-dark-text">Generar</h2>
              </div>
              <div className="space-y-4 p-4">
                <label className="block text-sm">
                  <span className="font-medium text-gov-gray-800 dark:text-dark-text">Prompt</span>
                  <textarea
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                    rows={4}
                    className="mt-1 w-full rounded-lg border border-gov-gray-200 bg-white px-3 py-2 text-sm dark:border-dark-border dark:bg-dark-bg"
                    placeholder="Describe la imagen…"
                  />
                </label>
                <label className="block text-sm">
                  <span className="font-medium text-gov-gray-800 dark:text-dark-text">Negative prompt</span>
                  <input
                    value={negativePrompt}
                    onChange={(e) => setNegativePrompt(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-gov-gray-200 bg-white px-3 py-2 text-sm dark:border-dark-border dark:bg-dark-bg"
                  />
                </label>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                  <label className="block text-sm">
                    <span className="font-medium text-gov-gray-800 dark:text-dark-text">Template</span>
                    <select
                      value={template}
                      onChange={(e) => setTemplate(e.target.value)}
                      className="mt-1 w-full rounded-lg border border-gov-gray-200 bg-white px-3 py-2 text-sm dark:border-dark-border dark:bg-dark-bg"
                    >
                      {(templates.length
                        ? templates
                        : [{ id: defaultTemplate, label: defaultTemplate, aspect_ratios: ASPECT_FALLBACK }]
                      ).map((t) => (
                        <option key={t.id} value={t.id}>
                          {t.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="block text-sm">
                    <span className="font-medium text-gov-gray-800 dark:text-dark-text">Aspect ratio</span>
                    <select
                      value={aspectRatio}
                      onChange={(e) => setAspectRatio(e.target.value)}
                      className="mt-1 w-full rounded-lg border border-gov-gray-200 bg-white px-3 py-2 text-sm dark:border-dark-border dark:bg-dark-bg"
                    >
                      {aspectOptions.map((ar) => (
                        <option key={ar} value={ar}>
                          {ar}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="block text-sm">
                    <span className="font-medium text-gov-gray-800 dark:text-dark-text">Tenant</span>
                    <input
                      value={tenantId}
                      onChange={(e) => setTenantId(e.target.value)}
                      className="mt-1 w-full rounded-lg border border-gov-gray-200 bg-white px-3 py-2 text-sm dark:border-dark-border dark:bg-dark-bg"
                    />
                  </label>
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  <button
                    type="button"
                    disabled={loading || !canGenerate}
                    onClick={() => void onGenerate()}
                    className="rounded-lg bg-gov-blue-700 px-4 py-2 text-sm font-semibold text-white hover:bg-gov-blue-800 disabled:opacity-50"
                  >
                    {loading ? 'Generando…' : 'Generar'}
                  </button>
                  {loading && (
                    <span className="text-sm tabular-nums text-gov-gray-600 dark:text-dark-muted">
                      {formatElapsedSec(generatingElapsedMs)}
                    </span>
                  )}
                </div>
              </div>
            </section>

            {result && (
              <section className="rounded-xl border border-gov-gray-200 bg-white dark:border-dark-border dark:bg-dark-surface">
                <div className="border-b border-gov-gray-100 px-4 py-3 dark:border-dark-border">
                  <h2 className="text-base font-semibold text-gov-gray-900 dark:text-dark-text">Resultado</h2>
                </div>
                <div className="p-4">
                  {previewSrc ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={previewSrc}
                      alt="Generada por ComfyUI"
                      className="mb-3 max-h-[min(70vh,640px)] w-auto max-w-full rounded-lg border border-gov-gray-200 dark:border-dark-border"
                    />
                  ) : (
                    <p className="mb-3 text-sm text-amber-800 dark:text-amber-200">
                      Imagen en disco; vista previa no disponible.
                      {result.artifact_id ? ` ID: ${result.artifact_id}` : ''}
                    </p>
                  )}
                  {result.file_path && (
                    <p className="break-all font-mono text-xs text-gov-gray-600 dark:text-dark-muted">
                      {result.file_path}
                    </p>
                  )}
                  {result.elapsedMs != null && (
                    <p className="mt-2 text-sm tabular-nums text-gov-gray-600 dark:text-dark-muted">
                      {formatElapsedSec(result.elapsedMs)}
                    </p>
                  )}
                </div>
              </section>
            )}
          </div>

          <aside className="space-y-4 lg:col-span-4">
            <section className="rounded-xl border border-gov-gray-200 bg-white p-4 dark:border-dark-border dark:bg-dark-surface">
              <p className="text-sm font-semibold text-gov-gray-900 dark:text-dark-text">Servicio</p>
              <div className="mt-3 space-y-2 text-sm">
                <span
                  className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                    comfyOnline
                      ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200'
                      : 'bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-100'
                  }`}
                >
                  {comfyOnline ? 'Online' : 'Offline'}
                  {status?.latency_ms != null && comfyOnline ? ` · ${status.latency_ms} ms` : ''}
                </span>
                {status?.error && !comfyOnline && (
                  <p className="text-xs text-gov-gray-500">{status.error}</p>
                )}
                {comfyOnline && !checkpointsReady && (
                  <p className="text-xs text-amber-800 dark:text-amber-200">
                    Sin checkpoints en el directorio de modelos.
                  </p>
                )}
                {comfyOnline && checkpointsReady && status?.checkpoints?.length ? (
                  <p className="text-xs text-gov-gray-500">
                    {status.checkpoints.slice(0, 2).join(', ')}
                    {status.checkpoints.length > 2 ? ` (+${status.checkpoints.length - 2})` : ''}
                  </p>
                ) : null}
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={opsBusy !== null}
                  onClick={() => void runOp('pm2_start_comfyui')}
                  className="rounded-lg bg-gov-blue-700 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
                >
                  {opsBusy === 'pm2_start_comfyui' ? 'Iniciando…' : 'Iniciar PM2'}
                </button>
                <button
                  type="button"
                  disabled={opsBusy !== null}
                  onClick={() => void runOp('pm2_restart_comfyui')}
                  className="rounded-lg border border-gov-gray-200 px-3 py-1.5 text-xs font-semibold dark:border-dark-border disabled:opacity-50"
                >
                  {opsBusy === 'pm2_restart_comfyui' ? 'Reiniciando…' : 'Reiniciar'}
                </button>
              </div>
            </section>

            <section className="rounded-xl border border-gov-gray-200 bg-white dark:border-dark-border dark:bg-dark-surface">
              <div className="border-b border-gov-gray-100 px-4 py-3 dark:border-dark-border">
                <h2 className="text-base font-semibold text-gov-gray-900 dark:text-dark-text">
                  Configuración ComfyUI
                </h2>
              </div>
              <div className="space-y-3 p-4 text-sm">
                <label htmlFor="comfyui-api-url" className="block">
                  <span className="text-xs font-medium text-gov-gray-600 dark:text-dark-muted">API URL</span>
                  <input
                    id="comfyui-api-url"
                    value={comfyApiUrl}
                    onChange={(e) => setComfyApiUrl(e.target.value)}
                    disabled={!canWriteSettings}
                    className="mt-1 w-full rounded-lg border border-gov-gray-200 px-3 py-2 font-mono text-xs dark:border-dark-border dark:bg-dark-bg"
                  />
                </label>
                <label htmlFor="comfyui-timeout-sec" className="block">
                  <span className="text-xs font-medium text-gov-gray-600 dark:text-dark-muted">
                    Timeout (s)
                  </span>
                  <input
                    id="comfyui-timeout-sec"
                    value={comfyTimeoutSec}
                    onChange={(e) => setComfyTimeoutSec(e.target.value)}
                    disabled={!canWriteSettings}
                    className="mt-1 w-full rounded-lg border border-gov-gray-200 px-3 py-2 font-mono text-xs dark:border-dark-border dark:bg-dark-bg"
                  />
                </label>
                <p className="text-xs text-gov-gray-500 dark:text-dark-muted">
                  Fuente: <span className="font-mono">{comfySource}</span> ·{' '}
                  <span className="font-mono">comfyui.api_url</span> · timeout{' '}
                  <span className="font-mono">{comfyTimeoutSource}</span> ·{' '}
                  <span className="font-mono">comfyui.timeout_sec</span>
                </p>
                {canWriteSettings && (
                  <button
                    type="button"
                    onClick={() => void saveComfySettings()}
                    disabled={settingsSaving}
                    className="rounded-lg bg-gov-blue-700 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
                  >
                    {settingsSaving ? 'Guardando…' : 'Guardar en DuckDB'}
                  </button>
                )}
                {settingsMsg && (
                  <p className="text-xs text-gov-blue-700 dark:text-dark-cyan">{settingsMsg}</p>
                )}
              </div>
            </section>
          </aside>
        </div>
      </div>
    </ViewChrome>
  );
}
