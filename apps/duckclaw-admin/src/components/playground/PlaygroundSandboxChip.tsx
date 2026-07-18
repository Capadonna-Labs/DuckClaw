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
  /** Misma bóveda que usa el chat al persistir /sandbox on|off. */
  vaultDbPath?: string;
  refreshKey?: number;
  onToggleCommand?: (command: '/sandbox on' | '/sandbox off') => void | Promise<void>;
  toggling?: boolean;
};

/** Pill de sandbox: clic en el chip alterna on/off (sin botón Apagar/Encender aparte). */
export function PlaygroundSandboxChip({
  chatId,
  workerId,
  tenantId,
  vaultDbPath,
  onToggleCommand,
  toggling = false,
  refreshKey = 0,
}: PlaygroundSandboxChipProps) {
  const [policy, setPolicy] = useState<SandboxPolicy | null>(null);
  const [loading, setLoading] = useState(true);

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
        vaultDbPath: vaultDbPath?.trim() || undefined,
      });
      setPolicy(pol);
    } catch {
      setPolicy(null);
    } finally {
      setLoading(false);
    }
  }, [chatId, workerId, tenantId, vaultDbPath, refreshKey]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-gov-gray-200 bg-white px-2 py-1 text-[10px] text-gov-gray-400 dark:border-dark-border dark:bg-dark-surface">
        <Loader2 size={11} className="animate-spin" />
        Sandbox…
      </span>
    );
  }

  const enabled = policy?.sandbox_enabled === true;
  const networkOn = policy?.effective_network === 'allow';
  const canToggle = Boolean(onToggleCommand && policy);

  const chipClass = `inline-flex items-center gap-1 rounded-full border px-2 py-1 text-[10px] font-bold uppercase tracking-wide ${
    enabled
      ? 'border-green-200 bg-green-50 text-green-800 dark:border-green-900 dark:bg-green-950/40 dark:text-green-300'
      : 'border-gov-gray-200 bg-white text-gov-gray-600 dark:border-dark-border dark:bg-dark-surface dark:text-dark-muted'
  } ${canToggle ? 'cursor-pointer hover:opacity-90 disabled:cursor-wait disabled:opacity-60' : ''}`;

  const chipContent = (
    <>
      {toggling ? (
        <Loader2 size={11} className="animate-spin" aria-hidden />
      ) : (
        <Box size={11} aria-hidden />
      )}
      Sandbox {enabled ? 'on' : 'off'}
      {policy ? (
        <>
          <span className="opacity-40" aria-hidden>
            ·
          </span>
          <Globe size={10} aria-hidden />
          <span className="normal-case font-semibold">{networkOn ? 'red allow' : 'red deny'}</span>
        </>
      ) : null}
    </>
  );

  return (
    <>
      {canToggle ? (
        <button
          type="button"
          disabled={toggling}
          onClick={() => void onToggleCommand!(enabled ? '/sandbox off' : '/sandbox on')}
          className={chipClass}
          title={enabled ? 'Clic para apagar sandbox' : 'Clic para encender sandbox'}
          aria-pressed={enabled}
          aria-label={enabled ? 'Sandbox encendido; clic para apagar' : 'Sandbox apagado; clic para encender'}
        >
          {chipContent}
        </button>
      ) : (
        <span className={chipClass}>{chipContent}</span>
      )}
      {policy && !onToggleCommand ? (
        <Link
          href="/vnc"
          className="rounded-full border border-gov-blue-200 bg-white px-2 py-1 text-[10px] font-black text-gov-blue-800 dark:border-dark-border dark:bg-dark-surface dark:text-dark-cyan"
        >
          VNC
        </Link>
      ) : null}
    </>
  );
}
