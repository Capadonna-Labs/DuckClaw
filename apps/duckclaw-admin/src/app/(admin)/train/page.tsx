'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  adminService,
  type TrainPipelineResult,
  type TrainStatus,
  type TrainTraceFile,
} from '@/services/adminService';
import SettingsSection from '@/components/settings/SettingsSection';
import { GraduationCap, Database, Play, ChevronDown, ChevronRight } from 'lucide-react';
import { clampInput, LIMITS } from '@/lib/validation';

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function PipelineOutput({ result }: { result: TrainPipelineResult | null }) {
  if (!result) return null;
  const text = [
    result.exit_code !== undefined ? `exit_code: ${result.exit_code}` : '',
    result.records !== undefined ? `records: ${result.records}` : '',
    result.stats ? `stats: ${JSON.stringify(result.stats, null, 2)}` : '',
    result.stdout ? `--- stdout ---\n${result.stdout}` : '',
    result.stderr ? `--- stderr ---\n${result.stderr}` : '',
  ]
    .filter(Boolean)
    .join('\n\n');
  return (
    <pre className="mt-3 p-3 rounded-xl bg-gov-gray-50 dark:bg-dark-bg text-xs font-mono whitespace-pre-wrap max-h-64 overflow-y-auto">
      {text || '(sin salida)'}
    </pre>
  );
}

