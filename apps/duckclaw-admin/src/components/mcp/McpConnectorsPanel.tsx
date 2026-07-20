'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { ChevronLeft, ChevronRight, RefreshCw, Search } from 'lucide-react';
import type { TemplateSummary } from '@/types/admin';
import {
  adminService,
  type McpConnectorPreset,
  type McpConnectorSummary,
  type McpConnectorTestResult,
} from '@/services/adminService';
import { pollWriteTask } from '@/lib/pollWriteTask';
import EmptyState from '@/components/shared/EmptyState';
import { ConnectorDetailDrawer } from '@/components/mcp/ConnectorDetailDrawer';
import { ConnectorListRow } from '@/components/mcp/ConnectorListRow';
import { McpNewConnectorSection } from '@/components/mcp/McpNewConnectorSection';
import {
  filterMcpConnectors,
  looksLikeAutofillEmail,
  MCP_CONNECTORS_PAGE_SIZE,
} from '@/lib/mcpConnectorsList';
import type { McpConnectorPrimaryKind } from '@/lib/mcpConnectorPrimaryAction';
import {
  filterMcpConnectorsByStatus,
  type McpConnectorStatusFilter,
} from '@/lib/mcpConnectorHealth';
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
  const [connectorNotices, setConnectorNotices] = useState<Record<string, string>>({});
  const [statusFilter, setStatusFilter] = useState<McpConnectorStatusFilter>('all');
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [selectedConnectorId, setSelectedConnectorId] = useState<string | null>(null);
  const [drawerFocusBearer, setDrawerFocusBearer] = useState(false);
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
      const message = e instanceof Error ? e.message : 'No se pudo iniciar OAuth';
      setConnectorNotices((prev) => ({ ...prev, [connectorId]: message }));
      setError(message);
      setBusyId(null);
    }
  };

  const presetById = useMemo(
    () => Object.fromEntries(presets.map((preset) => [preset.preset_id, preset])),
    [presets]
  );

  const filteredConnectors = useMemo(() => {
    const byQuery = filterMcpConnectors(connectors, query);
    return filterMcpConnectorsByStatus(byQuery, {
      status: statusFilter,
      grantsByWorker,
      testResults,
      presetById,
    });
  }, [connectors, query, statusFilter, grantsByWorker, testResults, presetById]);

  const statusCounts = useMemo(() => {
    const base = filterMcpConnectors(connectors, query);
    return {
      all: base.length,
      needs_auth: filterMcpConnectorsByStatus(base, {
        status: 'needs_auth',
        grantsByWorker,
        testResults,
        presetById,
      }).length,
      no_grants: filterMcpConnectorsByStatus(base, {
        status: 'no_grants',
        grantsByWorker,
        testResults,
        presetById,
      }).length,
      test_failed: filterMcpConnectorsByStatus(base, {
        status: 'test_failed',
        grantsByWorker,
        testResults,
        presetById,
      }).length,
    };
  }, [connectors, query, grantsByWorker, testResults, presetById]);

  const paginated = useMemo(
    () => paginateItems(filteredConnectors, page, MCP_CONNECTORS_PAGE_SIZE),
    [filteredConnectors, page]
  );

  useEffect(() => {
    setPage(1);
  }, [query, statusFilter]);

  useEffect(() => {
    if (page !== paginated.currentPage) setPage(paginated.currentPage);
  }, [page, paginated.currentPage]);

  useEffect(() => {
    if (!selectedConnectorId) return;
    if (!connectors.some((row) => row.connector_id === selectedConnectorId)) {
      setSelectedConnectorId(null);
      setDrawerFocusBearer(false);
    }
  }, [connectors, selectedConnectorId]);

  const visibleStart =
    paginated.totalItems === 0 ? 0 : (paginated.currentPage - 1) * MCP_CONNECTORS_PAGE_SIZE + 1;
  const visibleEnd = Math.min(paginated.currentPage * MCP_CONNECTORS_PAGE_SIZE, paginated.totalItems);

  const selectedConnector =
    connectors.find((row) => row.connector_id === selectedConnectorId) || null;

  const openDetail = (connectorId: string, opts?: { focusBearer?: boolean }) => {
    setSelectedConnectorId(connectorId);
    setDrawerFocusBearer(Boolean(opts?.focusBearer));
  };

  const closeDetail = () => {
    setSelectedConnectorId(null);
    setDrawerFocusBearer(false);
  };

  const handleRowPrimary = (connectorId: string, kind: McpConnectorPrimaryKind) => {
    if (kind === 'connect_oauth') {
      void connectOAuth(connectorId);
      return;
    }
    if (kind === 'configure_bearer') {
      openDetail(connectorId, { focusBearer: true });
      return;
    }
    openDetail(connectorId);
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

  const revokeGrant = async (connectorId: string) => {
    const workerId = grantWorkerByConnector[connectorId] || workers[0]?.id;
    if (!workerId || busyId) return;
    setBusyId(`revoke:${connectorId}`);
    setError(null);
    setGrantNotices((prev) => {
      const next = { ...prev };
      delete next[connectorId];
      return next;
    });
    try {
      const result = await adminService.revokeMcpConnectorGrant(connectorId, workerId);
      const polled = await pollWriteTask(result.task_id);
      if (polled.state === 'failed') {
        throw new Error(polled.detail || 'Revoke no se aplicó en DB');
      }
      const workerLabel = workers.find((w) => w.id === workerId)?.name || workerId;
      await refreshGrants(workers);
      await adminService.releaseWorkerGraphCache().catch(() => undefined);
      setGrantNotices((prev) => ({
        ...prev,
        [connectorId]: `Grant revocado para ${workerLabel}. Abre un chat nuevo para reflejar el cambio.`,
      }));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo revocar el grant');
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

            <div className="flex flex-wrap gap-2">
              {(
                [
                  ['all', 'Todos'],
                  ['needs_auth', 'Falta auth'],
                  ['no_grants', 'Sin grants'],
                  ['test_failed', 'Test falló'],
                ] as const
              ).map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => setStatusFilter(id)}
                  className={`rounded-full px-3 py-1 text-xs font-bold ${
                    statusFilter === id
                      ? 'bg-gov-blue-700 text-white dark:bg-dark-cyan dark:text-dark-bg'
                      : 'border border-gov-gray-200 text-gov-gray-700 dark:border-dark-border dark:text-dark-muted'
                  }`}
                >
                  {label}
                  <span className="ml-1 opacity-70">({statusCounts[id]})</span>
                </button>
              ))}
            </div>

            {filteredConnectors.length === 0 ? (
              <EmptyState variant="filtered" />
            ) : (
              <>
                <ul
                  className="overflow-hidden rounded-2xl border border-gov-gray-100 bg-white shadow-sm dark:border-dark-border dark:bg-dark-surface"
                  data-mcp-connector-list="true"
                >
                  {paginated.items.map((connector) => {
                    const grantedWorkerLabels = workers
                      .filter((w) => (grantsByWorker[w.id] || []).includes(connector.connector_id))
                      .map((w) => w.name || w.id);
                    return (
                      <ConnectorListRow
                        key={connector.connector_id}
                        connector={connector}
                        preset={connector.preset_id ? presetById[connector.preset_id] : undefined}
                        canWrite={canWrite}
                        grantedWorkerLabels={grantedWorkerLabels}
                        busyId={busyId}
                        testResult={testResults[connector.connector_id]}
                        onOpenDetail={() => openDetail(connector.connector_id)}
                        onPrimary={(kind) => handleRowPrimary(connector.connector_id, kind)}
                      />
                    );
                  })}
                </ul>

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

      {selectedConnector ? (
        <ConnectorDetailDrawer
          open={Boolean(selectedConnectorId)}
          connector={selectedConnector}
          preset={
            selectedConnector.preset_id ? presetById[selectedConnector.preset_id] : undefined
          }
          canWrite={canWrite}
          workers={workers}
          busyId={busyId}
          authToken={authTokens[selectedConnector.connector_id] || ''}
          grantWorkerId={
            grantWorkerByConnector[selectedConnector.connector_id] || workers[0]?.id || ''
          }
          grantNotice={grantNotices[selectedConnector.connector_id]}
          connectorNotice={connectorNotices[selectedConnector.connector_id]}
          grantedWorkerLabels={workers
            .filter((w) =>
              (grantsByWorker[w.id] || []).includes(selectedConnector.connector_id)
            )
            .map((w) => w.name || w.id)}
          selectedWorkerAlreadyGranted={(
            grantsByWorker[
              grantWorkerByConnector[selectedConnector.connector_id] || workers[0]?.id || ''
            ] || []
          ).includes(selectedConnector.connector_id)}
          testResult={testResults[selectedConnector.connector_id]}
          focusBearer={drawerFocusBearer}
          onClose={closeDetail}
          onAuthTokenChange={(value) =>
            setAuthTokens((prev) => ({
              ...prev,
              [selectedConnector.connector_id]: value,
            }))
          }
          onGrantWorkerChange={(value) =>
            setGrantWorkerByConnector((prev) => ({
              ...prev,
              [selectedConnector.connector_id]: value,
            }))
          }
          onSaveAuth={() => saveAuth(selectedConnector.connector_id)}
          onConnectOAuth={() => connectOAuth(selectedConnector.connector_id)}
          onTest={() => runTest(selectedConnector.connector_id)}
          onGrant={() => grantWorker(selectedConnector.connector_id)}
          onRevoke={() => revokeGrant(selectedConnector.connector_id)}
          onDeactivate={() => deactivate(selectedConnector.connector_id)}
        />
      ) : null}

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
