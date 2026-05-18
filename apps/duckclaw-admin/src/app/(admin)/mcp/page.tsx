'use client';

import { useCallback, useEffect, useState } from 'react';
import { formatOpsOutput } from '@/lib/formatOpsOutput';
import { adminService } from '@/services/adminService';
import { PageShell } from '@/components/admin/PageShell';
import SettingsSection from '@/components/settings/SettingsSection';
import { useAuthStore } from '@/store/authStore';
import { Cable, Circle, Play, RefreshCw } from 'lucide-react';

type McpLive = Awaited<ReturnType<typeof adminService.getMcpLiveStatus>>;

export default function McpPage() {
  const { usuario } = useAuthStore();
  const canRunOps = usuario?.rol === 'admin';
  const [live, setLive] = useState<McpLive | null>(null);
  const [data, setData] = useState<Awaited<ReturnType<typeof adminService.getMcpCatalog>> | null>(
    null
  );
  const [error, setError] = useState<string | null>(null);
  const [opsRunning, setOpsRunning] = useState<string | null>(null);
  const [opsOutput, setOpsOutput] = useState<string | null>(null);

  const refreshLive = useCallback(() => {
    return adminService.getMcpLiveStatus().then(setLive).catch(() => setLive(null));
  }, []);

  useEffect(() => {
    refreshLive();
    adminService
      .getMcpCatalog()
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : 'Error'));
  }, [refreshLive]);

  const runMcpOp = async (opId: 'pm2_start_mcp' | 'pm2_restart_mcp' | 'pm2_logs_mcp') => {
    setOpsRunning(opId);
    setOpsOutput(null);
    setError(null);
    try {
      const r = await adminService.runOps(opId);
      setOpsOutput(
        formatOpsOutput({
          ok: r.ok,
          exit_code: r.exit_code,
          stdout: r.stdout,
          stderr: r.stderr,
          executed_via: r.executed_via,
          op_id: opId,
        })
      );
      if (opId !== 'pm2_logs_mcp') {
        for (let i = 0; i < 8; i++) {
          await new Promise((res) => setTimeout(res, 1500));
          const status = await adminService.getMcpLiveStatus();
          setLive(status);
          if (status.reachable) break;
        }
        const catalog = await adminService.getMcpCatalog().catch(() => null);
        if (catalog) setData(catalog);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error ejecutando operación');
    } finally {
      setOpsRunning(null);
    }
  };

  const isUp = live?.reachable === true;

  return (
    <PageShell>
      <header>
        <h1 className="text-3xl font-black dark:text-dark-text">MCP</h1>
        <p className="text-sm text-gov-gray-500 mt-1">
          Servidor streamable HTTP en puerto 8001 (PM2: <code className="text-xs">DuckClaw-MCP</code>
          )
        </p>
      </header>

      <McpLiveBanner
        live={live}
        isUp={isUp}
        canRunOps={canRunOps}
        opsRunning={opsRunning}
        onStart={() => runMcpOp('pm2_start_mcp')}
        onRestart={() => runMcpOp('pm2_restart_mcp')}
        onRefresh={refreshLive}
      />

      {opsOutput && (
        <pre className="p-4 text-xs font-mono bg-slate-900 text-slate-100 rounded-xl overflow-x-auto max-h-48 whitespace-pre-wrap">
          {opsOutput}
        </pre>
      )}

      {data?._gateway_stale && (
        <p className="text-sm text-amber-800 bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-900 p-3 rounded-xl">
          El API Gateway en PM2 no tiene las rutas <code>/catalog/*</code> actualizadas. Catálogo
          servido en modo fallback. Reinicia:{' '}
          <strong>Operaciones → Reiniciar DuckClaw-Gateway</strong> o{' '}
          <code className="text-xs">pm2 restart DuckClaw-Gateway --update-env</code>.
        </p>
      )}

      {error && <p className="text-red-600 text-sm">{error}</p>}

      {data && (
        <>
          <SettingsSection
            titulo="Servidor DuckClaw MCP"
            descripcion={isUp ? 'Proceso detectado en localhost' : 'No responde en localhost'}
            icono={<Cable size={22} />}
          >
            <McpCmdBlock data={data} live={live} isUp={isUp} />
            <table className="w-full text-sm mt-4">
              <thead>
                <tr className="text-left text-gov-gray-500">
                  <th className="pb-2">Tool</th>
                  <th className="pb-2">Descripción</th>
                </tr>
              </thead>
              <tbody>
                {data.duckclaw_mcp.tools.map((t) => (
                  <tr key={t.name} className="border-t dark:border-dark-border">
                    <td className="py-2 font-mono text-xs">{t.name}</td>
                    <td className="py-2">{t.description}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </SettingsSection>

          <SettingsSection titulo="Servidores stdio (config)" icono={<Cable size={22} />}>
            <ul className="text-sm space-y-2">
              {data.stdio_servers.map((s) => (
                <li key={s.id} className="p-2 rounded-lg bg-gov-gray-50 dark:bg-dark-bg">
                  <span className="font-mono font-bold">{s.id}</span>
                  <span className={s.enabled ? ' text-green-700' : ' text-gov-gray-500'}>
                    {' '}
                    · {s.enabled ? 'habilitado' : 'deshabilitado'}
                  </span>
                  <p className="text-xs text-gov-gray-500 mt-1">{s.note}</p>
                </li>
              ))}
            </ul>
            <p className="text-xs text-gov-gray-500 mt-3">{data.github_note}</p>
          </SettingsSection>
        </>
      )}
    </PageShell>
  );
}

function McpLiveBanner({
  live,
  isUp,
  canRunOps,
  opsRunning,
  onStart,
  onRestart,
  onRefresh,
}: {
  live: McpLive | null;
  isUp: boolean;
  canRunOps: boolean;
  opsRunning: string | null;
  onStart: () => void;
  onRestart: () => void;
  onRefresh: () => void;
}) {
  const busy = opsRunning !== null;

  return (
    <div
      className={`flex flex-col sm:flex-row sm:items-start gap-3 p-4 rounded-2xl border ${
        isUp
          ? 'bg-green-50 border-green-200 dark:bg-green-950/30 dark:border-green-900'
          : 'bg-red-50 border-red-200 dark:bg-red-950/30 dark:border-red-900'
      }`}
    >
      <div className="flex items-start gap-3 flex-1 min-w-0">
        <Circle
          size={12}
          className={`mt-1 shrink-0 fill-current ${isUp ? 'text-green-600' : 'text-red-500'}`}
        />
        <div className="text-sm space-y-1 min-w-0">
          <p className="font-bold">{isUp ? 'MCP en línea' : 'MCP no detectado'}</p>
          {live && (
            <>
              <p className="font-mono text-xs break-all">{live.url}</p>
              <p className="font-mono text-[10px] text-gov-gray-600 dark:text-dark-muted">
                {live.command}
              </p>
              {!isUp && live.error && (
                <p className="text-xs text-red-700 dark:text-red-400">{live.error}</p>
              )}
            </>
          )}
        </div>
      </div>

      <div className="flex flex-wrap gap-2 shrink-0">
        {canRunOps && (
          <>
            {!isUp && (
              <button
                type="button"
                disabled={busy}
                onClick={onStart}
                className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-bold rounded-lg bg-gov-blue-700 text-white hover:bg-gov-blue-800 disabled:opacity-50"
              >
                <Play size={14} />
                {opsRunning === 'pm2_start_mcp' ? 'Iniciando…' : 'Iniciar MCP (PM2)'}
              </button>
            )}
            <button
              type="button"
              disabled={busy}
              onClick={onRestart}
              className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-bold rounded-lg border dark:border-dark-border hover:border-gov-blue-500 disabled:opacity-50"
            >
              <RefreshCw size={14} className={busy ? 'animate-spin' : ''} />
              {opsRunning === 'pm2_restart_mcp' ? 'Reiniciando…' : 'Reiniciar MCP'}
            </button>
          </>
        )}
        <button
          type="button"
          disabled={busy}
          onClick={() => onRefresh()}
          className="inline-flex items-center gap-1.5 px-3 py-2 text-xs rounded-lg text-gov-gray-600 hover:bg-black/5 dark:hover:bg-white/5 disabled:opacity-50"
        >
          <RefreshCw size={14} />
          Comprobar
        </button>
      </div>
    </div>
  );
}

function McpCmdBlock({
  data,
  live,
  isUp,
}: {
  data: NonNullable<Awaited<ReturnType<typeof adminService.getMcpCatalog>>>;
  live: McpLive | null;
  isUp: boolean;
}) {
  return (
    <div className="space-y-2 text-sm font-mono bg-gov-gray-50 dark:bg-dark-bg p-4 rounded-xl">
      <p>{data.duckclaw_mcp.command}</p>
      <p className="text-gov-blue-700 dark:text-dark-cyan">{live?.url ?? data.duckclaw_mcp.url}</p>
      {data.duckclaw_mcp.live && (
        <p className="text-xs font-sans text-gov-gray-500">
          Gateway probe: {data.duckclaw_mcp.live.reachable ? 'OK' : 'off'}
          {data.duckclaw_mcp.live.status_code != null &&
            ` (HTTP ${data.duckclaw_mcp.live.status_code})`}
        </p>
      )}
      <p className="text-xs font-sans text-gov-gray-500">
        Estado UI:{' '}
        {isUp
          ? 'respondiendo en /'
          : 'sin respuesta — usa «Iniciar MCP (PM2)» arriba o el comando manual'}
      </p>
      <p className="text-xs font-sans text-gov-gray-500">
        PM2: <code>pm2 start config/ecosystem.mcp.config.cjs</code>
      </p>
    </div>
  );
}
