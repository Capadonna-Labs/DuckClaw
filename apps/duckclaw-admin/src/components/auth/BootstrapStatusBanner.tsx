'use client';

import { useState } from 'react';
import { AlertCircle, CheckCircle2, Loader2, RefreshCw } from 'lucide-react';
import type { AdminBootstrapStatus } from '@/lib/adminBootstrapStatus';

export function BootstrapStatusBanner({
  status,
  loading,
  onRestartDone,
}: {
  status: AdminBootstrapStatus | null;
  loading: boolean;
  onRestartDone?: () => void;
}) {
  const [restarting, setRestarting] = useState(false);
  const [restartMsg, setRestartMsg] = useState<string | null>(null);

  const runEmergencyRestart = async () => {
    setRestarting(true);
    setRestartMsg('Reiniciando Gateway (PM2)… puede tardar ~30s.');
    try {
      const res = await fetch('/api/admin/bootstrap/restart-stack', {
        method: 'POST',
        credentials: 'include',
        cache: 'no-store',
        signal: AbortSignal.timeout(120_000),
      });
      const data = (await res.json().catch(() => ({}))) as {
        ok?: boolean;
        detail?: string;
        stdout?: string;
      };
      if (!res.ok || !data.ok) {
        setRestartMsg(data.detail || `Reinicio falló (HTTP ${res.status})`);
        return;
      }
      setRestartMsg('Gateway reiniciado. Comprobando disponibilidad…');
      onRestartDone?.();
    } catch (err) {
      setRestartMsg(err instanceof Error ? err.message : 'No se pudo reiniciar el stack');
    } finally {
      setRestarting(false);
    }
  };
  if (loading && !status) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-slate-50 p-3 text-sm text-slate-600">
        <p className="flex items-center gap-2 font-semibold">
          <Loader2 size={16} className="animate-spin" />
          Revisando plataforma…
        </p>
      </div>
    );
  }

  if (!status) return null;

  if (status.canAttemptLogin) {
    return (
      <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">
        <p className="flex items-center gap-2 font-semibold">
          <CheckCircle2 size={16} />
          Gateway listo para login.
        </p>
      </div>
    );
  }

  const isGatewayStarting =
    status.code === 'gateway_unreachable' || status.code === 'gateway_unconfigured';
  const isDesktopLite = (status.recoveryCommand || '').includes('desktop_restart');
  const gatewayTitle =
    isGatewayStarting && status.pm2Status === 'missing'
      ? isDesktopLite
        ? 'Gateway embebido detenido'
        : 'Gateway no registrado en PM2'
      : isGatewayStarting
        ? 'Gateway iniciando'
        : status.message;
  const gatewayDetail =
    isGatewayStarting && status.pm2Status === 'missing'
      ? isDesktopLite
        ? 'La consola está lista, pero duckclaw_backend no responde. Usa Reiniciar sistema o cierra y vuelve a abrir DuckClaw.'
        : 'El frontend está listo, pero falta iniciar el stack backend con el launcher operativo.'
      : isGatewayStarting
        ? 'Reintentando automáticamente. Puedes abrir la interfaz antes del Gateway sin perder el flujo.'
        : 'Revisa la configuración bootstrap del BFF y del Gateway.';

  return (
    <div className="rounded-2xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
      <p className="flex items-center gap-2 font-semibold">
        {isGatewayStarting ? <Loader2 size={16} className="animate-spin" /> : <AlertCircle size={16} />}
        {gatewayTitle}
      </p>
      <p className="mt-1 text-xs text-amber-800">{gatewayDetail}</p>
      {isGatewayStarting && (
        <p className="mt-2 text-xs text-amber-800">
          Arranque recomendado:{' '}
          <code className="rounded bg-amber-100 px-1 py-0.5 font-mono text-[11px]">
            {status.recoveryCommand || 'pnpm stack:up'}
          </code>
        </p>
      )}
      {isGatewayStarting && (
        <button
          type="button"
          disabled={restarting}
          onClick={() => void runEmergencyRestart()}
          className="mt-3 inline-flex min-h-[36px] items-center gap-1.5 rounded-xl border border-amber-300 bg-white px-3 py-2 text-xs font-bold text-amber-900 hover:bg-amber-100 disabled:opacity-60"
        >
          <RefreshCw size={14} className={restarting ? 'animate-spin' : ''} />
          {restarting ? 'Reiniciando Gateway…' : 'Reiniciar Gateway (PM2)'}
        </button>
      )}
      {restartMsg && <p className="mt-2 text-xs text-amber-900 whitespace-pre-wrap">{restartMsg}</p>}
      {status.gatewayHint && (
        <p className="mt-2 font-mono text-[11px] text-amber-700">{status.gatewayHint}</p>
      )}
    </div>
  );
}
