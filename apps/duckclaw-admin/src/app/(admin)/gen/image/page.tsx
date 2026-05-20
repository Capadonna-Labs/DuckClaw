'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { PageShell } from '@/components/admin/PageShell';
import SettingsSection from '@/components/settings/SettingsSection';
import { adminService } from '@/services/adminService';
import { friendlyGatewayError } from '@/lib/adminErrors';
import { parseArtifactIdFromPath } from '@/lib/artifactPreview';
import { Image, RefreshCw, Sparkles } from 'lucide-react';

const ASPECT_FALLBACK = ['1:1', '16:9', '9:16', '4:3', '3:4'];

function formatElapsedSec(ms: number): string {
  return `${(ms / 1000).toFixed(2)} s`;
}

export default function GenImagePage() {
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
      setTemplates(tpl.templates);
      setDefaultTemplate(tpl.default || 'comfy_default');
      setTemplate((prev) => prev || tpl.default || 'comfy_default');
      if (cfg.effective_tenant_id) setTenantId(cfg.effective_tenant_id);
      setError(null);
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Error al cargar';
      setError(
        msg.includes('404') || msg.includes('502')
          ? `${friendlyGatewayError(msg)} Si ComfyUI corre en PM2 pero el estado falla, recarga esta página; si Generar falla, reinicia el Gateway.`
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
      } else {
        setError(null);
      }
      await loadMeta();
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Error en operación PM2';
      setError(
        msg === opId || msg.includes('Comando no permitido')
          ? `PM2 local: ${msg}. Reinicia el admin (pnpm dev) o ejecuta en el Mac: pm2 ${opId.replace('pm2_', '').replace(/_/g, ' ')}`
          : msg
      );
    } finally {
      setOpsBusy(null);
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
    <PageShell>
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-black dark:text-dark-text">Image</h1>
          <p className="text-sm text-gov-gray-500 dark:text-dark-muted mt-1">
            Generación txt2img vía ComfyUI ({status?.url || 'COMFYUI_API_URL'})
          </p>
        </div>
        <button
          type="button"
          onClick={() => void loadMeta()}
          className="inline-flex items-center gap-2 px-3 py-2 text-sm rounded-lg border border-gov-gray-200 dark:border-dark-border hover:bg-gov-gray-50 dark:hover:bg-dark-bg"
        >
          <RefreshCw size={16} />
          Actualizar estado
        </button>
      </header>

      {error && (
        <p className="text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950/40 px-3 py-2 rounded-lg">
          {error}
        </p>
      )}

      <SettingsSection
        titulo="Servicio ComfyUI"
        descripcion="PM2 y health check del API local"
        icono={<Sparkles size={22} />}
      >
        <div className="flex flex-wrap items-center gap-3 mb-4">
          <span
            className={`inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-semibold ${
              comfyOnline
                ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200'
                : 'bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-100'
            }`}
          >
            {comfyOnline ? 'Online' : 'Offline'}
            {status?.latency_ms != null && comfyOnline ? ` · ${status.latency_ms} ms` : ''}
          </span>
          {status?.error && !comfyOnline && (
            <span className="text-xs text-gov-gray-500">{status.error}</span>
          )}
          {comfyOnline && !checkpointsReady && (
            <span className="text-xs text-amber-800 dark:text-amber-200">
              Sin checkpoints: copia un .safetensors en{' '}
              <code className="text-[10px]">COMFYUI_HOME/models/checkpoints/</code> y reinicia ComfyUI.
            </span>
          )}
          {comfyOnline && checkpointsReady && status?.checkpoints?.length ? (
            <span className="text-xs text-gov-gray-500">
              Checkpoints: {status.checkpoints.slice(0, 3).join(', ')}
              {status.checkpoints.length > 3 ? ` (+${status.checkpoints.length - 3})` : ''}
            </span>
          ) : null}
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={opsBusy !== null}
            onClick={() => void runOp('pm2_start_comfyui')}
            className="px-3 py-2 text-sm font-medium rounded-lg bg-gov-blue-700 text-white hover:bg-gov-blue-800 disabled:opacity-50"
          >
            {opsBusy === 'pm2_start_comfyui' ? 'Iniciando…' : 'Iniciar ComfyUI (PM2)'}
          </button>
          <button
            type="button"
            disabled={opsBusy !== null}
            onClick={() => void runOp('pm2_restart_comfyui')}
            className="px-3 py-2 text-sm font-medium rounded-lg border border-gov-gray-300 dark:border-dark-border hover:bg-gov-gray-50 dark:hover:bg-dark-bg disabled:opacity-50"
          >
            {opsBusy === 'pm2_restart_comfyui' ? 'Reiniciando…' : 'Reiniciar ComfyUI'}
          </button>
        </div>
        <p className="text-xs text-gov-gray-500 mt-3">
          Define <code className="text-[10px]">COMFYUI_HOME</code> en .env si no usas{' '}
          <code className="text-[10px]">~/ComfyUI</code>. Tras cambiar .env:{' '}
          <code className="text-[10px]">pm2 restart DuckClaw-Gateway --update-env</code>
        </p>
      </SettingsSection>

      <SettingsSection
        titulo="Generar imagen"
        descripcion="Workflow API comfy_default (u otro template)"
        icono={<Image size={22} />}
      >
        <div className="grid gap-4 max-w-2xl">
          <label className="block text-sm">
            <span className="font-medium">Prompt</span>
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              rows={4}
              className="mt-1 w-full rounded-lg border border-gov-gray-200 dark:border-dark-border bg-white dark:bg-dark-bg px-3 py-2 text-sm"
              placeholder="Describe la imagen…"
            />
          </label>
          <label className="block text-sm">
            <span className="font-medium">Negative prompt</span>
            <input
              value={negativePrompt}
              onChange={(e) => setNegativePrompt(e.target.value)}
              className="mt-1 w-full rounded-lg border border-gov-gray-200 dark:border-dark-border bg-white dark:bg-dark-bg px-3 py-2 text-sm"
            />
          </label>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <label className="block text-sm">
              <span className="font-medium">Template</span>
              <select
                value={template}
                onChange={(e) => setTemplate(e.target.value)}
                className="mt-1 w-full rounded-lg border border-gov-gray-200 dark:border-dark-border bg-white dark:bg-dark-bg px-3 py-2 text-sm"
              >
                {(templates.length ? templates : [{ id: defaultTemplate, label: defaultTemplate, aspect_ratios: ASPECT_FALLBACK }]).map(
                  (t) => (
                    <option key={t.id} value={t.id}>
                      {t.label}
                    </option>
                  )
                )}
              </select>
            </label>
            <label className="block text-sm">
              <span className="font-medium">Aspect ratio</span>
              <select
                value={aspectRatio}
                onChange={(e) => setAspectRatio(e.target.value)}
                className="mt-1 w-full rounded-lg border border-gov-gray-200 dark:border-dark-border bg-white dark:bg-dark-bg px-3 py-2 text-sm"
              >
                {aspectOptions.map((ar) => (
                  <option key={ar} value={ar}>
                    {ar}
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-sm">
              <span className="font-medium">Tenant</span>
              <input
                value={tenantId}
                onChange={(e) => setTenantId(e.target.value)}
                className="mt-1 w-full rounded-lg border border-gov-gray-200 dark:border-dark-border bg-white dark:bg-dark-bg px-3 py-2 text-sm"
              />
            </label>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              disabled={loading || !canGenerate}
              onClick={() => void onGenerate()}
              className="inline-flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-semibold rounded-lg bg-gov-blue-700 text-white hover:bg-gov-blue-800 disabled:opacity-50"
            >
              {loading ? 'Generando…' : 'Generar'}
            </button>
            {loading && (
              <span className="text-sm font-medium text-gov-gray-600 dark:text-dark-muted tabular-nums">
                Tiempo transcurrido: {formatElapsedSec(generatingElapsedMs)}
              </span>
            )}
          </div>
        </div>
      </SettingsSection>

      {result && (
        <SettingsSection
          titulo="Resultado"
          descripcion="Artefacto guardado en el vault del tenant"
          icono={<Image size={22} />}
        >
          {previewSrc ? (
            <img
              src={previewSrc}
              alt="Generada por ComfyUI"
              className="max-w-full max-h-[min(70vh,640px)] w-auto rounded-xl border border-gov-gray-200 dark:border-dark-border mb-3 shadow-sm"
            />
          ) : (
            <p className="text-sm text-amber-800 dark:text-amber-200 mb-3">
              Imagen generada en disco; no se pudo cargar la vista previa.
              {result.artifact_id ? ` ID: ${result.artifact_id}` : ''}
            </p>
          )}
          {result.file_path && (
            <p className="text-xs font-mono text-gov-gray-600 dark:text-dark-muted break-all">
              {result.file_path}
            </p>
          )}
          {result.prompt_id && (
            <p className="text-xs text-gov-gray-500 mt-1">prompt_id: {result.prompt_id}</p>
          )}
          {result.elapsedMs != null && (
            <p className="text-sm font-medium text-gov-gray-600 dark:text-dark-muted mt-2 tabular-nums">
              Tiempo de generación: {formatElapsedSec(result.elapsedMs)}
            </p>
          )}
        </SettingsSection>
      )}
    </PageShell>
  );
}
