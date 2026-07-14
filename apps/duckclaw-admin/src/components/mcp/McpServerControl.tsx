'use client';

import type { ReactNode } from 'react';
import { ChevronDown } from 'lucide-react';
import type { McpCatalog, McpLive } from '@/components/mcp/useMcpCatalog';
import { McpLiveBanner } from '@/components/mcp/McpLiveBanner';

type McpServerControlProps = {
  data: McpCatalog | null;
  live: McpLive | null;
  isUp: boolean;
  canRunOps: boolean;
  opsRunning: string | null;
  opsOutput: string | null;
  onStart: () => void;
  onRestart: () => void;
  onRefreshLive: () => void;
  showNativeTools: boolean;
};

function AdvancedBlock({
  title,
  children,
  defaultOpen = false,
}: {
  title: string;
  children: ReactNode;
  defaultOpen?: boolean;
}) {
  return (
    <details
      className="group rounded-xl border border-gov-gray-100 dark:border-dark-border"
      open={defaultOpen}
    >
      <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-4 py-3 text-sm font-bold text-gov-gray-800 dark:text-dark-text [&::-webkit-details-marker]:hidden">
        <span>{title}</span>
        <ChevronDown size={16} className="shrink-0 transition-transform group-open:rotate-180" />
      </summary>
      <div className="border-t border-gov-gray-100 px-4 py-3 dark:border-dark-border">{children}</div>
    </details>
  );
}

export function McpServerControl({
  data,
  live,
  isUp,
  canRunOps,
  opsRunning,
  opsOutput,
  onStart,
  onRestart,
  onRefreshLive,
  showNativeTools,
}: McpServerControlProps) {
  const toolCount = data?.duckclaw_mcp.tools.length ?? 0;

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-gov-blue-100 bg-gov-blue-50/50 px-4 py-3 text-sm text-gov-gray-700 dark:border-dark-border dark:bg-dark-bg dark:text-dark-muted">
        <p>
          <strong className="font-bold">Para qué sirve:</strong> expone un endpoint MCP/HTTP (
          <span className="font-mono">duckclaw_mcp</span>) para clientes externos — Cursor, scripts, pruebas.
          Los agentes del <strong className="font-bold">chat</strong> usan skills y conectores; no necesitan que
          abras esto salvo integración HTTP explícita.
        </p>
      </div>

      <McpLiveBanner
        live={live}
        isUp={isUp}
        canRunOps={canRunOps}
        opsRunning={opsRunning}
        onStart={onStart}
        onRestart={onRestart}
        onRefresh={onRefreshLive}
      />

      {!canRunOps ? (
        <p className="text-xs text-gov-gray-500 dark:text-dark-muted">
          Solo administradores pueden arrancar el servidor desde Admin. Si eres admin y no ves el botón, revisa tu
          rol en la consola.
        </p>
      ) : null}

      {opsOutput ? (
        <pre className="scrollbar-hide max-h-48 overflow-x-auto whitespace-pre-wrap rounded-xl bg-slate-900 p-4 font-mono text-xs text-slate-100">
          {opsOutput}
        </pre>
      ) : null}

      {data && showNativeTools ? (
        <AdvancedBlock title={`Tools nativas registradas (${toolCount})`}>
          <p className="mb-3 text-xs text-gov-gray-500 dark:text-dark-muted">
            Transparente para usuarios del chat: solo aparecen si un cliente MCP se conecta a este servidor. No
            confundir con tools de la pestaña Conectores.
          </p>
          <div className="scrollbar-hide overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gov-gray-500">
                  <th className="pb-2">Tool</th>
                  <th className="pb-2">Descripción</th>
                </tr>
              </thead>
              <tbody>
                {data.duckclaw_mcp.tools.map((tool) => (
                  <tr key={tool.name} className="border-t dark:border-dark-border">
                    <td className="py-2 font-mono text-xs">{tool.name}</td>
                    <td className="py-2">{tool.description}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </AdvancedBlock>
      ) : data && toolCount > 0 ? (
        <p className="text-xs text-gov-gray-500 dark:text-dark-muted">
          {toolCount} tool(s) nativas en el catálogo del servidor (detalle en modo desarrollador).
        </p>
      ) : null}
    </div>
  );
}
