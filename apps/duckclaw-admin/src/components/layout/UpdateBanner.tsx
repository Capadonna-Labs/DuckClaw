'use client';

import { Download, Loader2 } from 'lucide-react';
import { useAutoUpdate } from '@/hooks/useAutoUpdate';
import { isDesktopBuild } from '@/lib/tauriRuntime';

export function UpdateBanner() {
  const { available, version, checking, downloading, progress, error, installAndRestart } =
    useAutoUpdate();

  if (!isDesktopBuild()) return null;
  if (!available && !checking && !error) return null;

  return (
    <div
      role="status"
      className="shrink-0 border-b border-emerald-200 bg-emerald-50 px-4 py-2 text-sm dark:border-emerald-900/50 dark:bg-emerald-950/40"
    >
      <div className="mx-auto flex max-w-screen-2xl flex-wrap items-center justify-between gap-2">
        <div className="text-emerald-900 dark:text-emerald-100">
          {checking && !available && 'Comprobando actualizaciones…'}
          {available && !downloading && (
            <>
              Nueva versión disponible
              {version ? ` (v${version})` : ''}. Tras actualizar deberás iniciar sesión de nuevo.
            </>
          )}
          {downloading && `Descargando actualización… ${Math.round(progress)}%`}
          {error && <span className="text-red-700 dark:text-red-300">{error}</span>}
        </div>
        {available && (
          <button
            type="button"
            onClick={() => void installAndRestart()}
            disabled={downloading}
            className="inline-flex min-h-[36px] items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-bold text-white hover:bg-emerald-700 disabled:opacity-60"
          >
            {downloading ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Download size={14} />
            )}
            {downloading ? 'Instalando…' : 'Actualizar y reiniciar'}
          </button>
        )}
      </div>
    </div>
  );
}
