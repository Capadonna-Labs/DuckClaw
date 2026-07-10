'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import {
  CheckCircle2,
  ExternalLink,
  KeyRound,
  Loader2,
  LogIn,
  Plug,
  RefreshCw,
  TestTube2,
  Trash2,
  UserPlus,
} from 'lucide-react';
import type { TemplateSummary } from '@/types/admin';
import {
  adminService,
  type McpConnectorPreset,
  type McpConnectorSummary,
  type McpConnectorTestResult,
} from '@/services/adminService';
import { pollWriteTask } from '@/lib/pollWriteTask';

type McpConnectorsPanelProps = {
  canWrite: boolean;
};

export function McpConnectorsPanel({ canWrite }: McpConnectorsPanelProps) {
  const searchParams = useSearchParams();
  const [connectors, setConnectors] = useState<McpConnectorSummary[]>([]);
  const [presets, setPresets] = useState<McpConnectorPreset[]>([]);
  const [workers, setWorkers] = useState<TemplateSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [selectedPreset, setSelectedPreset] = useState('');
  const [authTokens, setAuthTokens] = useState<Record<string, string>>({});
  const [grantWorkerByConnector, setGrantWorkerByConnector] = useState<Record<string, string>>({});
  const [grantNotices, setGrantNotices] = useState<Record<string, string>>({});
  const [testResults, setTestResults] = useState<Record<string, McpConnectorTestResult>>({});

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    Promise.all([
      adminService.listMcpConnectors(),
      adminService.listMcpConnectorPresets(),
      adminService.listTemplates(),
    ])
      .then(([connectorRows, presetRows, workerRows]) => {
        setConnectors(connectorRows);
        setPresets(presetRows);
        setWorkers(workerRows.filter((w) => w.active !== false && w.status !== 'inactive'));
        if (!selectedPreset && presetRows.length > 0) {
          setSelectedPreset(presetRows[0].preset_id);
        }
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'No se pudieron cargar conectores'))
      .finally(() => setLoading(false));
  }, [selectedPreset]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const oauth = searchParams.get('oauth');
    if (oauth === 'success') {
      setError(null);
      load();
    } else if (oauth === 'error') {
      const msg = searchParams.get('msg') || 'OAuth falló';
      setError(decodeURIComponent(msg));
    }
  }, [searchParams, load]);

  const oauthRedirectUri = () =>
    `${window.location.origin}/api/admin/mcp/connectors/oauth/callback`;

  const connectHiggsfield = async (connectorId: string) => {
    if (busyId) return;
    setBusyId(`oauth:${connectorId}`);
    setError(null);
    try {
      const result = await adminService.startMcpConnectorOAuth(connectorId, oauthRedirectUri());
      window.location.href = result.authorization_url;
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo iniciar OAuth');
      setBusyId(null);
    }
  };

  const presetById = useMemo(
    () => Object.fromEntries(presets.map((preset) => [preset.preset_id, preset])),
    [presets]
  );

  const createFromPreset = async () => {
    if (!selectedPreset || busyId) return;
    setBusyId('create');
    setError(null);
    try {
      await adminService.createMcpConnector({ preset_id: selectedPreset });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo crear el conector');
    } finally {
      setBusyId(null);
    }
  };

  const saveAuth = async (connectorId: string) => {
    const token = (authTokens[connectorId] || '').trim();
    if (!token || busyId) return;
    setBusyId(connectorId);
    setError(null);
    try {
      await adminService.setMcpConnectorAuth(connectorId, token);
      setAuthTokens((prev) => ({ ...prev, [connectorId]: '' }));
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo guardar el token');
    } finally {
      setBusyId(null);
    }
  };

  const runTest = async (connectorId: string) => {
    if (busyId) return;
    setBusyId(`test:${connectorId}`);
    setError(null);
    try {
      const result = await adminService.testMcpConnector(connectorId);
      setTestResults((prev) => ({ ...prev, [connectorId]: result }));
    } catch (e) {
      setTestResults((prev) => ({
        ...prev,
        [connectorId]: {
          ok: false,
          connector_id: connectorId,
          transport: '',
          tool_count: 0,
          tools: [],
          error: e instanceof Error ? e.message : 'Test falló',
        },
      }));
    } finally {
      setBusyId(null);
    }
  };

  const grantWorker = async (connectorId: string) => {
    const workerId = grantWorkerByConnector[connectorId];
    if (!workerId || busyId) return;
    setBusyId(`grant:${connectorId}`);
    setError(null);
    setGrantNotices((prev) => {
      const next = { ...prev };
      delete next[connectorId];
      return next;
    });
    try {
      const result = await adminService.grantMcpConnector(connectorId, workerId);
      const polled = await pollWriteTask(result.task_id);
      if (polled.state === 'failed') {
        throw new Error(polled.detail || 'Grant no se aplicó en DB');
      }
      const connector = connectors.find((c) => c.connector_id === connectorId);
      const workerLabel = workers.find((w) => w.id === workerId)?.display_name || workerId;
      const skillHint =
        connector?.preset_id === 'higgsfield'
          ? ' Skill higgsfield activada en pestaña Agentes (manifest).'
          : connector?.preset_id
            ? ` Skill ${connector.preset_id} activada en manifest si aplica.`
            : '';
      setGrantNotices((prev) => ({
        ...prev,
        [connectorId]: `Grant aplicado a ${workerLabel}.${skillHint}`,
      }));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo asignar el worker');
    } finally {
      setBusyId(null);
    }
  };

  const deactivate = async (connectorId: string) => {
    if (busyId || !window.confirm(`¿Desactivar conector ${connectorId}?`)) return;
    setBusyId(`deactivate:${connectorId}`);
    setError(null);
    try {
      await adminService.deactivateMcpConnector(connectorId);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo desactivar');
    } finally {
      setBusyId(null);
    }
  };

  if (loading) {
    return <p className="text-sm text-gov-gray-500">Cargando conectores…</p>;
  }

  return (
    <div className="space-y-6">
      {error && (
        <p className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300">
          {error}
        </p>
      )}

      {canWrite && (
        <section className="rounded-3xl border border-gov-gray-100 bg-white p-5 shadow-sm dark:border-dark-border dark:bg-dark-surface">
          <h2 className="text-lg font-black text-gov-gray-900 dark:text-dark-text">Nuevo conector</h2>
          <p className="mt-1 text-sm text-gov-gray-500 dark:text-dark-muted">
            Elige un preset empaquetado. El ID será <span className="font-mono">mcp_&#123;preset&#125;</span>.
          </p>
          <div className="mt-4 flex flex-wrap items-end gap-3">
            <label className="flex flex-col gap-1 text-xs font-bold uppercase tracking-wide text-gov-gray-500">
              Preset
              <select
                value={selectedPreset}
                onChange={(e) => setSelectedPreset(e.target.value)}
                className="min-w-[220px] rounded-xl border border-gov-gray-200 bg-white px-3 py-2 text-sm font-normal normal-case dark:border-dark-border dark:bg-dark-bg"
              >
                {presets.map((preset) => (
                  <option key={preset.preset_id} value={preset.preset_id}>
                    {preset.display_name}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              onClick={createFromPreset}
              disabled={!selectedPreset || busyId === 'create'}
              className="inline-flex items-center gap-2 rounded-xl bg-gov-blue-700 px-4 py-2 text-sm font-bold text-white disabled:opacity-50 dark:bg-dark-cyan dark:text-dark-bg"
            >
              {busyId === 'create' ? <Loader2 size={16} className="animate-spin" /> : <Plug size={16} />}
              Crear conector
            </button>
          </div>
          {selectedPreset && presetById[selectedPreset] && (
            <PresetHint preset={presetById[selectedPreset]} />
          )}
        </section>
      )}

      <section className="space-y-4">
        {connectors.length === 0 ? (
          <div className="rounded-3xl border border-dashed border-gov-gray-200 p-8 text-center dark:border-dark-border">
            <p className="text-sm text-gov-gray-500">Sin conectores activos. Crea uno desde un preset.</p>
          </div>
        ) : (
          connectors.map((connector) => (
            <ConnectorCard
              key={connector.connector_id}
              connector={connector}
              canWrite={canWrite}
              workers={workers}
              busyId={busyId}
              authToken={authTokens[connector.connector_id] || ''}
              grantWorkerId={grantWorkerByConnector[connector.connector_id] || workers[0]?.id || ''}
              grantNotice={grantNotices[connector.connector_id]}
              testResult={testResults[connector.connector_id]}
              onAuthTokenChange={(value) =>
                setAuthTokens((prev) => ({ ...prev, [connector.connector_id]: value }))
              }
              onGrantWorkerChange={(value) =>
                setGrantWorkerByConnector((prev) => ({ ...prev, [connector.connector_id]: value }))
              }
              onSaveAuth={() => saveAuth(connector.connector_id)}
              onConnectOAuth={() => connectHiggsfield(connector.connector_id)}
              onTest={() => runTest(connector.connector_id)}
              onGrant={() => grantWorker(connector.connector_id)}
              onDeactivate={() => deactivate(connector.connector_id)}
            />
          ))
        )}
      </section>

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={load}
          className="inline-flex items-center gap-2 text-sm font-bold text-gov-blue-700 dark:text-dark-cyan"
        >
          <RefreshCw size={14} /> Actualizar
        </button>
        <Link href="/playground" className="text-sm font-bold text-gov-blue-700 dark:text-dark-cyan">
          Ir al Playground →
        </Link>
      </div>
    </div>
  );
}

function PresetHint({ preset }: { preset: McpConnectorPreset }) {
  const docsUrl = typeof preset.metadata?.docs_url === 'string' ? preset.metadata.docs_url : '';
  const authHint = typeof preset.metadata?.auth_hint === 'string' ? preset.metadata.auth_hint : '';
  const install = typeof preset.metadata?.install === 'string' ? preset.metadata.install : '';

  return (
    <div className="mt-4 rounded-2xl bg-gov-gray-50 p-4 text-sm dark:bg-dark-bg">
      <p>
        <span className="font-bold">Transporte:</span> {preset.transport}
        {preset.endpoint_url ? ` · ${preset.endpoint_url}` : ''}
      </p>
      {install && (
        <p className="mt-1 font-mono text-xs text-gov-gray-600 dark:text-dark-muted">{install}</p>
      )}
      {authHint && <p className="mt-2 text-gov-gray-600 dark:text-dark-muted">{authHint}</p>}
      {docsUrl && (
        <a
          href={docsUrl}
          target="_blank"
          rel="noreferrer"
          className="mt-2 inline-flex items-center gap-1 text-xs font-bold text-gov-blue-700 dark:text-dark-cyan"
        >
          Documentación <ExternalLink size={12} />
        </a>
      )}
    </div>
  );
}

function ConnectorCard({
  connector,
  canWrite,
  workers,
  busyId,
  authToken,
  grantWorkerId,
  grantNotice,
  testResult,
  onAuthTokenChange,
  onGrantWorkerChange,
  onSaveAuth,
  onConnectOAuth,
  onTest,
  onGrant,
  onDeactivate,
}: {
  connector: McpConnectorSummary;
  canWrite: boolean;
  workers: TemplateSummary[];
  busyId: string | null;
  authToken: string;
  grantWorkerId: string;
  grantNotice?: string;
  testResult?: McpConnectorTestResult;
  onAuthTokenChange: (value: string) => void;
  onGrantWorkerChange: (value: string) => void;
  onSaveAuth: () => void;
  onConnectOAuth: () => void;
  onTest: () => void;
  onGrant: () => void;
  onDeactivate: () => void;
}) {
  const needsBearer = connector.auth_kind === 'bearer' || connector.preset_id === 'higgsfield';
  const isHiggsfield = connector.preset_id === 'higgsfield';
  const authReady = !needsBearer || connector.has_auth;
  const showAuthBadge = needsBearer || isHiggsfield;

  return (
    <article className="rounded-3xl border border-gov-gray-100 bg-white p-5 shadow-sm dark:border-dark-border dark:bg-dark-surface">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-lg font-black text-gov-gray-900 dark:text-dark-text">
            {connector.display_name}
          </h3>
          <p className="mt-1 font-mono text-xs text-gov-gray-500">{connector.connector_id}</p>
          <p className="mt-2 text-sm text-gov-gray-600 dark:text-dark-muted">
            {connector.transport}
            {connector.endpoint_url ? ` · ${connector.endpoint_url}` : ''}
            {connector.preset_id ? ` · preset ${connector.preset_id}` : ''}
          </p>
        </div>
        <div className="flex flex-wrap gap-2 text-xs font-bold">
          <span
            className={
              connector.enabled
                ? 'rounded-full bg-green-100 px-2 py-1 text-green-800 dark:bg-green-950/40 dark:text-green-300'
                : 'rounded-full bg-gov-gray-100 px-2 py-1 text-gov-gray-600'
            }
          >
            {connector.enabled ? 'habilitado' : 'deshabilitado'}
          </span>
          {showAuthBadge && (
            <span
              className={
                connector.has_auth
                  ? 'rounded-full bg-green-100 px-2 py-1 text-green-800 dark:bg-green-950/40 dark:text-green-300'
                  : 'rounded-full bg-amber-100 px-2 py-1 text-amber-800'
              }
            >
              {connector.has_auth ? 'auth OK' : isHiggsfield ? 'falta OAuth' : 'falta Bearer'}
            </span>
          )}
        </div>
      </div>

      {canWrite && isHiggsfield && (
        <div className="mt-4 rounded-2xl border border-gov-gray-100 p-4 dark:border-dark-border">
          <div className="flex items-center gap-2 text-sm font-bold">
            <LogIn size={16} /> Conectar cuenta Higgsfield
          </div>
          <p className="mt-2 text-xs text-gov-gray-600 dark:text-dark-muted">
            Inicia sesión con tu cuenta Higgsfield desde DuckClaw. La sesión queda guardada en el servidor para
            workers con skill <code className="font-mono">higgsfield</code>.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={onConnectOAuth}
              disabled={busyId === `oauth:${connector.connector_id}`}
              className="inline-flex items-center gap-2 rounded-xl bg-gov-blue-700 px-4 py-2 text-sm font-bold text-white disabled:opacity-50 dark:bg-dark-cyan dark:text-dark-bg"
            >
              {busyId === `oauth:${connector.connector_id}` ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <LogIn size={14} />
              )}
              {connector.has_auth ? 'Reconectar Higgsfield' : 'Conectar Higgsfield'}
            </button>
          </div>
        </div>
      )}

      {canWrite && needsBearer && !isHiggsfield && (
        <div className="mt-4 rounded-2xl border border-gov-gray-100 p-4 dark:border-dark-border">
          <div className="flex items-center gap-2 text-sm font-bold">
            <KeyRound size={16} /> Token Bearer
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <input
              type="password"
              value={authToken}
              onChange={(e) => onAuthTokenChange(e.target.value)}
              placeholder="Bearer token…"
              className="min-w-[280px] flex-1 rounded-xl border border-gov-gray-200 px-3 py-2 text-sm dark:border-dark-border dark:bg-dark-bg"
            />
            <button
              type="button"
              onClick={onSaveAuth}
              disabled={!authToken.trim() || busyId === connector.connector_id}
              className="rounded-xl border px-4 py-2 text-sm font-bold disabled:opacity-50"
            >
              Guardar token
            </button>
          </div>
        </div>
      )}

      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={onTest}
          disabled={!authReady || busyId === `test:${connector.connector_id}`}
          className="inline-flex items-center gap-2 rounded-xl border px-3 py-2 text-sm font-bold disabled:opacity-50"
        >
          {busyId === `test:${connector.connector_id}` ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <TestTube2 size={14} />
          )}
          Probar list_tools
        </button>

        {canWrite && (
          <>
            <select
              value={grantWorkerId}
              onChange={(e) => onGrantWorkerChange(e.target.value)}
              className="rounded-xl border border-gov-gray-200 px-3 py-2 text-sm dark:border-dark-border dark:bg-dark-bg"
            >
              {workers.map((worker) => (
                <option key={worker.id} value={worker.id}>
                  {worker.name || worker.id}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={onGrant}
              disabled={!grantWorkerId || busyId === `grant:${connector.connector_id}`}
              className="inline-flex items-center gap-2 rounded-xl bg-gov-blue-700 px-3 py-2 text-sm font-bold text-white disabled:opacity-50 dark:bg-dark-cyan dark:text-dark-bg"
            >
              <UserPlus size={14} /> Grant worker
            </button>
            <button
              type="button"
              onClick={onDeactivate}
              disabled={busyId === `deactivate:${connector.connector_id}`}
              className="inline-flex items-center gap-2 rounded-xl border border-red-200 px-3 py-2 text-sm font-bold text-red-700 disabled:opacity-50"
            >
              <Trash2 size={14} /> Desactivar
            </button>
          </>
        )}
      </div>

      {grantNotice && (
        <div className="mt-4 rounded-2xl border border-green-200 bg-green-50 p-4 text-sm text-green-900 dark:border-green-900/50 dark:bg-green-950/20 dark:text-green-200">
          <div className="flex items-center gap-2 font-bold">
            <CheckCircle2 size={16} />
            {grantNotice}
          </div>
        </div>
      )}

      {testResult && (
        <div
          className={`mt-4 rounded-2xl p-4 text-sm ${
            testResult.ok
              ? 'border border-green-200 bg-green-50 text-green-900 dark:border-green-900/50 dark:bg-green-950/20 dark:text-green-200'
              : 'border border-red-200 bg-red-50 text-red-800 dark:border-red-900/50 dark:bg-red-950/20 dark:text-red-200'
          }`}
        >
          <div className="flex items-center gap-2 font-bold">
            {testResult.ok ? <CheckCircle2 size={16} /> : <TestTube2 size={16} />}
            {testResult.ok
              ? `${testResult.tool_count} tools detectadas`
              : testResult.error || 'Test falló'}
          </div>
          {testResult.tools.length > 0 && (
            <ul className="mt-2 max-h-40 space-y-1 overflow-y-auto font-mono text-xs">
              {testResult.tools.map((tool) => (
                <li key={tool.name}>{tool.name}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </article>
  );
}
