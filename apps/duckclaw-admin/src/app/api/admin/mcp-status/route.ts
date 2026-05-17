import { NextResponse } from 'next/server';

export async function GET() {
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
