'use client';

import { useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { ExternalLink } from 'lucide-react';
import { PageShell } from '@/components/admin/PageShell';
import type { EmbeddedViewProps } from '@/components/admin/embeddedView';
import { McpCmdBlock } from '@/components/mcp/McpCmdBlock';
import { McpConnectorsPanel } from '@/components/mcp/McpConnectorsPanel';
import { McpLiveBanner } from '@/components/mcp/McpLiveBanner';
import { MCP_TABS, parseMcpTab, type McpTabId } from '@/components/mcp/mcpPageTabs';
import { OfficialMcpReferenceTable } from '@/components/mcp/OfficialMcpReferenceTable';
import { useMcpCatalog, useMcpLiveStatus } from '@/components/mcp/useMcpCatalog';
import { formatOpsOutput } from '@/lib/formatOpsOutput';
import { isAdminRole } from '@/lib/roles';
import { adminService } from '@/services/adminService';
import { useAuthStore } from '@/store/authStore';

export function McpUnifiedView({ embedded = false }: EmbeddedViewProps) {
  const { usuario } = useAuthStore();
  const router = useRouter();
  const searchParams = useSearchParams();
  const tabParam = embedded ? 'mcpTab' : 'tab';
  const [tab, setTab] = useState<McpTabId>(() =>
    parseMcpTab(searchParams.get(tabParam))
  );
  const { data, error, refreshCatalog } = useMcpCatalog();
  const { live, setLive, refreshLive } = useMcpLiveStatus();
  const [opsRunning, setOpsRunning] = useState<string | null>(null);
  const [opsOutput, setOpsOutput] = useState<string | null>(null);
  const [opsError, setOpsError] = useState<string | null>(null);
  const [mcpPort, setMcpPort] = useState('8001');
  const [mcpSource, setMcpSource] = useState('default');
  const [settingsMsg, setSettingsMsg] = useState<string | null>(null);
  const [settingsSaving, setSettingsSaving] = useState(false);
  const canWrite = isAdminRole(usuario?.rol);
  const canRunOps = usuario?.rol === 'admin';
  const isUp = live?.reachable === true;

  useEffect(() => {
    setTab(parseMcpTab(searchParams.get(tabParam)));
  }, [searchParams, tabParam]);

  useEffect(() => {
    if (!data) return;
    setMcpPort(data.duckclaw_mcp.port || '8001');
    setMcpSource(data.duckclaw_mcp.source || 'default');
  }, [data]);

  const selectTab = (next: McpTabId) => {
    setTab(next);
    if (embedded) {
      router.replace(`/plataforma?tab=mcp&mcpTab=${next}`, { scroll: false });
      return;
    }
    router.replace(`/mcp?tab=${next}`, { scroll: false });
  };

  const runMcpOp = async (opId: 'pm2_start_mcp' | 'pm2_restart_mcp') => {
    setOpsRunning(opId);
    setOpsOutput(null);
    setOpsError(null);
    try {
      const result = await adminService.runOps(opId);
      setOpsOutput(
        formatOpsOutput({
          ok: result.ok,
          exit_code: result.exit_code,
          stdout: result.stdout,
          stderr: result.stderr,
          executed_via: result.executed_via,
          op_id: opId,
        })
      );
      for (let i = 0; i < 8; i++) {
        await new Promise((res) => setTimeout(res, 1500));
        const status = await adminService.getMcpLiveStatus();
        setLive(status);
        if (status.reachable) break;
      }
      await refreshCatalog().catch(() => undefined);
    } catch (e) {
      setOpsError(e instanceof Error ? e.message : 'Error ejecutando operación');
    } finally {
      setOpsRunning(null);
    }
  };

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

  const activeTab = MCP_TABS.find((t) => t.id === tab);
  const shellClassName = embedded ? 'space-y-6' : undefined;

  const body = (
    <>
      {!embedded && (
        <header>
          <h1 className="text-3xl font-black dark:text-dark-text">MCP</h1>
          <p className="mt-1 max-w-3xl text-sm text-gov-gray-500 dark:text-dark-muted">
            Conectores externos, servidor DuckClaw HTTP, runtime PM2 y catálogo en una sola vista.
            Las tools de conectores aparecen como{' '}
            <span className="font-mono">mcp__&#123;connector&#125;__&#123;tool&#125;</span>.
          </p>
        </header>
      )}

      <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap">
        {MCP_TABS.map((item) => {
          const selected = tab === item.id;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => selectTab(item.id)}
              className={`rounded-xl px-4 py-3 text-left sm:min-w-[160px] ${
                selected
                  ? 'bg-gov-blue-700 text-white'
                  : 'border border-gov-blue-200 text-gov-blue-800 dark:border-dark-border dark:text-dark-cyan'
              }`}
            >
              <span className="block text-sm font-black">{item.label}</span>
              <span
                className={`mt-0.5 block text-xs font-normal ${
                  selected ? 'text-blue-100' : 'text-gov-gray-500 dark:text-dark-muted'
                }`}
              >
                {item.hint}
              </span>
            </button>
          );
        })}
      </div>

      {!embedded && activeTab && (
        <p className="text-sm text-gov-gray-500 dark:text-dark-muted">{activeTab.hint}</p>
      )}

      {(error || opsError) && (
        <p className="text-sm text-red-600">{error ?? opsError}</p>
      )}

      {tab === 'connectors' && <McpConnectorsPanel canWrite={canWrite} />}

      {tab === 'runtime' && (
        <>
          <McpLiveBanner
            live={live}
            isUp={isUp}
            canRunOps={canRunOps}
            opsRunning={opsRunning}
            onStart={() => void runMcpOp('pm2_start_mcp')}
            onRestart={() => void runMcpOp('pm2_restart_mcp')}
            onRefresh={refreshLive}
          />
          {opsOutput && (
            <pre className="max-h-48 overflow-x-auto whitespace-pre-wrap rounded-xl bg-slate-900 p-4 font-mono text-xs text-slate-100">
              {opsOutput}
            </pre>
          )}
        </>
      )}

      {tab === 'config' && (
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
          {settingsMsg && (
            <p className="text-xs text-gov-blue-700 dark:text-dark-cyan">{settingsMsg}</p>
          )}
        </section>
      )}

      {tab === 'server' && data && <McpCmdBlock data={data} live={live} isUp={isUp} />}

      {tab === 'tools' && data && (
        <section className="overflow-x-auto rounded-3xl border border-gov-gray-100 bg-white p-5 shadow-sm dark:border-dark-border dark:bg-dark-surface">
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
        </section>
      )}

      {tab === 'catalog' && data && (
        <>
          <section className="rounded-3xl border border-gov-gray-100 bg-white p-5 shadow-sm dark:border-dark-border dark:bg-dark-surface">
            <OfficialMcpReferenceTable servers={data.official_reference.servers} />
            <div className="mt-4 flex flex-wrap gap-3 text-xs font-bold">
              <a
                href={data.official_reference.registry_url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 rounded-lg border px-3 py-2 text-gov-blue-700 hover:border-gov-blue-400 dark:border-dark-border dark:text-dark-cyan"
              >
                MCP Registry <ExternalLink size={14} />
              </a>
              <a
                href={data.official_reference.source_repo}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 rounded-lg border px-3 py-2 text-gov-blue-700 hover:border-gov-blue-400 dark:border-dark-border dark:text-dark-cyan"
              >
                {data.official_reference.source_label} <ExternalLink size={14} />
              </a>
            </div>
          </section>

          <section className="rounded-3xl border border-gov-gray-100 bg-white p-5 shadow-sm dark:border-dark-border dark:bg-dark-surface">
            <h2 className="text-lg font-black text-gov-gray-900 dark:text-dark-text">
              Servidores stdio (solo lectura)
            </h2>
            <ul className="mt-3 space-y-2 text-sm">
              {data.stdio_servers.map((server) => (
                <li key={server.id} className="rounded-lg bg-gov-gray-50 p-2 dark:bg-dark-bg">
                  <span className="font-mono font-bold">{server.id}</span>
                  <span className={server.enabled ? ' text-green-700' : ' text-gov-gray-500'}>
                    {' '}
                    · {server.enabled ? 'habilitado' : 'deshabilitado'}
                  </span>
                  <p className="mt-1 text-xs text-gov-gray-500">{server.note}</p>
                </li>
              ))}
            </ul>
            <p className="mt-3 text-xs text-gov-gray-500">{data.github_note}</p>
          </section>
        </>
      )}
    </>
  );

  if (embedded) {
    return <div className={shellClassName}>{body}</div>;
  }

  return <PageShell className={shellClassName}>{body}</PageShell>;
}
