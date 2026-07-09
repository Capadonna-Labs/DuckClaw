'use client';

import { useState } from 'react';
import { Loader2 } from 'lucide-react';
import { adminService } from '@/services/adminService';

export type SlmConfig = {
  enabled?: boolean;
  model?: string;
  model_short?: string;
  adapter_path?: string;
  base_url?: string;
  mlx_status?: 'online' | 'offline' | 'unknown';
  pm2_name?: string;
  adapters?: { id: string; label: string; path: string; active?: boolean }[];
  hint?: string;
};

type Props = {
  chatId: string;
  slm: SlmConfig | null | undefined;
  onUpdated: () => void;
  disabled?: boolean;
  /** @deprecated Usa `size="compact"` */
  compact?: boolean;
  size?: 'compact' | 'default' | 'modal';
};

const NONE_VALUE = '__none__';

function statusBadge(status: SlmConfig['mlx_status']) {
  if (status === 'online') {
    return (
      <span className="inline-flex items-center rounded-full bg-emerald-100 px-1.5 py-0.5 text-[9px] font-bold text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300">
        online
      </span>
    );
  }
  if (status === 'offline') {
    return (
      <span className="inline-flex items-center rounded-full bg-red-100 px-1.5 py-0.5 text-[9px] font-bold text-red-800 dark:bg-red-950 dark:text-red-300">
        offline
      </span>
    );
  }
  return null;
}

export function ChatSlmSelector({
  chatId,
  slm,
  onUpdated,
  disabled,
  compact,
  size: sizeProp,
}: Props) {
  const size = sizeProp ?? (compact ? 'compact' : 'default');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const enabled = Boolean(slm?.enabled);
  const adapters = slm?.adapters ?? [];
  const activeAdapter =
    adapters.find((a) => a.active)?.path ||
    (slm?.adapter_path || '').trim() ||
    '';

  const selectValue = enabled
    ? activeAdapter || adapters[0]?.path || 'default'
    : NONE_VALUE;

  const selectCls =
    size === 'modal'
      ? 'text-sm px-3 py-2.5 min-h-[2.75rem] border rounded-xl dark:border-dark-border dark:bg-dark-bg w-full max-w-full min-w-0 disabled:opacity-50'
      : size === 'compact'
        ? 'text-[10px] px-1.5 py-1 border rounded-md dark:border-dark-border dark:bg-dark-bg w-full max-w-full min-w-0 disabled:opacity-50'
        : 'text-xs px-2 py-1.5 border rounded-lg dark:border-dark-border dark:bg-dark-bg max-w-[180px] disabled:opacity-50';

  const labelCls =
    size === 'modal'
      ? 'text-xs font-semibold text-gov-gray-600 dark:text-dark-muted'
      : 'sr-only';

  const applySlm = async (value: string) => {
    if (!chatId || disabled || pending) return;
    setError(null);
    setPending(true);
    try {
      if (value === NONE_VALUE) {
        await adminService.setPlaygroundSlm({ chat_id: chatId, enabled: false });
      } else {
        await adminService.setPlaygroundSlm({
          chat_id: chatId,
          enabled: true,
          adapter_path: value === 'default' ? '' : value,
        });
      }
      onUpdated();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error al actualizar SLM');
    } finally {
      setPending(false);
    }
  };

  if (!chatId) return null;

  const modelLabel = slm?.model_short || slm?.model || 'MLX-Inference';
  const pm2Name = slm?.pm2_name || 'MLX-Inference';

  return (
    <div
      className={`min-w-0 ${
        size === 'modal' || size === 'compact'
          ? 'flex flex-col items-stretch gap-2 w-full max-w-full'
          : 'flex flex-wrap items-center gap-2'
      }`}
      title="SLM local opcional (MLX-Inference PM2)"
    >
      <label
        className={`flex flex-col gap-1.5 ${size === 'modal' ? 'w-full' : ''}`}
        htmlFor={`slm-select-${chatId}`}
      >
        <span className={`${labelCls} flex items-center gap-2 flex-wrap`}>
          SLM (opcional)
          {statusBadge(slm?.mlx_status)}
          <span className="font-normal text-gov-gray-400">{pm2Name}</span>
        </span>
        {size !== 'modal' && size !== 'compact' && (
          <span className="text-[10px] text-gov-gray-500 dark:text-dark-muted flex items-center gap-1">
            SLM {statusBadge(slm?.mlx_status)}
          </span>
        )}
        <div className={`relative flex items-center min-w-0 ${size === 'modal' || size === 'compact' ? 'w-full' : ''}`}>
          <select
            id={`slm-select-${chatId}`}
            value={selectValue}
            disabled={disabled || pending}
            onChange={(e) => void applySlm(e.target.value)}
            className={selectCls}
            aria-label="SLM opcional MLX-Inference"
          >
            <option value={NONE_VALUE}>Ninguno</option>
            <option value="default">
              {modelLabel} (base PM2)
            </option>
            {adapters.map((a) => (
              <option key={a.id} value={a.path}>
                {a.label}
                {a.active ? ' ✓' : ''}
              </option>
            ))}
          </select>
          {pending && (
            <Loader2
              size={size === 'modal' ? 16 : 12}
              className={`absolute animate-spin text-gov-blue-600 dark:text-dark-cyan ${
                size === 'modal' ? 'right-3' : '-right-4'
              }`}
              aria-hidden
            />
          )}
        </div>
      </label>
      {(size === 'modal' || size === 'compact') && slm?.hint && (
        <p className="text-[10px] text-gov-gray-400 dark:text-dark-muted leading-snug">
          {slm.hint}
        </p>
      )}
      {error && (
        <p className={`w-full ${size === 'modal' ? 'text-xs' : 'text-[10px]'} text-red-500 dark:text-red-400`}>
          {error}
        </p>
      )}
    </div>
  );
}
