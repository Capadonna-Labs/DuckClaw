'use client';

import { useMemo, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { adminService } from '@/services/adminService';
import {
  modelOptionsForProvider,
  modelLabelForOption,
  isOpenRouterProvider,
  SELECTABLE_LLM_PROVIDERS,
} from '@/lib/llmModelPresets';
import { SearchableModelSelect } from '@/components/chat/SearchableModelSelect';

type CatalogItem = {
  id: string;
  label: string;
  kind: string;
  model_example?: string;
  active?: boolean;
  keys_ok?: boolean;
};

type Props = {
  chatId: string;
  provider: string;
  model: string;
  catalog: CatalogItem[];
  onUpdated: () => void;
  disabled?: boolean;
  compact?: boolean;
};

export function ChatLlmSelectors({
  chatId,
  provider,
  model,
  catalog,
  onUpdated,
  disabled,
  compact,
}: Props) {
  const [pending, setPending] = useState<'provider' | 'model' | null>(null);
  const [error, setError] = useState<string | null>(null);

  const selectableCatalog = useMemo(
    () => catalog.filter((c) => SELECTABLE_LLM_PROVIDERS.has(c.id)),
    [catalog]
  );

  const activeProvider = (provider || '').trim().toLowerCase();
  const catalogItem = selectableCatalog.find((c) => c.id === activeProvider);
  const modelOptions = useMemo(
    () =>
      modelOptionsForProvider(activeProvider, catalogItem?.model_example, model),
    [activeProvider, catalogItem?.model_example, model]
  );
  const currentModel = model.trim() || modelOptions[0] || '';
  const openRouter = isOpenRouterProvider(activeProvider);

  const searchableOptions = useMemo(
    () =>
      modelOptions.map((m) => ({
        value: m,
        label: modelLabelForOption(activeProvider, m),
      })),
    [modelOptions, activeProvider]
  );

  const applyModel = async (next: { provider?: string; model?: string }) => {
    if (!chatId || disabled || pending) return;
    const pid = (next.provider ?? activeProvider).trim().toLowerCase();
    if (next.provider && !SELECTABLE_LLM_PROVIDERS.has(pid)) return;
    const item = selectableCatalog.find((c) => c.id === pid);
    if (item?.kind === 'api' && item.keys_ok === false) {
      setError(`Configura las API keys en .env para ${item.label}`);
      return;
    }
    setError(null);
    setPending(next.provider ? 'provider' : 'model');
    try {
      await adminService.setPlaygroundModel({
        chat_id: chatId,
        provider: pid,
        ...(next.model?.trim() ? { model: next.model.trim() } : {}),
      });
      onUpdated();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error al actualizar modelo');
    } finally {
      setPending(null);
    }
  };

  const selectCls = compact
    ? 'text-[10px] px-1.5 py-1 border rounded-md dark:border-dark-border dark:bg-dark-bg max-w-[120px] disabled:opacity-50'
    : 'text-xs px-2 py-1.5 border rounded-lg dark:border-dark-border dark:bg-dark-bg max-w-[160px] disabled:opacity-50';

  if (!chatId || selectableCatalog.length === 0) return null;

  return (
    <div
      className={`flex flex-wrap items-center gap-1.5 ${compact ? '' : 'gap-2'}`}
      title="Proveedor y modelo de esta conversación"
    >
      <label className="sr-only" htmlFor={`llm-provider-${chatId}`}>
        Proveedor LLM
      </label>
      <select
        id={`llm-provider-${chatId}`}
        value={activeProvider || selectableCatalog[0]?.id || ''}
        disabled={disabled || Boolean(pending)}
        onChange={(e) => void applyModel({ provider: e.target.value })}
        className={selectCls}
        aria-label="Proveedor LLM"
      >
        {selectableCatalog.map((p) => (
          <option key={p.id} value={p.id} disabled={p.kind === 'api' && p.keys_ok === false}>
            {compact ? p.id : p.label.replace(/\s*\(.*\)\s*$/, '')}
          </option>
        ))}
      </select>
      <label className="sr-only" htmlFor={`llm-model-${chatId}`}>
        Modelo LLM
      </label>
      <div className="relative flex items-center">
        {openRouter ? (
          <SearchableModelSelect
            id={`llm-model-${chatId}`}
            value={currentModel}
            options={searchableOptions}
            onChange={(v) => void applyModel({ model: v })}
            disabled={disabled || Boolean(pending) || !activeProvider}
            compact={compact}
            allowCustom
            placeholder="Modelo OpenRouter"
            searchPlaceholder="Buscar modelo…"
            aria-label="Modelo OpenRouter"
          />
        ) : (
          <select
            id={`llm-model-${chatId}`}
            value={currentModel}
            disabled={disabled || Boolean(pending) || !activeProvider}
            onChange={(e) => void applyModel({ model: e.target.value })}
            className={selectCls}
            aria-label="Modelo LLM"
          >
            {modelOptions.length === 0 && (
              <option value={currentModel}>{currentModel || '—'}</option>
            )}
            {modelOptions.map((m) => (
              <option key={m} value={m}>
                {modelLabelForOption(activeProvider, m)}
              </option>
            ))}
          </select>
        )}
        {pending && (
          <Loader2
            size={12}
            className="absolute -right-4 animate-spin text-gov-blue-600 dark:text-dark-cyan"
            aria-hidden
          />
        )}
      </div>
      {error && (
        <p className="w-full text-[10px] text-red-500 dark:text-red-400">{error}</p>
      )}
    </div>
  );
}
