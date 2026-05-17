'use client';

import { useEffect, useState } from 'react';
import { adminService } from '@/services/adminService';
import { PageShell } from '@/components/admin/PageShell';
import SettingsSection from '@/components/settings/SettingsSection';
import { Cable, Circle } from 'lucide-react';

export default function McpPage() {
  const [live, setLive] = useState<Awaited<ReturnType<typeof adminService.getMcpLiveStatus>> | null>(
    null
  );
  const [data, setData] = useState<Awaited<ReturnType<typeof adminService.getMcpCatalog>> | null>(
    null
  );
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    adminService.getMcpLiveStatus().then(setLive).catch(() => setLive(null));
    adminService
      .getMcpCatalog()
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : 'Error'));
  }, []);

  const isUp = live?.reachable === true;

  return (
    <PageShell>
      <header>
        <h1 className="text-3xl font-black dark:text-dark-text">MCP</h1>
        <p className="text-sm text-gov-gray-500 mt-1">
          Servidor streamable HTTP en puerto 8001 (mismo proceso que{' '}
          <code className="text-xs">uv run python -m duckclaw_mcp</code>)
        </p>
      </header>

      <McpLiveBanner live={live} isUp={isUp} />

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
}: {
  live: Awaited<ReturnType<typeof adminService.getMcpLiveStatus>> | null;
  isUp: boolean;
}) {
  return (
    <div
      className={`flex items-start gap-3 p-4 rounded-2xl border ${
        isUp
          ? 'bg-green-50 border-green-200 dark:bg-green-950/30 dark:border-green-900'
          : 'bg-red-50 border-red-200 dark:bg-red-950/30 dark:border-red-900'
      }`}
    >
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
  );
}

function McpCmdBlock({
  data,
  live,
  isUp,
}: {
  data: NonNullable<Awaited<ReturnType<typeof adminService.getMcpCatalog>>>;
  live: Awaited<ReturnType<typeof adminService.getMcpLiveStatus>> | null;
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
        Estado UI: {isUp ? 'respondiendo en /' : 'sin respuesta — levanta el comando de arriba'}
      </p>
    </div>
  );
}
