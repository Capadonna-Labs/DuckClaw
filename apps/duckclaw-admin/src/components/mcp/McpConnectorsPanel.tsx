'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import {
  CheckCircle2,
  KeyRound,
  Loader2,
  LogIn,
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
import {
  presetUsesOAuthPkce,
} from '@/lib/mcpPresetAuth';

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
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'No se pudieron cargar conectores'))
      .finally(() => setLoading(false));
  }, []);

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

  const connectOAuth = async (connectorId: string) => {
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
      const presetId = connector?.preset_id?.trim();
      const skillHint = presetId
        ? ` Skill ${presetId} activada en manifest si aplica.`
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

      <section className="space-y-4">
        {connectors.length === 0 ? (
          <div className="rounded-3xl border border-dashed border-gov-gray-200 p-8 text-center dark:border-dark-border">
            <p className="text-sm text-gov-gray-500">
              Sin conectores activos. Crea uno en la pestaña <strong className="font-bold">Configuración</strong>.
            </p>
          </div>
        ) : (
          connectors.map((connector) => (
            <ConnectorCard
              key={connector.connector_id}
              connector={connector}
              preset={connector.preset_id ? presetById[connector.preset_id] : undefined}
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
              onConnectOAuth={() => connectOAuth(connector.connector_id)}
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

function ConnectorCard({
  connector,
  preset,
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
  preset?: McpConnectorPreset;
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
  const usesOAuth = presetUsesOAuthPkce(preset);
  const needsBearer = connector.auth_kind === 'bearer' && !usesOAuth;
  const needsAuth = needsBearer || usesOAuth;
  const authReady = !needsAuth || connector.has_auth;
  const showAuthBadge = needsAuth;

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
              {connector.has_auth ? 'auth OK' : usesOAuth ? 'falta OAuth' : 'falta Bearer'}
            </span>
          )}
        </div>
      </div>

      {canWrite && usesOAuth && (
        <div className="mt-4 rounded-2xl border border-gov-gray-100 p-4 dark:border-dark-border">
          <div className="flex items-center gap-2 text-sm font-bold">
            <LogIn size={16} /> Conectar OAuth (PKCE)
          </div>
          <p className="mt-2 text-xs text-gov-gray-600 dark:text-dark-muted">
            Inicia sesión con el proveedor del conector. La sesión queda en el servidor para los workers con la
            skill <code className="font-mono">{connector.preset_id || connector.connector_id}</code>.
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
              {connector.has_auth ? 'Reconectar OAuth' : 'Conectar OAuth'}
            </button>
          </div>
        </div>
      )}

      {canWrite && needsBearer && (
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
