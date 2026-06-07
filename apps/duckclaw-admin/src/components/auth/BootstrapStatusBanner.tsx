'use client';

import { AlertCircle, CheckCircle2, Loader2 } from 'lucide-react';
import type { AdminBootstrapStatus } from '@/lib/adminBootstrapStatus';

export function BootstrapStatusBanner({
  status,
  loading,
}: {
  status: AdminBootstrapStatus | null;
  loading: boolean;
}) {
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
  const gatewayTitle =
    isGatewayStarting && status.pm2Status === 'missing'
      ? 'Gateway no registrado en PM2'
      : isGatewayStarting
        ? 'Gateway iniciando'
        : status.message;
  const gatewayDetail =
    isGatewayStarting && status.pm2Status === 'missing'
      ? 'El frontend está listo, pero falta iniciar el stack backend con el launcher operativo.'
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
      {status.gatewayHint && (
        <p className="mt-2 font-mono text-[11px] text-amber-700">{status.gatewayHint}</p>
      )}
    </div>
  );
}
