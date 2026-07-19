'use client';

import type { ReactNode } from 'react';
import { Loader2 } from 'lucide-react';
import type { McpConnectorPreset, McpConnectorSummary } from '@/services/adminService';
import {
  mcpConnectorAuthFlags,
  resolveMcpConnectorPrimaryAction,
  type McpConnectorPrimaryKind,
} from '@/lib/mcpConnectorPrimaryAction';

type Props = {
  connector: McpConnectorSummary;
  preset?: McpConnectorPreset;
  canWrite: boolean;
  grantedWorkerLabels: string[];
  busyId: string | null;
  onOpenDetail: () => void;
  onPrimary: (kind: McpConnectorPrimaryKind) => void;
};

function StatusChip({
  tone,
  children,
}: {
  tone: 'ok' | 'warn' | 'muted';
  children: ReactNode;
}) {
  const className =
    tone === 'ok'
      ? 'bg-green-100 text-green-800 dark:bg-green-950/40 dark:text-green-300'
      : tone === 'warn'
        ? 'bg-amber-100 text-amber-800'
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
  onOpenDetail,
  onPrimary,
}: Props) {
  const { usesOAuth, needsAuth, authReady } = mcpConnectorAuthFlags(connector, preset);
  const primary = resolveMcpConnectorPrimaryAction(connector, {
    preset,
    grantCount: grantedWorkerLabels.length,
    canWrite,
  });
  const oauthBusy = busyId === `oauth:${connector.connector_id}`;
  const endpoint = connector.endpoint_url || connector.transport;

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
                {connector.has_auth ? 'auth OK' : usesOAuth ? 'falta OAuth' : 'falta Bearer'}
              </StatusChip>
            ) : null}
            <StatusChip tone={grantedWorkerLabels.length > 0 ? 'ok' : 'warn'}>
              {grantedWorkerLabels.length > 0
                ? `grant: ${grantedWorkerLabels.join(', ')}`
                : 'sin grants'}
            </StatusChip>
          </div>
          <p className="mt-0.5 truncate font-mono text-[11px] text-gov-gray-500 dark:text-dark-muted">
            {connector.connector_id}
            {endpoint ? ` · ${endpoint}` : ''}
            {connector.preset_id ? ` · ${connector.preset_id}` : ''}
          </p>
        </div>

        <div className="flex shrink-0 items-center gap-2">
          {!authReady && canWrite && primary.kind === 'connect_oauth' ? (
            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation();
                onPrimary(primary.kind);
              }}
              disabled={oauthBusy}
              className="inline-flex items-center gap-1.5 rounded-lg bg-gov-blue-700 px-3 py-1.5 text-xs font-bold text-white disabled:opacity-50 dark:bg-dark-cyan dark:text-dark-bg"
            >
              {oauthBusy ? <Loader2 size={12} className="animate-spin" /> : null}
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
