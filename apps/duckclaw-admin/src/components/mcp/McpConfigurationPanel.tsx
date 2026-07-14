'use client';

import { McpServerControl } from '@/components/mcp/McpServerControl';
import type { McpCatalog, McpLive } from '@/components/mcp/useMcpCatalog';

type McpConfigurationPanelProps = {
  data: McpCatalog | null;
  live: McpLive | null;
  isUp: boolean;
  canWrite: boolean;
  canRunOps: boolean;
  developerMode: boolean;
  opsRunning: string | null;
  opsOutput: string | null;
  mcpPort: string;
  mcpSource: string;
  settingsMsg: string | null;
  settingsSaving: boolean;
  onMcpPortChange: (value: string) => void;
  onSaveSettings: () => void;
  onStart: () => void;
  onRestart: () => void;
  onRefreshLive: () => void;
};

function ConfigSection({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-3xl border border-gov-gray-100 bg-white p-5 shadow-sm dark:border-dark-border dark:bg-dark-surface">
      <h2 className="text-lg font-black text-gov-gray-900 dark:text-dark-text">{title}</h2>
      {description ? (
        <p className="mt-1 text-sm text-gov-gray-500 dark:text-dark-muted">{description}</p>
      ) : null}
      <div className="mt-4">{children}</div>
    </section>
  );
}

export function McpConfigurationPanel({
  data,
  live,
  isUp,
  canWrite: _canWrite,
  canRunOps,
  developerMode,
  opsRunning,
  opsOutput,
  mcpPort,
  mcpSource,
  settingsMsg,
  settingsSaving,
  onMcpPortChange,
  onSaveSettings,
  onStart,
  onRestart,
  onRefreshLive,
}: McpConfigurationPanelProps) {
  return (
    <div className="space-y-6">
      <ConfigSection
        title="Servidor HTTP DuckClaw"
        description="Arranca el proceso PM2 y comprueba salud. La alta de conectores está en la pestaña Conectores."
      >
        <McpServerControl
          data={data}
          live={live}
          isUp={isUp}
          canRunOps={canRunOps}
          opsRunning={opsRunning}
          opsOutput={opsOutput}
          onStart={onStart}
          onRestart={onRestart}
          onRefreshLive={onRefreshLive}
          showNativeTools={developerMode}
        />
      </ConfigSection>

      <ConfigSection
        title="Puerto"
        description="Persistido en DuckDB. Reinicia el servidor HTTP tras cambiar el puerto."
      >
        <div className="grid max-w-xl gap-3 text-sm">
          <label htmlFor="mcp-port" className="text-xs font-bold uppercase text-gov-gray-500">
            Puerto
          </label>
          <input
            id="mcp-port"
            value={mcpPort}
            onChange={(e) => onMcpPortChange(e.target.value)}
            disabled={!canRunOps}
            className="w-full rounded-xl border px-3 py-2 font-mono dark:border-dark-border dark:bg-dark-bg"
          />
          <p className="text-xs text-gov-gray-500 dark:text-dark-muted">
            Fuente: <span className="font-mono">{mcpSource}</span> ·{' '}
            <span className="font-mono">mcp.port</span>
          </p>
          {canRunOps ? (
            <button
              type="button"
              onClick={onSaveSettings}
              disabled={settingsSaving}
              className="w-fit rounded-xl bg-gov-blue-700 px-4 py-2 text-sm font-bold text-white disabled:opacity-50"
            >
              {settingsSaving ? 'Guardando…' : 'Guardar puerto'}
            </button>
          ) : null}
          {settingsMsg ? (
            <p className="text-xs text-gov-blue-700 dark:text-dark-cyan">{settingsMsg}</p>
          ) : null}
        </div>
      </ConfigSection>
    </div>
  );
}
