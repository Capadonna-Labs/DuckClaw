'use client';

import { useEffect, useMemo, useState } from 'react';
import { adminService } from '@/services/adminService';
import { SearchableModelSelect } from '@/components/chat/SearchableModelSelect';
import { OPENROUTER_MODEL_PRESETS } from '@/lib/llmModelPresets';
import { workerOptionId, workerOptionLabel, type WorkerOption } from '@/lib/workerOptions';
import { workerLlmKey } from '@/lib/workerLlmKey';

const INHERIT = '';


type Props = {
  tenantId?: string;
  workers: WorkerOption[];
  disabled?: boolean;
};

/** Modelo por agente (OpenRouter): vacío = hereda el modelo del chat. Aplica en todos los chats del tenant. */
export function WorkerLlmOverrides({ tenantId, workers, disabled }: Props) {
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    adminService
      .listWorkerLlm(tenantId)
      .then((res) => {
        if (!cancelled) setOverrides(res.overrides ?? {});
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'No se pudo cargar');
      });
    return () => {
      cancelled = true;
    };
  }, [tenantId]);

  const options = useMemo(
    () => [
      { value: INHERIT, label: 'Heredar del chat' },
      ...OPENROUTER_MODEL_PRESETS.map((p) => ({ value: p.id, label: p.label })),
    ],
    []
  );

  const apply = async (workerId: string, model: string) => {
    const key = workerLlmKey(workerId);
    const prev = overrides[key] ?? INHERIT;
    if (model === prev) return;
    setPending(key);
    setError(null);
    setOverrides((o) => ({ ...o, [key]: model }));
    try {
      await adminService.setWorkerLlm({ worker_id: workerId, model, tenant_id: tenantId ?? 'default' });
    } catch (err) {
      setOverrides((o) => ({ ...o, [key]: prev }));
      setError(err instanceof Error ? err.message : 'No se pudo guardar');
    } finally {
      setPending(null);
    }
  };

  if (!workers.length) return null;
  return (
    <div className="space-y-2">
      {workers.map((w) => {
        const id = workerOptionId(w);
        const key = workerLlmKey(id);
        return (
          <div key={id} className="flex items-center gap-3">
            <span className="w-40 shrink-0 truncate text-sm text-gov-gray-700 dark:text-gov-gray-300" title={id}>
              {workerOptionLabel(w)}
            </span>
            <SearchableModelSelect
              className="flex-1"
              value={overrides[key] ?? INHERIT}
              options={options}
              onChange={(v) => void apply(id, v)}
              disabled={disabled || pending === key}
              allowCustom
              placeholder="Heredar del chat"
              size="modal"
              aria-label={`Modelo de ${workerOptionLabel(w)}`}
            />
          </div>
        );
      })}
      {error && <p className="text-xs text-red-600">{error}</p>}
    </div>
  );
}
