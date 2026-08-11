'use client';

import type { ReactNode } from 'react';
import { Loader2 } from 'lucide-react';
import type {
  McpConnectorPreset,
  McpConnectorSummary,
  McpConnectorTestResult,
} from '@/services/adminService';
import {
  mcpConnectorAuthFlags,
  resolveMcpConnectorPrimaryAction,
  type McpConnectorPrimaryKind,
} from '@/lib/mcpConnectorPrimaryAction';
import { mcpConnectorRowHint } from '@/lib/mcpConnectorHealth';

type Props = {
  connector: McpConnectorSummary;
  preset?: McpConnectorPreset;
  canWrite: boolean;
  grantedWorkerLabels: string[];
  busyId: string | null;
  testResult?: McpConnectorTestResult;
  onOpenDetail: () => void;
  onPrimary: (kind: McpConnectorPrimaryKind) => void;
};

function StatusChip({
  tone,
  children,
}: {
  tone: 'ok' | 'warn' | 'muted' | 'error';
  children: ReactNode;
}) {
  const className =
    tone === 'ok'
      ? 'bg-green-100 text-green-800 dark:bg-green-950/40 dark:text-green-300'
      : tone === 'warn'
        ? 'bg-amber-100 text-amber-800'
        : tone === 'error'
          ? 'bg-red-100 text-red-800 dark:bg-red-950/40 dark:text-red-300'
          : 'bg-gov-gray-100 text-gov-gray-600 dark:bg-dark-bg dark:text-dark-muted';
  return (
    <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${className}`}>
      {children}
    </span>
  );
}

export function ConnectorListRow({
  connector,
  preset,
  canWrite,
  grantedWorkerLabels,
  busyId,
  testResult,
  onOpenDetail,
  onPrimary,
}: Props) {
  const { usesOAuth, usesAdbDevice, needsAuth } = mcpConnectorAuthFlags(connector, preset);
  const primary = resolveMcpConnectorPrimaryAction(connector, {
    preset,
    grantCount: grantedWorkerLabels.length,
    canWrite,
    testResult,
  });
  const rowHint = mcpConnectorRowHint({
    connector,
    preset,
    grantCount: grantedWorkerLabels.length,
    testResult,
  });
  const oauthBusy = busyId === `oauth:${connector.connector_id}`;
  const adbBusy = busyId === `adb:${connector.connector_id}`;
  const endpoint = connector.endpoint_url || connector.transport;
  const hintTone =
    testResult && !testResult.ok ? 'error' : testResult?.ok ? 'ok' : 'muted';

  return (
    <li>
      <div
        role="button"
        tabIndex={0}
        onClick={onOpenDetail}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            onOpenDetail();
          }
        }}
        className="group flex min-h-[3.5rem] cursor-pointer flex-wrap items-center gap-3 border-b border-gov-gray-100 px-4 py-3 last:border-b-0 hover:bg-gov-gray-50 dark:border-dark-border dark:hover:bg-dark-bg/60"
        data-connector-row={connector.connector_id}
      >
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="truncate text-sm font-bold text-gov-gray-900 dark:text-dark-text">
              {connector.display_name}
            </p>
            <StatusChip tone={connector.enabled ? 'ok' : 'muted'}>
              {connector.enabled ? 'habilitado' : 'off'}
            </StatusChip>
            {needsAuth ? (
              <StatusChip tone={connector.has_auth ? 'ok' : 'warn'}>
                {connector.has_auth
                  ? usesAdbDevice
                    ? 'ADB conectado'
                    : 'auth OK'
                  : usesAdbDevice
                    ? 'ADB offline'
                    : usesOAuth
                      ? 'falta OAuth'
                      : 'falta Bearer'}
              </StatusChip>
            ) : null}
            <StatusChip tone={grantedWorkerLabels.length > 0 ? 'ok' : 'warn'}>
              {grantedWorkerLabels.length > 0
                ? `grant: ${grantedWorkerLabels.join(', ')}`
                : 'sin grants'}
            </StatusChip>
            {testResult ? (
              <StatusChip tone={testResult.ok ? 'ok' : 'error'}>
                {testResult.ok ? `${testResult.tool_count} tools` : 'test falló'}
              </StatusChip>
            ) : null}
          </div>
          <p className="mt-0.5 truncate font-mono text-[11px] text-gov-gray-500 dark:text-dark-muted">
            {connector.connector_id}
            {endpoint ? ` · ${endpoint}` : ''}
            {connector.preset_id ? ` · ${connector.preset_id}` : ''}
          </p>
          {rowHint ? (
            <p
              className={`mt-1 truncate text-xs ${
                hintTone === 'error'
                  ? 'text-red-700 dark:text-red-300'
                  : hintTone === 'ok'
                    ? 'text-green-800 dark:text-green-300'
                    : 'text-gov-gray-500 dark:text-dark-muted'
              }`}
            >
              {rowHint}
            </p>
          ) : null}
        </div>

        <div className="flex shrink-0 items-center gap-2">
          {canWrite && (primary.kind === 'connect_oauth' || primary.kind === 'connect_adb') ? (
            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation();
                onPrimary(primary.kind);
              }}
              disabled={oauthBusy || adbBusy}
              className="inline-flex items-center gap-1.5 rounded-lg bg-gov-blue-700 px-3 py-1.5 text-xs font-bold text-white disabled:opacity-50 dark:bg-dark-cyan dark:text-dark-bg"
            >
              {oauthBusy || adbBusy ? <Loader2 size={12} className="animate-spin" /> : null}
              {primary.label}
            </button>
          ) : (
            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation();
                onPrimary(primary.kind);
              }}
              className="rounded-lg border border-gov-gray-200 px-3 py-1.5 text-xs font-bold text-gov-gray-800 hover:bg-white dark:border-dark-border dark:text-dark-text dark:hover:bg-dark-surface"
            >
              {primary.label}
            </button>
          )}
        </div>
      </div>
    </li>
  );
}
