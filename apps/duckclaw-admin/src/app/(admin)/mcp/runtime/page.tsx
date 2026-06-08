'use client';

import Link from 'next/link';
import { useState } from 'react';
import { PageShell } from '@/components/admin/PageShell';
import { McpLiveBanner } from '@/components/mcp/McpLiveBanner';
import { useMcpCatalog, useMcpLiveStatus } from '@/components/mcp/useMcpCatalog';
import { formatOpsOutput } from '@/lib/formatOpsOutput';
import { adminService } from '@/services/adminService';
import { useAuthStore } from '@/store/authStore';

export default function McpRuntimePage() {
  const { usuario } = useAuthStore();
  const canRunOps = usuario?.rol === 'admin';
  const { refreshCatalog } = useMcpCatalog();
  const { live, setLive, refreshLive } = useMcpLiveStatus();
  const [opsRunning, setOpsRunning] = useState<string | null>(null);
  const [opsOutput, setOpsOutput] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const isUp = live?.reachable === true;

  const runMcpOp = async (opId: 'pm2_start_mcp' | 'pm2_restart_mcp') => {
    setOpsRunning(opId);
    setOpsOutput(null);
    setError(null);
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
      setError(e instanceof Error ? e.message : 'Error ejecutando operación');
    } finally {
      setOpsRunning(null);
    }
  };

  return (
    <PageShell>
      <header>
        <h1 className="text-3xl font-black dark:text-dark-text">Estado runtime MCP</h1>
        <p className="mt-1 text-sm text-gov-gray-500 dark:text-dark-muted">
          Vista dedicada a proceso, PM2 y health-check.
        </p>
      </header>
      {error && <p className="text-sm text-red-600">{error}</p>}
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
      <Link href="/mcp" className="text-sm font-bold text-gov-blue-700 dark:text-dark-cyan">
        Volver a MCP
      </Link>
    </PageShell>
  );
}
