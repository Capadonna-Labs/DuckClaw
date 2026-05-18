'use client';

import { useState } from 'react';
import { Loader2 } from 'lucide-react';
import { adminService } from '@/services/adminService';

type CatalogItem = {
  id: string;
  label: string;
  kind: string;
  hint?: string;
  active?: boolean;
  keys_ok?: boolean;
};

type Props = {
  chatId: string;
  catalog: CatalogItem[];
  onUpdated: () => void;
  disabled?: boolean;
};

const SELECTABLE_PROVIDERS = new Set([
  'mlx',
  'ollama',
  'openai',
  'anthropic',
  'deepseek',
  'groq',
  'gemini',
]);

export function LlmProviderCatalog({ chatId, catalog, onUpdated, disabled }: Props) {
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const selectProvider = async (providerId: string) => {
    if (!chatId || disabled || pendingId) return;
    if (!SELECTABLE_PROVIDERS.has(providerId)) return;
    const item = catalog.find((c) => c.id === providerId);
    if (item?.kind === 'api' && item.keys_ok === false) {
      setError(`Configura las API keys en .env para ${item.label}`);
      return;
    }
    setError(null);
    setPendingId(providerId);
    try {
      await adminService.setPlaygroundModel({ chat_id: chatId, provider: providerId });
      onUpdated();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error al cambiar proveedor');
    } finally {
      setPendingId(null);
    }
  };

  return (
    <div className="space-y-2">
      <ul className="space-y-2 max-h-48 overflow-y-auto text-xs">
        {catalog.map((p) => {
          const selectable = SELECTABLE_PROVIDERS.has(p.id);
          const isPending = pendingId === p.id;
          const blocked = p.kind === 'api' && p.keys_ok === false;
          return (
            <li key={p.id}>
              <button
                type="button"
                disabled={!selectable || disabled || Boolean(pendingId) || blocked}
                onClick={() => void selectProvider(p.id)}
                className={`w-full text-left p-2 rounded-lg border transition-colors ${
                  p.active
                    ? 'border-gov-blue-500 bg-gov-blue-50 dark:bg-gov-blue-950/40 ring-1 ring-gov-blue-500/50'
                    : 'border-transparent bg-gov-gray-50 dark:bg-dark-bg hover:border-gov-gray-300 dark:hover:border-dark-border'
                } ${!selectable || blocked ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
                title={
                  blocked
                    ? 'Faltan variables en .env'
                    : selectable
                      ? `Usar ${p.label} en esta conversación`
                      : 'Proveedor no disponible desde la UI'
                }
              >
                <div className="flex items-center justify-between gap-2">
                  <p className="font-bold">{p.label}</p>
                  {isPending && <Loader2 size={14} className="animate-spin shrink-0" />}
                </div>
                <p className="text-gov-gray-500">{p.kind === 'local' ? 'Local' : 'API'}</p>
                {p.active && (
                  <p className="text-[10px] text-gov-blue-700 dark:text-dark-cyan font-semibold mt-1">
                    Activo en esta conversación
                  </p>
                )}
              </button>
            </li>
          );
        })}
      </ul>
      {error && (
        <p className="text-[11px] text-red-500 dark:text-red-400">{error}</p>
      )}
      <p className="text-[10px] text-gov-gray-500">
        Equivale a <code className="font-mono">/model provider=…</code> en el chat. Solo afecta esta
        conversación.
      </p>
    </div>
  );
}
