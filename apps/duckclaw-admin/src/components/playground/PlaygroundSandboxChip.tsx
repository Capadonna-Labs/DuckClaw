'use client';

import { useCallback, useEffect, useState } from 'react';
import { Box, Globe, Loader2 } from 'lucide-react';
import Link from 'next/link';
import { adminService } from '@/services/adminService';

type SandboxPolicy = Awaited<ReturnType<typeof adminService.getSandboxChatPolicy>>;

type PlaygroundSandboxChipProps = {
  chatId: string;
  workerId: string;
  tenantId?: string;
  refreshKey?: number;
  onToggleCommand?: (command: '/sandbox on' | '/sandbox off') => void | Promise<void>;
  toggling?: boolean;
};

export function PlaygroundSandboxChip({
  chatId,
  workerId,
  tenantId,
  onToggleCommand,
  toggling = false,
  refreshKey = 0,
}: PlaygroundSandboxChipProps) {
  const [policy, setPolicy] = useState<SandboxPolicy | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!chatId.trim() || !workerId.trim()) {
      setPolicy(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const pol = await adminService.getSandboxChatPolicy({
        chatId: chatId.trim(),
        workerId: workerId.trim(),
        tenantId,
      });
      setPolicy(pol);
      setError(null);
    } catch (e) {
      setPolicy(null);
      setError(e instanceof Error ? e.message : 'No se pudo leer la política sandbox');
    } finally {
      setLoading(false);
    }
  }, [chatId, workerId, tenantId, refreshKey]);

  useEffect(() => {
    void load();
  }, [load]);

  const enabled = policy?.sandbox_enabled === true;
  const networkOn = policy?.effective_network === 'allow';

  return (
    <div className="shrink-0 border-b border-gov-blue-50 bg-gov-gray-50/80 px-3 py-2 dark:border-dark-border dark:bg-dark-bg/80">
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-black uppercase tracking-wide ${
            enabled
              ? 'border-green-200 bg-green-50 text-green-800 dark:border-green-900 dark:bg-green-950/40 dark:text-green-300'
              : 'border-gov-gray-200 bg-white text-gov-gray-600 dark:border-dark-border dark:bg-dark-surface dark:text-dark-muted'
          }`}
        >
          <Box size={12} aria-hidden />
          Sandbox {enabled ? 'activo' : 'off'}
        </span>

        {loading ? (
          <span className="inline-flex items-center gap-1 text-[10px] text-gov-gray-400">
            <Loader2 size={12} className="animate-spin" />
            Leyendo política…
          </span>
        ) : policy ? (
          <>
            {policy.browser_sandbox && (
              <span className="rounded-full bg-gov-blue-50 px-2 py-0.5 text-[10px] font-bold text-gov-blue-800 dark:bg-dark-surface dark:text-dark-cyan">
                browser
              </span>
            )}
            <span className="inline-flex items-center gap-1 text-[10px] text-gov-gray-500 dark:text-dark-muted">
              <Globe size={11} />
              Red: {networkOn ? 'allow' : policy.effective_network || 'deny'}
            </span>
            {onToggleCommand ? (
              <button
                type="button"
                disabled={toggling}
                onClick={() => void onToggleCommand(enabled ? '/sandbox off' : '/sandbox on')}
                className="rounded-lg border border-gov-blue-200 bg-white px-2.5 py-1 text-[10px] font-black text-gov-blue-800 hover:bg-gov-blue-50 disabled:opacity-50 dark:border-dark-border dark:bg-dark-surface dark:text-dark-cyan"
              >
                {toggling ? 'Aplicando…' : enabled ? '/sandbox off' : '/sandbox on'}
              </button>
            ) : (
              <Link
                href="/vnc"
                className="rounded-lg border border-gov-blue-200 bg-white px-2.5 py-1 text-[10px] font-black text-gov-blue-800 hover:bg-gov-blue-50 dark:border-dark-border dark:bg-dark-surface dark:text-dark-cyan"
              >
                Configurar en VNC
              </Link>
            )}
          </>
        ) : null}
      </div>
      {error && (
        <p className="mt-1 text-[10px] text-amber-800 dark:text-amber-200">{error}</p>
      )}
      <p className="mt-1 text-[10px] text-gov-gray-500 dark:text-dark-muted">
        El toggle persiste por conversación en el vault. Usa{' '}
        <code className="font-mono">/sandbox on</code> en el chat o el botón de arriba.
      </p>
    </div>
  );
}