function TraceTable({
  title,
  files,
  lake,
  onSample,
}: {
  title: string;
  files: TrainTraceFile[];
  lake: 'conversation_traces' | 'gemma4';
  onSample: (lake: 'conversation_traces' | 'gemma4', path: string) => void;
}) {
  if (!files.length) {
    return <p className="text-sm text-gov-gray-500">Sin archivos recientes.</p>;
  }
  return (
    <div>
      <p className="text-xs font-bold text-gov-gray-500 mb-2">{title}</p>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-left text-gov-gray-500 border-b dark:border-dark-border">
              <th className="py-2 pr-2">Ruta</th>
              <th className="py-2 pr-2">Líneas</th>
              <th className="py-2 pr-2">Tamaño</th>
              <th className="py-2" />
            </tr>
          </thead>
          <tbody>
            {files.map((f) => (
              <tr key={f.relative_path} className="border-b dark:border-dark-border/50">
                <td className="py-2 pr-2 font-mono">{f.relative_path}</td>
                <td className="py-2 pr-2">{f.line_count >= 0 ? f.line_count : '—'}</td>
                <td className="py-2 pr-2">{formatBytes(f.size_bytes)}</td>
                <td className="py-2">
                  <button
                    type="button"
                    onClick={() => onSample(lake, f.relative_path)}
                    className="text-gov-blue-700 dark:text-gov-blue-400 font-semibold hover:underline"
                  >
                    Muestra
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function TrainPage() {
  const [status, setStatus] = useState<TrainStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<TrainPipelineResult | null>(null);
  const [requireValidSql, setRequireValidSql] = useState(true);
  const [sanitizeDryRun, setSanitizeDryRun] = useState(false);
  const [useLoraConfig, setUseLoraConfig] = useState(true);
  const [sampleJson, setSampleJson] = useState<string | null>(null);
  const [redisOpen, setRedisOpen] = useState(false);
  const [tenantId, setTenantId] = useState('default');
  const [sessionId, setSessionId] = useState('');
  const [redisMessages, setRedisMessages] = useState<unknown[]>([]);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const s = await adminService.getTrainStatus();
      setStatus(s);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const runAction = async (id: string, fn: () => Promise<TrainPipelineResult>) => {
    setRunning(id);
    setError(null);
    setLastResult(null);
    try {
      const r = await fn();
      setLastResult(r);
      if (r.exit_code !== undefined && r.exit_code !== 0) {
        setError(`Comando terminó con código ${r.exit_code}`);
      }
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error');
    } finally {
      setRunning(null);
    }
  };

  const loadSample = async (lake: 'conversation_traces' | 'gemma4', relativePath: string) => {
    setError(null);
    setSampleJson(null);
    try {
      const r = await adminService.getTrainTraceSample(lake, relativePath, 3);
      setSampleJson(JSON.stringify(r.samples, null, 2));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error');
    }
  };

  const loadRedis = async () => {
    setError(null);
    try {
      const r = await adminService.getChatHistory(tenantId, sessionId);
      setRedisMessages(r.messages ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error');
    }
  };

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-3xl font-black dark:text-dark-text">Train</h1>
        <p className="text-sm text-gov-gray-500 mt-1">
          SFT / GRPO · conversation_traces · Gemma4 · MLX LoRA
        </p>
      </header>

      {error && <p className="text-red-600 text-sm">{error}</p>}

      <SettingsSection
        titulo="Estado del pipeline"
        descripcion={
          status ? `Formato de captura: ${status.trace_format}` : 'Cargando rutas y conteos…'
        }
        icono={<GraduationCap size={22} />}
      >
        {loading && <p className="text-sm text-gov-gray-500">Cargando…</p>}
        {status && (
          <div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
              {Object.entries(status.paths).map(([k, v]) => (
                <div key={k}>
                  <p className="text-[10px] uppercase font-bold text-gov-gray-500">{k}</p>
                  <p className="font-mono text-xs break-all">{v}</p>
                </div>
              ))}
              <div>
                <p className="text-[10px] uppercase font-bold text-gov-gray-500">dataset_sft</p>
                <p>
                  {status.files.dataset_sft?.exists
                    ? formatBytes(status.files.dataset_sft.size_bytes ?? 0)
                    : 'no existe'}
                </p>
              </div>
              <div>
                <p className="text-[10px] uppercase font-bold text-gov-gray-500">train.jsonl</p>
                <p>
                  {status.files.train_jsonl?.exists
                    ? formatBytes(status.files.train_jsonl.size_bytes ?? 0)
                    : 'no existe'}
                </p>
              </div>
            </div>
          </div>
        )}
        <button
          type="button"
          onClick={() => {
            setLoading(true);
            refresh();
          }}
          className="mt-4 text-sm font-bold text-gov-blue-700 dark:text-gov-blue-400"
        >
          Actualizar estado
        </button>
      </SettingsSection>

      <SettingsSection
        titulo="Acciones SFT"
        descripcion="Collect → sanitize → materialize → entrenar (puede tardar horas)"
        icono={<Play size={22} />}
      >
        <div className="flex flex-wrap gap-2 items-center mb-4">
          <label className="flex items-center gap-2 text-xs">
            <input
              type="checkbox"
              checked={requireValidSql}
              onChange={(e) => setRequireValidSql(e.target.checked)}
            />
            SQL válido en collect
          </label>
          <label className="flex items-center gap-2 text-xs">
            <input
              type="checkbox"
              checked={sanitizeDryRun}
              onChange={(e) => setSanitizeDryRun(e.target.checked)}
            />
            Sanitize dry-run
          </label>
          <label className="flex items-center gap-2 text-xs">
            <input
              type="checkbox"
              checked={useLoraConfig}
              onChange={(e) => setUseLoraConfig(e.target.checked)}
            />
            duckops train -c lora_config.yaml
          </label>
        </div>
        <div className="flex flex-wrap gap-2">
          {[
            {
              id: 'collect',
              label: '1. Collect SFT',
              fn: () => adminService.trainCollect(requireValidSql),
            },
            {
              id: 'sanitize',
              label: '2. Sanitize Gemma4',
              fn: () => adminService.trainSanitize(sanitizeDryRun),
            },
            {
              id: 'materialize',
              label: '3. Materialize',
              fn: () => adminService.trainMaterialize(),
            },
            {
              id: 'run',
              label: '4. Run MLX',
              fn: () => adminService.trainRun(useLoraConfig),
            },
          ].map((a) => (
            <button
              key={a.id}
              type="button"
              disabled={running !== null}
              onClick={() => runAction(a.id, a.fn)}
              className="px-4 py-2 bg-gov-blue-700 text-white rounded-xl text-sm font-bold disabled:opacity-50"
            >
              {running === a.id ? 'Ejecutando…' : a.label}
            </button>
          ))}
        </div>
        <PipelineOutput result={lastResult} />
        {status?.pipeline.sft && (
          <ol className="mt-4 list-decimal list-inside text-xs text-gov-gray-600 dark:text-gov-gray-400 space-y-1">
            {status.pipeline.sft.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
        )}
      </SettingsSection>

      <SettingsSection
        titulo="Explorador de trazas"
        descripcion="Archivos traces.jsonl recientes en el datalake"
        icono={<Database size={22} />}
      >
        {status && (
          <>
            <TraceTable
              title={`conversation_traces (${status.conversation_traces.file_count} archivos)`}
              files={status.conversation_traces.recent}
              lake="conversation_traces"
              onSample={loadSample}
            />
            <div className="mt-6">
              <TraceTable
                title={`gemma4 sanitizado (${status.gemma4_sanitized.file_count} archivos)`}
                files={status.gemma4_sanitized.recent}
                lake="gemma4"
                onSample={loadSample}
              />
            </div>
          </>
        )}
        {sampleJson && (
          <pre className="mt-4 p-3 rounded-xl bg-gov-gray-50 dark:bg-dark-bg text-xs font-mono whitespace-pre-wrap max-h-80 overflow-y-auto">
            {sampleJson}
          </pre>
        )}
      </SettingsSection>

      <SettingsSection
        titulo="GRPO (alternativa)"
        descripcion="Group Relative Policy Optimization — captura con reward_metadata"
        icono={<GraduationCap size={22} />}
      >
        <p className="text-sm text-gov-gray-600 dark:text-gov-gray-400 mb-2">
          En <code className="font-mono text-xs">.env</code> del gateway:
        </p>
        <pre className="p-3 rounded-xl bg-gov-gray-50 dark:bg-dark-bg text-xs font-mono">
          DUCKCLAW_CONVERSATION_TRACES_FORMAT=grpo
        </pre>
        {status?.pipeline.grpo && (
          <ul className="mt-3 list-disc list-inside text-xs text-gov-gray-600 dark:text-gov-gray-400">
            {status.pipeline.grpo.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        )}
        <p className="mt-3 text-xs text-gov-gray-500">
          Spec: specs/features/platform/SFT_DATASET_FORMAT.md (§3)
        </p>
      </SettingsSection>

      <section className="rounded-3xl border dark:border-dark-border overflow-hidden">
        <button
          type="button"
          onClick={() => setRedisOpen((o) => !o)}
          className="w-full flex items-center gap-2 px-6 py-4 text-left font-bold dark:text-dark-text bg-white dark:bg-dark-surface"
        >
          {redisOpen ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
          Sesión Redis (debug)
        </button>
        {redisOpen && (
          <div>
            <div className="px-6 pb-6 space-y-3 border-t dark:border-dark-border pt-4">
              <p className="text-xs text-gov-gray-500">
                Historial por tenant/session (no es el datalake conversation_traces).
              </p>
              <div className="flex flex-wrap gap-2">
                <input
                  value={tenantId}
                  onChange={(e) => setTenantId(clampInput(e.target.value, LIMITS.tenantId))}
                  maxLength={LIMITS.tenantId}
                  className="px-3 py-2 border rounded-xl dark:border-dark-border dark:bg-dark-bg text-sm"
                  placeholder="tenant_id"
                />
                <input
                  value={sessionId}
                  onChange={(e) => setSessionId(clampInput(e.target.value, LIMITS.sessionId))}
                  maxLength={LIMITS.sessionId}
                  className="flex-1 min-w-[200px] px-3 py-2 border rounded-xl dark:border-dark-border dark:bg-dark-bg text-sm font-mono"
                  placeholder="session_id / chat_id"
                />
                <button
                  type="button"
                  onClick={loadRedis}
                  className="px-4 py-2 bg-gov-gray-700 text-white rounded-xl text-sm font-bold"
                >
                  Cargar
                </button>
              </div>
              <ul className="space-y-2 max-h-[320px] overflow-y-auto text-sm">
                {redisMessages.map((m, i) => (
                  <li
                    key={i}
                    className="p-3 rounded-xl bg-gov-gray-50 dark:bg-dark-bg font-mono text-xs whitespace-pre-wrap"
                  >
                    {JSON.stringify(m, null, 2)}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
