'use client';

import { useMemo, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { adminService } from '@/services/adminService';
import {
  modelOptionsForProvider,
  modelLabelForOption,
  isOpenRouterProvider,
  SELECTABLE_LLM_PROVIDERS,
  mlxInferenceModelPaths,
  defaultMlxModel,
  isForeignModelForMlx,
  type MlxInferenceCatalog,
} from '@/lib/llmModelPresets';
import { SearchableModelSelect } from '@/components/chat/SearchableModelSelect';
import { writePlaygroundLastLlm } from '@/lib/playgroundLastSelection';

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
  tenantId?: string;
  provider: string;
  model: string;
  catalog: CatalogItem[];
  /** Modelos/adapters expuestos por MLX-Inference PM2 (mismo origen que SLM config). */
  mlxInference?: MlxInferenceCatalog | null;
  onUpdated: () => void;
  disabled?: boolean;
  /** @deprecated Usa `size="compact"` */
  compact?: boolean;
  size?: 'compact' | 'default' | 'modal';
};

export function ChatLlmSelectors({
  chatId,
  tenantId,
  provider,
  model,
  catalog,
  mlxInference,
  onUpdated,
  disabled,
  compact,
  size: sizeProp,
}: Props) {
  const size = sizeProp ?? (compact ? 'compact' : 'default');
  const [pending, setPending] = useState<'provider' | 'model' | null>(null);
  const [error, setError] = useState<string | null>(null);

  const selectableCatalog = useMemo(
    () => catalog.filter((c) => SELECTABLE_LLM_PROVIDERS.has(c.id)),
    [catalog]
  );

  const activeProvider = (provider || '').trim().toLowerCase();
  const catalogItem = selectableCatalog.find((c) => c.id === activeProvider);
  const mlxModelPaths = useMemo(
    () => (activeProvider === 'mlx' ? mlxInferenceModelPaths(mlxInference) : []),
    [activeProvider, mlxInference]
  );
  const modelOptions = useMemo(
    () =>
      modelOptionsForProvider(
        activeProvider,
        catalogItem?.model_example,
        activeProvider === 'mlx' && isForeignModelForMlx(model) ? '' : model,
        mlxModelPaths
      ),
    [activeProvider, catalogItem?.model_example, model, mlxModelPaths]
  );
  const currentModel =
    (activeProvider === 'mlx' && isForeignModelForMlx(model)
      ? defaultMlxModel(mlxInference)
      : model.trim()) ||
    modelOptions[0] ||
    '';
  const openRouter = isOpenRouterProvider(activeProvider);

  const searchableOptions = useMemo(
    () =>
      modelOptions.map((m) => ({
        value: m,
        label: modelLabelForOption(activeProvider, m, mlxInference),
      })),
    [modelOptions, activeProvider, mlxInference]
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
      const modelArg =
        next.model?.trim() ||
        (next.provider && pid === 'mlx' ? defaultMlxModel(mlxInference) : undefined);
      await adminService.setPlaygroundModel({
        chat_id: chatId,
        provider: pid,
        ...(modelArg ? { model: modelArg } : {}),
      });
      writePlaygroundLastLlm(tenantId, {
        provider: pid,
        model: modelArg || currentModel,
      });
      onUpdated();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error al actualizar modelo');
    } finally {
      setPending(null);
    }
  };

  const selectCls =
    size === 'modal'
      ? 'text-sm px-3 py-2.5 min-h-[2.75rem] border rounded-xl dark:border-dark-border dark:bg-dark-bg w-full max-w-full min-w-0 disabled:opacity-50'
      : size === 'compact'
        ? 'text-[10px] px-1.5 py-1 border rounded-md dark:border-dark-border dark:bg-dark-bg w-full max-w-full min-w-0 disabled:opacity-50'
        : 'text-xs px-2 py-1.5 border rounded-lg dark:border-dark-border dark:bg-dark-bg max-w-[160px] disabled:opacity-50';

  const labelCls =
    size === 'modal'
      ? 'text-xs font-semibold text-gov-gray-600 dark:text-dark-muted'
      : 'sr-only';

  if (!chatId || selectableCatalog.length === 0) return null;

  return (
    <div
      className={`min-w-0 ${
        size === 'modal' || size === 'compact'
          ? 'flex flex-col items-stretch gap-3 w-full max-w-full'
          : 'flex flex-wrap items-center gap-2'
      }`}
      title="Proveedor y modelo de esta conversación"
    >
      <label className={`flex flex-col gap-1.5 ${size === 'modal' ? 'w-full' : ''}`} htmlFor={`llm-provider-${chatId}`}>
        <span className={labelCls}>Proveedor LLM</span>
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
              {size === 'modal'
                ? p.label.replace(/\s*\(.*\)\s*$/, '')
                : size === 'compact'
                  ? p.id
                  : p.label.replace(/\s*\(.*\)\s*$/, '')}
            </option>
          ))}
        </select>
      </label>
      <label className={`flex flex-col gap-1.5 ${size === 'modal' ? 'w-full' : ''}`} htmlFor={`llm-model-${chatId}`}>
        <span className={labelCls}>Modelo LLM</span>
        <div className={`relative flex items-center min-w-0 ${size === 'modal' || size === 'compact' ? 'w-full' : ''}`}>
          {openRouter ? (
            <SearchableModelSelect
              id={`llm-model-${chatId}`}
              value={currentModel}
              options={searchableOptions}
              onChange={(v) => void applyModel({ model: v })}
              disabled={disabled || Boolean(pending) || !activeProvider}
              size={size === 'modal' ? 'modal' : size === 'compact' ? 'compact' : 'default'}
              allowCustom
              className={size === 'modal' || size === 'compact' ? 'w-full max-w-full' : undefined}
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
                  {modelLabelForOption(activeProvider, m, mlxInference)}
                </option>
              ))}
            </select>
          )}
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
      {activeProvider === 'mlx' && size === 'modal' && (
        <p className="text-[10px] text-gov-gray-400 dark:text-dark-muted leading-snug">
          Inferencia local vía PM2 MLX-Inference (OpenAI-compatible). El adapter activo en PM2 define el
          modelo cargado; cambiar LoRA puede requerir reiniciar MLX-Inference.
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
