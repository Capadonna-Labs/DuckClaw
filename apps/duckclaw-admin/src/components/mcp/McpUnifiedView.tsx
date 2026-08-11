'use client';

import { useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { ExternalLink } from 'lucide-react';
import { PageShell } from '@/components/admin/PageShell';
import type { EmbeddedViewProps } from '@/components/admin/embeddedView';
import { McpConfigurationPanel } from '@/components/mcp/McpConfigurationPanel';
import { McpConnectorsPanel } from '@/components/mcp/McpConnectorsPanel';
import { MCP_TABS, parseMcpTab, type McpTabId } from '@/components/mcp/mcpPageTabs';
import { OfficialMcpReferenceTable } from '@/components/mcp/OfficialMcpReferenceTable';
import { useMcpCatalog, useMcpLiveStatus } from '@/components/mcp/useMcpCatalog';
import { useDeveloperMode } from '@/hooks/useDeveloperMode';
import { formatOpsOutput } from '@/lib/formatOpsOutput';
import { trimStr } from '@/lib/utils';
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
  const { developerMode } = useDeveloperMode();
  const canWrite = isAdminRole(usuario?.rol);
  const canRunOps = usuario?.rol === 'admin';
  const isUp = live?.reachable === true;

  useEffect(() => {
    setTab(parseMcpTab(searchParams.get(tabParam)));
  }, [searchParams, tabParam]);

  useEffect(() => {
    if (!data) return;
    setMcpPort(trimStr(data.duckclaw_mcp.port) || '8001');
    setMcpSource(trimStr(data.duckclaw_mcp.source) || 'default');
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
    const port = trimStr(mcpPort);
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
        <header className="border-b border-gov-gray-200 pb-4 dark:border-dark-border">
          <h1 className="text-2xl font-bold text-gov-gray-900 dark:text-dark-text">MCP</h1>
          <p className="mt-1 text-sm text-gov-gray-600 dark:text-dark-muted">
            Conectores (plantillas → DuckDB), servidor DuckClaw MCP y referencia oficial.
          </p>
        </header>
      )}

      <div
        className="flex flex-wrap gap-1 border-b border-gov-gray-200 dark:border-dark-border"
        role="tablist"
        aria-label="Secciones MCP"
      >
        {MCP_TABS.map((item) => {
          const selected = tab === item.id;
          return (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={selected}
              onClick={() => selectTab(item.id)}
              className={`border-b-2 px-4 py-2.5 text-sm font-semibold transition-colors -mb-px ${
                selected
                  ? 'border-gov-blue-600 text-gov-blue-800 dark:border-dark-cyan dark:text-dark-cyan'
                  : 'border-transparent text-gov-gray-500 hover:text-gov-gray-800 dark:hover:text-dark-text'
              }`}
            >
              {item.label}
            </button>
          );
        })}
      </div>

      {!embedded && activeTab ? (
        <p className="text-sm text-gov-gray-500 dark:text-dark-muted">{activeTab.hint}</p>
      ) : null}

      {(error || opsError) && (
        <p className="text-sm text-red-600">{error ?? opsError}</p>
      )}

      {tab === 'connectors' && <McpConnectorsPanel canWrite={canWrite} />}

      {tab === 'config' && (
        <McpConfigurationPanel
          data={data}
          live={live}
          isUp={isUp}
          canWrite={canWrite}
          canRunOps={canRunOps}
          developerMode={developerMode}
          opsRunning={opsRunning}
          opsOutput={opsOutput}
          mcpPort={mcpPort}
          mcpSource={mcpSource}
          settingsMsg={settingsMsg}
          settingsSaving={settingsSaving}
          onMcpPortChange={setMcpPort}
          onSaveSettings={() => void saveMcpSettings()}
          onStart={() => void runMcpOp('pm2_start_mcp')}
          onRestart={() => void runMcpOp('pm2_restart_mcp')}
          onRefreshLive={refreshLive}
        />
      )}

      {tab === 'catalog' && data && (
        <>
          <section className="rounded-xl border border-gov-gray-200 bg-white p-4 dark:border-dark-border dark:bg-dark-surface">
            <h2 className="text-lg font-black text-gov-gray-900 dark:text-dark-text">
              Referencia oficial MCP
            </h2>
            <p className="mt-1 text-sm text-gov-gray-500 dark:text-dark-muted">
              Documentación del registry — no es el listado de plantillas ni los conectores en DuckDB.
            </p>
            <div className="mt-4">
              <OfficialMcpReferenceTable servers={data.official_reference.servers} />
            </div>
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

          <section className="rounded-xl border border-gov-gray-200 bg-white p-4 dark:border-dark-border dark:bg-dark-surface">
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
            {data.youtube_transcript_note ? (
              <p className="mt-1 text-xs text-gov-gray-500">{data.youtube_transcript_note}</p>
            ) : null}
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
