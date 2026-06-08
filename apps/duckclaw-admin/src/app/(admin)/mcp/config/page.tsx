'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { PageShell } from '@/components/admin/PageShell';
import { useMcpCatalog } from '@/components/mcp/useMcpCatalog';
import { adminService } from '@/services/adminService';
import { useAuthStore } from '@/store/authStore';

export default function McpConfigPage() {
  const { usuario } = useAuthStore();
  const canRunOps = usuario?.rol === 'admin';
  const { data, error, refreshCatalog } = useMcpCatalog();
  const [mcpPort, setMcpPort] = useState('8001');
  const [mcpSource, setMcpSource] = useState('default');
  const [settingsMsg, setSettingsMsg] = useState<string | null>(null);
  const [settingsSaving, setSettingsSaving] = useState(false);

  useEffect(() => {
    if (!data) return;
    setMcpPort(data.duckclaw_mcp.port || '8001');
    setMcpSource(data.duckclaw_mcp.source || 'default');
  }, [data]);

  const saveMcpSettings = async () => {
    if (!canRunOps) return;
    const port = mcpPort.trim();
    if (!/^\d{2,5}$/.test(port)) {
      setSettingsMsg('Puerto inválido');
      return;
    }
    setSettingsSaving(true);
    setSettingsMsg(null);
    try {
      await adminService.patchRuntimeSettings([
        { domain: 'mcp', key: 'port', value: port, scope: 'global' },
      ]);
      setSettingsMsg('Configuración MCP guardada en DuckDB. Reinicia MCP para aplicar el puerto.');
      await refreshCatalog();
    } catch (e) {
      setSettingsMsg(e instanceof Error ? e.message : 'No se pudo guardar configuración MCP');
    } finally {
      setSettingsSaving(false);
    }
  };

  return (
    <PageShell>
      <header>
        <h1 className="text-3xl font-black dark:text-dark-text">Configuración MCP</h1>
        <p className="mt-1 text-sm text-gov-gray-500 dark:text-dark-muted">
          Vista dedicada a Runtime Settings DB-first.
        </p>
      </header>
      {error && <p className="text-sm text-red-600">{error}</p>}
      <section className="grid max-w-xl gap-3 rounded-3xl border border-gov-gray-100 bg-white p-5 text-sm shadow-sm dark:border-dark-border dark:bg-dark-surface">
        <label htmlFor="mcp-port" className="text-xs font-bold uppercase text-gov-gray-500">
          Puerto DuckClaw MCP
        </label>
        <input
          id="mcp-port"
          value={mcpPort}
          onChange={(e) => setMcpPort(e.target.value)}
          disabled={!canRunOps}
          className="w-full rounded-xl border px-3 py-2 font-mono dark:border-dark-border dark:bg-dark-bg"
        />
        <p className="text-xs text-gov-gray-500 dark:text-dark-muted">
          Fuente efectiva: <span className="font-mono">{mcpSource}</span> · setting{' '}
          <span className="font-mono">mcp.port</span>
        </p>
        {canRunOps && (
          <button
            type="button"
            onClick={() => void saveMcpSettings()}
            disabled={settingsSaving}
            className="w-fit rounded-xl bg-gov-blue-700 px-4 py-2 text-sm font-bold text-white disabled:opacity-50"
          >
            {settingsSaving ? 'Guardando...' : 'Guardar en DuckDB'}
          </button>
        )}
        {settingsMsg && <p className="text-xs text-gov-blue-700 dark:text-dark-cyan">{settingsMsg}</p>}
      </section>
      <Link href="/mcp" className="text-sm font-bold text-gov-blue-700 dark:text-dark-cyan">
        Volver a MCP
      </Link>
    </PageShell>
  );
}
