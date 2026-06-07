import { NextResponse } from 'next/server';
import { adminApiKey, gatewayBase, gatewayProxyHeaders } from '@/lib/gatewayProxy';

export async function GET() {
  const gateway = gatewayBase();
  const key = adminApiKey();
  if (gateway && key) {
    try {
      const res = await fetch(`${gateway}/api/v1/admin/catalog/mcp`, {
        headers: gatewayProxyHeaders({ 'X-Admin-Key': key }),
        cache: 'no-store',
        signal: AbortSignal.timeout(2500),
      });
      if (res.ok) {
        const catalog = (await res.json()) as {
          duckclaw_mcp?: {
            port?: string;
            url?: string;
            command?: string;
            live?: Record<string, unknown>;
          };
        };
        return NextResponse.json({
          ...(catalog.duckclaw_mcp?.live ?? {}),
          port: catalog.duckclaw_mcp?.port ?? '8001',
          url: catalog.duckclaw_mcp?.url ?? 'http://127.0.0.1:8001/mcp',
          command:
            catalog.duckclaw_mcp?.command ??
            'uv run python -m duckclaw_mcp --host 0.0.0.0 --port 8001',
        });
      }
    } catch {
      /* fallback local below */
    }
  }

  const port = (process.env.DUCKCLAW_MCP_PORT || '8001').trim();
  const base = `http://127.0.0.1:${port}`;
  try {
    const res = await fetch(`${base}/`, {
      cache: 'no-store',
      signal: AbortSignal.timeout(2500),
    });
    let probe: Record<string, unknown> = {};
    try {
      probe = (await res.json()) as Record<string, unknown>;
    } catch {
      probe = {};
    }
    return NextResponse.json({
      reachable: res.ok,
      status_code: res.status,
      port,
      url: `${base}/mcp`,
      command: `uv run python -m duckclaw_mcp --host 0.0.0.0 --port ${port}`,
      service: probe.service ?? 'duckclaw-mcp',
      hint: probe.hint ?? 'MCP: la URL debe terminar en /mcp',
    });
  } catch (err) {
    return NextResponse.json({
      reachable: false,
      port,
      url: `${base}/mcp`,
      command: `uv run python -m duckclaw_mcp --host 0.0.0.0 --port ${port}`,
      error: err instanceof Error ? err.message : String(err),
    });
  }
}
