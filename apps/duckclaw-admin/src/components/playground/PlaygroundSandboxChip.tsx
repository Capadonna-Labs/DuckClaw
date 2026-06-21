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

/** Pills compactos para la barra de composición del chat. */
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
    } catch {
      setPolicy(null);
    } finally {
      setLoading(false);
    }
  }, [chatId, workerId, tenantId, refreshKey]);

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

  return (
    <>
      <span
        className={`inline-flex items-center gap-1 rounded-full border px-2 py-1 text-[10px] font-bold uppercase tracking-wide ${
          enabled
            ? 'border-green-200 bg-green-50 text-green-800 dark:border-green-900 dark:bg-green-950/40 dark:text-green-300'
            : 'border-gov-gray-200 bg-white text-gov-gray-600 dark:border-dark-border dark:bg-dark-surface dark:text-dark-muted'
        }`}
      >
        <Box size={11} aria-hidden />
        Sandbox {enabled ? 'on' : 'off'}
      </span>
      {policy ? (
        <>
          <span className="inline-flex items-center gap-1 rounded-full border border-gov-gray-200 bg-white px-2 py-1 text-[10px] font-semibold text-gov-gray-600 dark:border-dark-border dark:bg-dark-surface dark:text-dark-muted">
            <Globe size={10} />
            {networkOn ? 'red allow' : 'red deny'}
          </span>
          {onToggleCommand ? (
            <button
              type="button"
              disabled={toggling}
              onClick={() => void onToggleCommand(enabled ? '/sandbox off' : '/sandbox on')}
              className="rounded-full border border-gov-blue-200 bg-white px-2 py-1 text-[10px] font-black text-gov-blue-800 hover:bg-gov-blue-50 disabled:opacity-50 dark:border-dark-border dark:bg-dark-surface dark:text-dark-cyan"
            >
              {toggling ? '…' : enabled ? 'Apagar' : 'Encender'}
            </button>
          ) : (
            <Link
              href="/vnc"
              className="rounded-full border border-gov-blue-200 bg-white px-2 py-1 text-[10px] font-black text-gov-blue-800 dark:border-dark-border dark:bg-dark-surface dark:text-dark-cyan"
            >
              VNC
            </Link>
          )}
        </>
      ) : null}
    </>
  );
}
