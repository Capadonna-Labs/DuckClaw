'use client';

import { useState, type ReactNode } from 'react';
import Link from 'next/link';
import {
  CheckCircle2,
  ChevronDown,
  ExternalLink,
  KeyRound,
  Loader2,
  LogIn,
  TestTube2,
  Trash2,
  UserMinus,
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
import {
  interpretMcpTestFailure,
  isGoogleWorkspacePreset,
} from '@/lib/mcpConnectorHealth';

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
  connectorNotice?: string;
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
  onRevoke: () => Promise<void>;
  onDeactivate: () => void;
};

function Chip({
  tone,
  children,
}: {
  tone: 'ok' | 'warn' | 'muted';
  children: ReactNode;
}) {
  const className =
    tone === 'ok'
      ? 'bg-emerald-500/15 text-emerald-800 dark:text-emerald-300'
      : tone === 'warn'
        ? 'bg-amber-500/15 text-amber-900 dark:text-amber-200'
        : 'bg-gov-gray-100 text-gov-gray-600 dark:bg-dark-bg dark:text-dark-muted';
  return (
    <span className={`rounded-md px-2 py-0.5 text-[11px] font-semibold tracking-wide ${className}`}>
      {children}
    </span>
  );
}

function Section({
  step,
  title,
  children,
}: {
  step?: number;
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="space-y-3">
      <h3 className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.08em] text-gov-gray-400 dark:text-dark-muted">
        {step != null ? (
          <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-gov-gray-100 text-[10px] text-gov-gray-700 dark:bg-dark-bg dark:text-dark-text">
            {step}
          </span>
        ) : null}
        {title}
      </h3>
      {children}
    </section>
  );
}

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
  connectorNotice,
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
  onRevoke,
  onDeactivate,
}: Props) {
  const [grantConfirmOpen, setGrantConfirmOpen] = useState(false);
  const [revokeConfirmOpen, setRevokeConfirmOpen] = useState(false);
  const [dangerOpen, setDangerOpen] = useState(false);

  if (!connector) return null;

  const { usesOAuth, needsBearer, needsAuth, authReady } = mcpConnectorAuthFlags(
    connector,
    preset
  );
  const googleWorkspace = isGoogleWorkspacePreset(preset, connector.preset_id);
  const testFailure =
    testResult && !testResult.ok ? interpretMcpTestFailure(testResult.error || '') : null;
  const selectedWorker = workers.find((w) => w.id === grantWorkerId);
  const workerLabel = (selectedWorker?.name || selectedWorker?.id || grantWorkerId).trim();
  const endpoint = connector.endpoint_url || connector.transport;
  const readyForPlayground = authReady && grantedWorkerLabels.length > 0;

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

  const openRevokeConfirm = () => {
    if (!grantWorkerId || busyId === `revoke:${connector.connector_id}`) return;
    setRevokeConfirmOpen(true);
  };

  const confirmRevoke = () => {
    void (async () => {
      try {
        await onRevoke();
      } finally {
        setRevokeConfirmOpen(false);
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

      <ConfirmModal
        isOpen={revokeConfirmOpen}
        title="Revocar grant del worker"
        description="El worker dejará de ver tools MCP de este conector en chats nuevos. No borra el conector ni la sesión OAuth."
        confirmLabel="Sí, revocar"
        isLoading={busyId === `revoke:${connector.connector_id}`}
        details={[
          { label: 'Conector', value: connector.display_name || connector.connector_id },
          { label: 'Worker', value: workerLabel },
        ]}
        onConfirm={confirmRevoke}
        onCancel={() => setRevokeConfirmOpen(false)}
      />

      <div className="flex flex-col gap-6" data-connector-drawer={connector.connector_id}>
        {/* Status strip — scan first */}
        <div className="space-y-2">
          <div className="flex flex-wrap gap-1.5">
            <Chip tone={connector.enabled ? 'ok' : 'muted'}>
              {connector.enabled ? 'habilitado' : 'off'}
            </Chip>
            {needsAuth ? (
              <Chip tone={connector.has_auth ? 'ok' : 'warn'}>
                {connector.has_auth ? 'auth OK' : usesOAuth ? 'falta OAuth' : 'falta Bearer'}
              </Chip>
            ) : null}
            <Chip tone={grantedWorkerLabels.length > 0 ? 'ok' : 'warn'}>
              {grantedWorkerLabels.length > 0
                ? `grant · ${grantedWorkerLabels.join(', ')}`
                : 'sin grants'}
            </Chip>
            {testResult ? (
              <Chip tone={testResult.ok ? 'ok' : 'warn'}>
                {testResult.ok ? `${testResult.tool_count} tools` : 'test falló'}
              </Chip>
            ) : null}
          </div>
          <p
            className="truncate font-mono text-[11px] text-gov-gray-500 dark:text-dark-muted"
            title={endpoint}
          >
            {connector.transport}
            {connector.endpoint_url ? ` · ${connector.endpoint_url}` : ''}
            {connector.preset_id ? ` · ${connector.preset_id}` : ''}
          </p>
          {readyForPlayground ? (
            <Link
              href="/playground"
              className="inline-flex items-center gap-1.5 text-xs font-bold text-gov-blue-700 dark:text-dark-cyan"
            >
              Abrir Playground <ExternalLink size={12} />
              <span className="font-normal text-gov-gray-500">· chat nuevo para cargar tools</span>
            </Link>
          ) : null}
        </div>

        {/* 1 · Auth — only if needed */}
        {canWrite && (usesOAuth || needsBearer) ? (
          <Section step={1} title="Credenciales">
            {usesOAuth ? (
              <div className="space-y-3 rounded-xl border border-gov-gray-100 p-3 dark:border-dark-border">
                {googleWorkspace ? (
                  <p className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:bg-amber-950/30 dark:text-amber-100">
                    Google Workspace exige{' '}
                    <code className="font-mono">GOOGLE_OAUTH_*</code> en el gateway. Si no lo usas,
                    ignora este conector.
                  </p>
                ) : null}
                {connectorNotice ? (
                  <p className="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-800 dark:bg-red-950/30 dark:text-red-200">
                    {connectorNotice}
                  </p>
                ) : (
                  <p className="text-xs text-gov-gray-500 dark:text-dark-muted">
                    Sesión OAuth en el servidor para workers con skill{' '}
                    <code className="font-mono">
                      {connector.preset_id || connector.connector_id}
                    </code>
                    .
                  </p>
                )}
                <button
                  type="button"
                  onClick={onConnectOAuth}
                  disabled={busyId === `oauth:${connector.connector_id}`}
                  className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-gov-blue-700 px-4 py-2.5 text-sm font-bold text-white disabled:opacity-50 dark:bg-dark-cyan dark:text-dark-bg"
                >
                  {busyId === `oauth:${connector.connector_id}` ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : (
                    <LogIn size={14} />
                  )}
                  {connector.has_auth ? 'Reconectar OAuth' : 'Conectar OAuth'}
                </button>
              </div>
            ) : null}

            {needsBearer ? (
              <div
                className="space-y-3 rounded-xl border border-gov-gray-100 p-3 dark:border-dark-border"
                data-focus-bearer={focusBearer ? 'true' : undefined}
              >
                <div className="flex items-center gap-2 text-sm font-semibold text-gov-gray-800 dark:text-dark-text">
                  <KeyRound size={15} className="opacity-70" /> Token Bearer
                </div>
                <div className="flex flex-col gap-2 sm:flex-row">
                  <input
                    type="password"
                    value={authToken}
                    autoFocus={focusBearer}
                    onChange={(e) => onAuthTokenChange(e.target.value)}
                    placeholder="Bearer token…"
                    className="min-w-0 flex-1 rounded-xl border border-gov-gray-200 bg-transparent px-3 py-2 text-sm dark:border-dark-border dark:bg-dark-bg"
                  />
                  <button
                    type="button"
                    onClick={onSaveAuth}
                    disabled={!authToken.trim() || busyId === connector.connector_id}
                    className="rounded-xl bg-gov-blue-700 px-4 py-2 text-sm font-bold text-white disabled:opacity-50 dark:bg-dark-cyan dark:text-dark-bg"
                  >
                    Guardar
                  </button>
                </div>
              </div>
            ) : null}
          </Section>
        ) : null}

        {/* 2 · Health */}
        <Section step={canWrite && (usesOAuth || needsBearer) ? 2 : 1} title="Salud">
          <button
            type="button"
            onClick={onTest}
            disabled={!authReady || busyId === `test:${connector.connector_id}`}
            className="inline-flex w-full items-center justify-center gap-2 rounded-xl border border-gov-gray-200 bg-gov-gray-50 px-3 py-2.5 text-sm font-bold text-gov-gray-900 disabled:opacity-50 dark:border-dark-border dark:bg-dark-bg dark:text-dark-text"
          >
            {busyId === `test:${connector.connector_id}` ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <TestTube2 size={14} />
            )}
            Probar list_tools
          </button>

          {testResult ? (
            <div
              className={`rounded-xl px-3 py-3 text-sm ${
                testResult.ok
                  ? 'bg-emerald-500/10 text-emerald-900 dark:text-emerald-200'
                  : 'bg-red-500/10 text-red-800 dark:text-red-200'
              }`}
            >
              <div className="flex items-center gap-2 font-bold">
                {testResult.ok ? <CheckCircle2 size={16} /> : <TestTube2 size={16} />}
                {testResult.ok
                  ? `${testResult.tool_count} tools detectadas`
                  : testResult.error || 'Test falló'}
              </div>
              {testFailure ? <p className="mt-1.5 text-xs opacity-90">{testFailure.hint}</p> : null}
              {!testResult.ok && canWrite && testFailure?.isAuthFailure ? (
                <div className="mt-2 flex flex-wrap gap-2">
                  {usesOAuth ? (
                    <button
                      type="button"
                      onClick={onConnectOAuth}
                      className="rounded-lg bg-gov-blue-700 px-3 py-1.5 text-xs font-bold text-white dark:bg-dark-cyan dark:text-dark-bg"
                    >
                      Reconectar OAuth
                    </button>
                  ) : null}
                  {needsBearer ? (
                    <button
                      type="button"
                      onClick={onSaveAuth}
                      disabled={!authToken.trim()}
                      className="rounded-lg border px-3 py-1.5 text-xs font-bold disabled:opacity-50"
                    >
                      Guardar nuevo token
                    </button>
                  ) : null}
                </div>
              ) : null}
              {testResult.tools.length > 0 ? (
                <details className="mt-2">
                  <summary className="cursor-pointer text-xs font-semibold opacity-80">
                    Ver {testResult.tools.length} tools
                  </summary>
                  <ul className="scrollbar-thin mt-2 max-h-36 space-y-1 overflow-y-auto font-mono text-[11px]">
                    {testResult.tools.map((tool) => (
                      <li key={tool.name}>{tool.name}</li>
                    ))}
                  </ul>
                </details>
              ) : null}
            </div>
          ) : (
            <p className="text-xs text-gov-gray-500 dark:text-dark-muted">
              Confirma que el endpoint responde antes de dar grant.
            </p>
          )}
        </Section>

        {/* 3 · Grants */}
        {canWrite ? (
          <Section
            step={canWrite && (usesOAuth || needsBearer) ? 3 : 2}
            title="Acceso a workers"
          >
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
                className={`inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2 text-sm font-bold text-white disabled:opacity-50 ${
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
                {selectedWorkerAlreadyGranted ? 'Reaplicar' : 'Dar grant'}
              </button>
            </div>

            {selectedWorkerAlreadyGranted ? (
              <button
                type="button"
                onClick={openRevokeConfirm}
                disabled={busyId === `revoke:${connector.connector_id}`}
                className="inline-flex w-full items-center justify-center gap-2 rounded-xl border border-transparent px-3 py-2 text-xs font-semibold text-amber-800 hover:border-amber-200 hover:bg-amber-50 disabled:opacity-50 dark:text-amber-100 dark:hover:bg-amber-950/20"
              >
                {busyId === `revoke:${connector.connector_id}` ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <UserMinus size={14} />
                )}
                Revocar grant de {workerLabel}
              </button>
            ) : null}

            {grantNotice ? (
              <div className="rounded-xl bg-emerald-500/10 px-3 py-2 text-xs text-emerald-900 dark:text-emerald-200">
                <div className="flex items-start gap-2 font-semibold">
                  <CheckCircle2 size={14} className="mt-0.5 shrink-0" />
                  {grantNotice}
                </div>
              </div>
            ) : null}
          </Section>
        ) : null}

        {/* Danger — progressive disclosure */}
        {canWrite ? (
          <div className="border-t border-gov-gray-100 pt-2 dark:border-dark-border">
            <button
              type="button"
              onClick={() => setDangerOpen((v) => !v)}
              className="flex w-full items-center justify-between py-2 text-left text-xs font-bold uppercase tracking-wide text-gov-gray-400"
              aria-expanded={dangerOpen}
            >
              Zona peligrosa
              <ChevronDown
                size={14}
                className={`transition-transform ${dangerOpen ? 'rotate-180' : ''}`}
              />
            </button>
            {dangerOpen ? (
              <button
                type="button"
                onClick={onDeactivate}
                disabled={busyId === `deactivate:${connector.connector_id}`}
                className="mt-1 inline-flex w-full items-center justify-center gap-2 rounded-xl border border-red-200 px-3 py-2 text-sm font-bold text-red-700 disabled:opacity-50 dark:border-red-900/50"
              >
                <Trash2 size={14} /> Desactivar conector
              </button>
            ) : null}
          </div>
        ) : null}
      </div>
    </AdminSideDrawer>
  );
}
