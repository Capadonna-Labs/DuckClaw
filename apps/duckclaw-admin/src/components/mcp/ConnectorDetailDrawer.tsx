'use client';

import { useState } from 'react';
import {
  CheckCircle2,
  KeyRound,
  Loader2,
  LogIn,
  TestTube2,
  Trash2,
  UserPlus,
} from 'lucide-react';
import type { TemplateSummary } from '@/types/admin';
import type {
  McpConnectorPreset,
  McpConnectorSummary,
  McpConnectorTestResult,
} from '@/services/adminService';
import ConfirmModal from '@/components/admin/ConfirmModal';
import { AdminSideDrawer } from '@/components/shared/AdminSideDrawer';
import { mcpConnectorAuthFlags } from '@/lib/mcpConnectorPrimaryAction';

type Props = {
  open: boolean;
  connector: McpConnectorSummary | null;
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
  focusBearer?: boolean;
  onClose: () => void;
  onAuthTokenChange: (value: string) => void;
  onGrantWorkerChange: (value: string) => void;
  onSaveAuth: () => void;
  onConnectOAuth: () => void;
  onTest: () => void;
  onGrant: () => Promise<void>;
  onDeactivate: () => void;
};

export function ConnectorDetailDrawer({
  open,
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
  focusBearer,
  onClose,
  onAuthTokenChange,
  onGrantWorkerChange,
  onSaveAuth,
  onConnectOAuth,
  onTest,
  onGrant,
  onDeactivate,
}: Props) {
  const [grantConfirmOpen, setGrantConfirmOpen] = useState(false);

  if (!connector) return null;

  const { usesOAuth, needsBearer, needsAuth, authReady } = mcpConnectorAuthFlags(
    connector,
    preset
  );
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
    <AdminSideDrawer
      open={open}
      title={connector.display_name}
      subtitle={connector.connector_id}
      onClose={onClose}
      widthClassName="w-full max-w-lg"
    >
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

      <div className="space-y-5" data-connector-drawer={connector.connector_id}>
        <dl className="space-y-2 text-sm">
          <div>
            <dt className="text-xs font-bold uppercase text-gov-gray-400">Transporte</dt>
            <dd className="mt-0.5 text-gov-gray-800 dark:text-dark-text">
              {connector.transport}
              {connector.endpoint_url ? ` · ${connector.endpoint_url}` : ''}
            </dd>
          </div>
          {connector.preset_id ? (
            <div>
              <dt className="text-xs font-bold uppercase text-gov-gray-400">Preset</dt>
              <dd className="mt-0.5 font-mono text-xs text-gov-gray-700 dark:text-dark-muted">
                {connector.preset_id}
              </dd>
            </div>
          ) : null}
          <div className="flex flex-wrap gap-2 pt-1 text-xs font-bold">
            <span
              className={
                connector.enabled
                  ? 'rounded-full bg-green-100 px-2 py-1 text-green-800 dark:bg-green-950/40 dark:text-green-300'
                  : 'rounded-full bg-gov-gray-100 px-2 py-1 text-gov-gray-600'
              }
            >
              {connector.enabled ? 'habilitado' : 'deshabilitado'}
            </span>
            {needsAuth ? (
              <span
                className={
                  connector.has_auth
                    ? 'rounded-full bg-green-100 px-2 py-1 text-green-800 dark:bg-green-950/40 dark:text-green-300'
                    : 'rounded-full bg-amber-100 px-2 py-1 text-amber-800'
                }
              >
                {connector.has_auth ? 'auth OK' : usesOAuth ? 'falta OAuth' : 'falta Bearer'}
              </span>
            ) : null}
            {grantedWorkerLabels.length > 0 ? (
              <span className="rounded-full bg-gov-blue-100 px-2 py-1 text-gov-blue-900 dark:bg-gov-blue-950/40 dark:text-gov-blue-200">
                grant: {grantedWorkerLabels.join(', ')}
              </span>
            ) : (
              <span className="rounded-full bg-amber-100 px-2 py-1 text-amber-800">sin grants</span>
            )}
          </div>
        </dl>

        {canWrite && usesOAuth ? (
          <section className="rounded-2xl border border-gov-gray-100 p-4 dark:border-dark-border">
            <div className="flex items-center gap-2 text-sm font-bold">
              <LogIn size={16} /> Conectar OAuth (PKCE)
            </div>
            <p className="mt-2 text-xs text-gov-gray-600 dark:text-dark-muted">
              Inicia sesión con el proveedor. La sesión queda en el servidor para workers con la skill{' '}
              <code className="font-mono">{connector.preset_id || connector.connector_id}</code>.
            </p>
            <button
              type="button"
              onClick={onConnectOAuth}
              disabled={busyId === `oauth:${connector.connector_id}`}
              className="mt-3 inline-flex items-center gap-2 rounded-xl bg-gov-blue-700 px-4 py-2 text-sm font-bold text-white disabled:opacity-50 dark:bg-dark-cyan dark:text-dark-bg"
            >
              {busyId === `oauth:${connector.connector_id}` ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <LogIn size={14} />
              )}
              {connector.has_auth ? 'Reconectar OAuth' : 'Conectar OAuth'}
            </button>
          </section>
        ) : null}

        {canWrite && needsBearer ? (
          <section
            className="rounded-2xl border border-gov-gray-100 p-4 dark:border-dark-border"
            data-focus-bearer={focusBearer ? 'true' : undefined}
          >
            <div className="flex items-center gap-2 text-sm font-bold">
              <KeyRound size={16} /> Token Bearer
            </div>
            <div className="mt-3 flex flex-col gap-2 sm:flex-row">
              <input
                type="password"
                value={authToken}
                autoFocus={focusBearer}
                onChange={(e) => onAuthTokenChange(e.target.value)}
                placeholder="Bearer token…"
                className="min-w-0 flex-1 rounded-xl border border-gov-gray-200 px-3 py-2 text-sm dark:border-dark-border dark:bg-dark-bg"
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
          </section>
        ) : null}

        <section className="space-y-3">
          <button
            type="button"
            onClick={onTest}
            disabled={!authReady || busyId === `test:${connector.connector_id}`}
            className="inline-flex w-full items-center justify-center gap-2 rounded-xl border px-3 py-2 text-sm font-bold disabled:opacity-50"
          >
            {busyId === `test:${connector.connector_id}` ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <TestTube2 size={14} />
            )}
            Probar list_tools
          </button>

          {canWrite ? (
            <>
              <div className="flex flex-col gap-2 sm:flex-row">
                <select
                  value={grantWorkerId}
                  onChange={(e) => onGrantWorkerChange(e.target.value)}
                  className="min-w-0 flex-1 rounded-xl border border-gov-gray-200 px-3 py-2 text-sm dark:border-dark-border dark:bg-dark-bg"
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
                  className={`inline-flex items-center justify-center gap-2 rounded-xl px-3 py-2 text-sm font-bold text-white disabled:opacity-50 ${
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
                  {selectedWorkerAlreadyGranted ? 'Reaplicar' : 'Grant worker'}
                </button>
              </div>
              <button
                type="button"
                onClick={onDeactivate}
                disabled={busyId === `deactivate:${connector.connector_id}`}
                className="inline-flex w-full items-center justify-center gap-2 rounded-xl border border-red-200 px-3 py-2 text-sm font-bold text-red-700 disabled:opacity-50"
              >
                <Trash2 size={14} /> Desactivar
              </button>
            </>
          ) : null}
        </section>

        {grantNotice ? (
          <div className="rounded-2xl border border-green-200 bg-green-50 p-4 text-sm text-green-900 dark:border-green-900/50 dark:bg-green-950/20 dark:text-green-200">
            <div className="flex items-center gap-2 font-bold">
              <CheckCircle2 size={16} />
              {grantNotice}
            </div>
          </div>
        ) : null}

        {testResult ? (
          <div
            className={`rounded-2xl p-4 text-sm ${
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
            {testResult.tools.length > 0 ? (
              <ul className="scrollbar-thin mt-2 max-h-40 space-y-1 overflow-y-auto font-mono text-xs">
                {testResult.tools.map((tool) => (
                  <li key={tool.name}>{tool.name}</li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}
      </div>
    </AdminSideDrawer>
  );
}
