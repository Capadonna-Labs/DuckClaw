'use client';

import type { McpCatalog, McpLive } from '@/components/mcp/useMcpCatalog';

export function McpCmdBlock({
  data,
  live,
  isUp,
}: {
  data: McpCatalog;
  live: McpLive | null;
  isUp: boolean;
}) {
  return (
    <div className="space-y-2 rounded-xl bg-gov-gray-50 p-4 font-mono text-sm dark:bg-dark-bg">
      <p>{data.duckclaw_mcp.command}</p>
      <p className="text-gov-blue-700 dark:text-dark-cyan">{live?.url ?? data.duckclaw_mcp.url}</p>
      {data.duckclaw_mcp.live && (
        <p className="font-sans text-xs text-gov-gray-500">
          Gateway probe: {data.duckclaw_mcp.live.reachable ? 'OK' : 'off'}
          {data.duckclaw_mcp.live.status_code != null &&
            ` (HTTP ${data.duckclaw_mcp.live.status_code})`}
        </p>
      )}
      <p className="font-sans text-xs text-gov-gray-500">
        Estado UI:{' '}
        {isUp ? 'respondiendo en /' : 'sin respuesta; usa runtime MCP o comando manual'}
      </p>
      <p className="font-sans text-xs text-gov-gray-500">
        PM2: <code>pm2 start config/ecosystem.mcp.config.cjs</code>
      </p>
    </div>
  );
}
