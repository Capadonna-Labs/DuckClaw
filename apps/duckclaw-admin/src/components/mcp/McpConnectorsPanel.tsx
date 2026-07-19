'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import {
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  KeyRound,
  Loader2,
  LogIn,
  RefreshCw,
  Search,
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
import ConfirmModal from '@/components/admin/ConfirmModal';
import EmptyState from '@/components/shared/EmptyState';
import { McpNewConnectorSection } from '@/components/mcp/McpNewConnectorSection';
import {
  filterMcpConnectors,
  looksLikeAutofillEmail,
  MCP_CONNECTORS_PAGE_SIZE,
} from '@/lib/mcpConnectorsList';
import { presetUsesOAuthPkce } from '@/lib/mcpPresetAuth';
import { paginateItems } from '@/lib/pagination';

type McpConnectorsPanelProps = {
  canWrite: boolean;
};

const MCP_CONNECTOR_FILTER_INPUT_ID = 'mcp-connector-filter';

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
  /** worker_id → connector_ids con grant activo */
  const [grantsByWorker, setGrantsByWorker] = useState<Record<string, string[]>>({});
  const [testResults, setTestResults] = useState<Record<string, McpConnectorTestResult>>({});
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const autofillClearedRef = useRef(false);

  const refreshGrants = useCallback(async (workerRows: TemplateSummary[]) => {
    if (workerRows.length === 0) {
      setGrantsByWorker({});
      return;
    }
    const entries = await Promise.all(
      workerRows.map(async (worker) => {
        try {
          const payload = await adminService.getWorkerMcpGrants(worker.id);
          const granted = (payload.connectors ?? [])
            .filter((row) => row.granted)
            .map((row) => row.connector_id);
          return [worker.id, granted] as const;
        } catch {
          return [worker.id, [] as string[]] as const;
        }
      })
    );
    setGrantsByWorker(Object.fromEntries(entries));
  }, []);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    return Promise.all([
      adminService.listMcpConnectors(),
      adminService.listMcpConnectorPresets(),
      adminService.listTemplates(),
    ])
      .then(async ([connectorRows, presetRows, workerRows]) => {
        const activeWorkers = workerRows.filter((w) => w.active !== false && w.status !== 'inactive');
        setConnectors(connectorRows);
        setPresets(presetRows);
        setWorkers(activeWorkers);
        setPage(1);
        await refreshGrants(activeWorkers);
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'No se pudieron cargar conectores'))
      .finally(() => setLoading(false));
  }, [refreshGrants]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (loading || autofillClearedRef.current || connectors.length === 0) return;
    const input = searchInputRef.current;
    if (!input) return;
    const domValue = input.value;
    const reactValue = query;
    const domLooksLikeEmail = looksLikeAutofillEmail(domValue);
    const reactLooksLikeEmail = looksLikeAutofillEmail(reactValue);

    if (domLooksLikeEmail || reactLooksLikeEmail) {
      autofillClearedRef.current = true;
      setQuery('');
      input.value = '';
      return;
    }
  }, [loading, query, connectors.length]);

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
      const connector = connectors.find((c) => c.connector_id === connectorId);
      const preset = connector?.preset_id ? presetById[connector.preset_id] : undefined;
      const isGoogleWorkspace =
        preset?.metadata?.oauth_provider === 'google_workspace' ||
        (connector?.preset_id || '').startsWith('google_');
      const result = await adminService.startMcpConnectorOAuth(
        connectorId,
        isGoogleWorkspace ? '' : oauthRedirectUri()
      );
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

  const filteredConnectors = useMemo(
    () => filterMcpConnectors(connectors, query),
    [connectors, query]
  );

  const paginated = useMemo(
    () => paginateItems(filteredConnectors, page, MCP_CONNECTORS_PAGE_SIZE),
    [filteredConnectors, page]
  );

  useEffect(() => {
    setPage(1);
  }, [query]);

  useEffect(() => {
    if (page !== paginated.currentPage) setPage(paginated.currentPage);
  }, [page, paginated.currentPage]);

  const visibleStart =
    paginated.totalItems === 0 ? 0 : (paginated.currentPage - 1) * MCP_CONNECTORS_PAGE_SIZE + 1;
  const visibleEnd = Math.min(paginated.currentPage * MCP_CONNECTORS_PAGE_SIZE, paginated.totalItems);

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
    const workerId = grantWorkerByConnector[connectorId] || workers[0]?.id;
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
      if (polled.state === 'timeout' || polled.state === 'not_found') {
        throw new Error(
          polled.state === 'timeout'
            ? 'Grant encolado pero no se confirmó (db-writer / lock DuckDB). Revisa PM2 y reintenta.'
            : 'No se encontró el estado del grant. Refresca la vista o reintenta.'
        );
      }
      const connector = connectors.find((c) => c.connector_id === connectorId);
      const workerLabel = workers.find((w) => w.id === workerId)?.name || workerId;
      const presetId = connector?.preset_id?.trim();
      const skillHint = presetId
        ? ` Skill ${presetId} activada en manifest si aplica.`
        : '';
      const alreadyHad = (grantsByWorker[workerId] || []).includes(connectorId);
      await refreshGrants(workers);
      // Runtime puede cachear el grafo del worker hasta el próximo chat.
      await adminService.releaseWorkerGraphCache().catch(() => undefined);
      setGrantNotices((prev) => ({
        ...prev,
        [connectorId]: alreadyHad
          ? `Grant ya existía para ${workerLabel} (re-aplicar = UPSERT, sin duplicar). Abre un chat nuevo para cargar tools.`
          : `Grant aplicado a ${workerLabel}. Tools MCP disponibles en un chat nuevo (no hace falta “Grant” otra vez).${skillHint}`,
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

      {canWrite ? (
        <section className="rounded-3xl border border-gov-gray-100 bg-white p-5 shadow-sm dark:border-dark-border dark:bg-dark-surface">
          <h2 className="text-lg font-black text-gov-gray-900 dark:text-dark-text">
            Nuevo desde plantilla
          </h2>
          <p className="mt-1 text-sm text-gov-gray-500 dark:text-dark-muted">
            Elige el servicio (agrupado por tipo). OAuth y Bearer se configuran al crear; luego otorga
            acceso a workers en la lista de abajo.
          </p>
          <div className="mt-4">
            <McpNewConnectorSection
              canWrite={canWrite}
              existingConnectors={connectors}
              onCreated={load}
            />
          </div>
        </section>
      ) : null}

      <section className="space-y-4">
        {connectors.length === 0 ? (
          <div className="rounded-3xl border border-dashed border-gov-gray-200 p-8 text-center dark:border-dark-border">
            <p className="text-sm text-gov-gray-500">
              Sin conectores activos. Usa <strong className="font-bold">Nuevo desde plantilla</strong>{' '}
              arriba (o revisa presets tras reiniciar el gateway).
            </p>
          </div>
        ) : (
          <>
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <label htmlFor={MCP_CONNECTOR_FILTER_INPUT_ID} className="relative block flex-1">
                <Search
                  size={14}
                  className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-gov-gray-400"
                />
                <input
                  ref={searchInputRef}
                  id={MCP_CONNECTOR_FILTER_INPUT_ID}
                  name="duckclaw-mcp-connector-filter"
                  type="text"
                  inputMode="search"
                  role="searchbox"
                  value={query}
                  readOnly
                  autoComplete="off"
                  autoCorrect="off"
                  autoCapitalize="off"
                  spellCheck={false}
                  data-1p-ignore="true"
                  data-lpignore="true"
                  onFocus={(e) => e.currentTarget.removeAttribute('readonly')}
                  onChange={(e) => {
                    const next = e.target.value;
                    if (looksLikeAutofillEmail(next)) {
                      setQuery('');
                      return;
                    }
                    setQuery(next);
                  }}
                  placeholder="Buscar conector…"
                  aria-label="Buscar conector MCP"
                  className="w-full rounded-xl border border-gov-gray-200 py-2 pl-9 pr-3 text-sm dark:border-dark-border dark:bg-dark-bg"
                />
              </label>
              <p className="text-xs font-medium text-gov-gray-500 dark:text-dark-muted">
                {paginated.totalItems} conector{paginated.totalItems === 1 ? '' : 'es'}
                {paginated.totalItems > 0
                  ? ` · mostrando ${visibleStart}-${visibleEnd}`
                  : query.trim()
                    ? ' · sin coincidencias'
                    : ''}
              </p>
            </div>

            {filteredConnectors.length === 0 ? (
              <EmptyState variant="filtered" />
            ) : (
              <>
                {paginated.items.map((connector) => {
                  const selectedWorkerId =
                    grantWorkerByConnector[connector.connector_id] || workers[0]?.id || '';
                  const grantedWorkerLabels = workers
                    .filter((w) => (grantsByWorker[w.id] || []).includes(connector.connector_id))
                    .map((w) => w.name || w.id);
                  const selectedAlreadyGranted = (grantsByWorker[selectedWorkerId] || []).includes(
                    connector.connector_id
                  );
                  return (
                  <ConnectorCard
                    key={connector.connector_id}
                    connector={connector}
                    preset={connector.preset_id ? presetById[connector.preset_id] : undefined}
                    canWrite={canWrite}
                    workers={workers}
                    busyId={busyId}
                    authToken={authTokens[connector.connector_id] || ''}
                    grantWorkerId={selectedWorkerId}
                    grantNotice={grantNotices[connector.connector_id]}
                    grantedWorkerLabels={grantedWorkerLabels}
                    selectedWorkerAlreadyGranted={selectedAlreadyGranted}
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
                  );
                })}

                {paginated.totalPages > 1 && (
                  <ConnectorPaginationControls
                    page={paginated.currentPage}
                    totalPages={paginated.totalPages}
                    onPageChange={setPage}
                  />
                )}
              </>
            )}
          </>
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

function ConnectorPaginationControls({
  page,
  totalPages,
  onPageChange,
}: {
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}) {
  return (
    <div className="flex items-center justify-center gap-2 pt-2">
      <button
        type="button"
        onClick={() => onPageChange(page - 1)}
        disabled={page <= 1}
        className="inline-flex items-center gap-1 rounded-lg border border-gov-gray-200 px-3 py-1.5 text-xs font-semibold disabled:cursor-not-allowed disabled:opacity-40 dark:border-dark-border"
      >
        <ChevronLeft size={14} />
        Anterior
      </button>
      <span className="min-w-16 text-center text-xs font-medium text-gov-gray-500 dark:text-dark-muted">
        {page}/{totalPages}
      </span>
      <button
        type="button"
        onClick={() => onPageChange(page + 1)}
        disabled={page >= totalPages}
        className="inline-flex items-center gap-1 rounded-lg border border-gov-gray-200 px-3 py-1.5 text-xs font-semibold disabled:cursor-not-allowed disabled:opacity-40 dark:border-dark-border"
      >
        Siguiente
        <ChevronRight size={14} />
      </button>
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
  grantedWorkerLabels,
  selectedWorkerAlreadyGranted,
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
  grantedWorkerLabels: string[];
  selectedWorkerAlreadyGranted: boolean;
  testResult?: McpConnectorTestResult;
  onAuthTokenChange: (value: string) => void;
  onGrantWorkerChange: (value: string) => void;
  onSaveAuth: () => void;
  onConnectOAuth: () => void;
  onTest: () => void;
  onGrant: () => Promise<void>;
  onDeactivate: () => void;
}) {
  const usesOAuth = presetUsesOAuthPkce(preset);
  const needsBearer = connector.auth_kind === 'bearer' && !usesOAuth;
  const needsAuth = needsBearer || usesOAuth;
  const authReady = !needsAuth || connector.has_auth;
  const showAuthBadge = needsAuth;
  const [grantConfirmOpen, setGrantConfirmOpen] = useState(false);

  const selectedWorker = workers.find((w) => w.id === grantWorkerId);
  const workerLabel = (selectedWorker?.name || selectedWorker?.id || grantWorkerId).trim();

  const openGrantConfirm = () => {
    if (!grantWorkerId || busyId === `grant:${connector.connector_id}`) return;
    setGrantConfirmOpen(true);
  };

  const confirmGrant = () => {
    void (async () => {
      try {
        await onGrant();
      } finally {
        setGrantConfirmOpen(false);
      }
    })();
  };

  return (
    <article className="rounded-3xl border border-gov-gray-100 bg-white p-5 shadow-sm dark:border-dark-border dark:bg-dark-surface">
      <ConfirmModal
        isOpen={grantConfirmOpen}
        title={
          selectedWorkerAlreadyGranted
            ? 'Reaplicar grant (idempotente)'
            : 'Otorgar conector al agente'
        }
        description={
          selectedWorkerAlreadyGranted
            ? 'Este worker ya tiene grant activo. Confirmar solo reafirma el mismo acceso (UPSERT); no duplica permisos.'
            : 'El worker podrá invocar las tools MCP de este conector en Playground y runtime.'
        }
        confirmLabel={selectedWorkerAlreadyGranted ? 'Reaplicar grant' : 'Sí, dar grant'}
        isLoading={busyId === `grant:${connector.connector_id}`}
        details={[
          { label: 'Conector', value: connector.display_name || connector.connector_id },
          { label: 'ID', value: connector.connector_id },
          { label: 'Worker', value: workerLabel },
          {
            label: 'Estado',
            value: selectedWorkerAlreadyGranted ? 'Ya autorizado' : 'Sin grant',
          },
        ]}
        onConfirm={confirmGrant}
        onCancel={() => setGrantConfirmOpen(false)}
      />

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
          {grantedWorkerLabels.length > 0 ? (
            <span className="rounded-full bg-gov-blue-100 px-2 py-1 text-gov-blue-900 dark:bg-gov-blue-950/40 dark:text-gov-blue-200">
              grant: {grantedWorkerLabels.join(', ')}
            </span>
          ) : (
            <span className="rounded-full bg-amber-100 px-2 py-1 text-amber-800">sin grants</span>
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
              onClick={openGrantConfirm}
              disabled={!grantWorkerId || busyId === `grant:${connector.connector_id}`}
              className={`inline-flex items-center gap-2 rounded-xl px-3 py-2 text-sm font-bold text-white disabled:opacity-50 ${
                selectedWorkerAlreadyGranted
                  ? 'bg-gov-gray-600 dark:bg-dark-muted dark:text-dark-bg'
                  : 'bg-gov-blue-700 dark:bg-dark-cyan dark:text-dark-bg'
              }`}
            >
              {busyId === `grant:${connector.connector_id}` ? (
                <Loader2 size={14} className="animate-spin" />
              ) : selectedWorkerAlreadyGranted ? (
                <CheckCircle2 size={14} />
              ) : (
                <UserPlus size={14} />
              )}
              {selectedWorkerAlreadyGranted ? 'Ya otorgado · reaplicar' : 'Grant worker'}
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
            <ul className="scrollbar-thin mt-2 max-h-40 space-y-1 overflow-y-auto font-mono text-xs">
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
