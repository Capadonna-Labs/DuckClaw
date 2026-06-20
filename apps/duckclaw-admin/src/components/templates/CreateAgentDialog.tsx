'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Bot, Loader2, X } from 'lucide-react';
import { adminService } from '@/services/adminService';
import { clampInput, LIMITS } from '@/lib/validation';

function slugifyId(raw: string): string {
  return raw
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 64);
}

type CreateAgentDialogProps = {
  open: boolean;
  onClose: () => void;
  onCreated?: () => void;
};

export function CreateAgentDialog({ open, onClose, onCreated }: CreateAgentDialogProps) {
  const router = useRouter();
  const [displayName, setDisplayName] = useState('');
  const [workerId, setWorkerId] = useState('');
  const [description, setDescription] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  const effectiveId = workerId.trim() || slugifyId(displayName);

  const submit = async () => {
    const name = displayName.trim();
    const id = effectiveId;
    if (!name || !id) {
      setError('Escribe un nombre para el agente.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await adminService.createUserAgent({
        worker_id: id,
        display_name: name,
        description: description.trim(),
        source_template_id: 'default',
      });
      onCreated?.();
      onClose();
      router.push(`/templates/${encodeURIComponent(id)}?focus=system_prompt.md`);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo crear el agente');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div
        role="dialog"
        aria-modal
        aria-labelledby="create-agent-title"
        className="w-full max-w-lg rounded-3xl border border-gov-gray-100 bg-white p-6 shadow-xl dark:border-dark-border dark:bg-dark-surface"
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <p id="create-agent-title" className="flex items-center gap-2 text-lg font-black dark:text-dark-text">
              <Bot size={20} className="text-gov-blue-700 dark:text-dark-cyan" />
              Nuevo agente
            </p>
            <p className="mt-1 text-sm text-gov-gray-500 dark:text-dark-muted">
              Incluye SQL, RAG, vault y sandbox base. Solo personaliza nombre e instrucciones.
            </p>
          </div>
          <button type="button" onClick={onClose} className="rounded-lg p-1 hover:bg-gov-gray-100 dark:hover:bg-dark-bg">
            <X size={18} />
          </button>
        </div>

        <div className="mt-5 space-y-4">
          <label className="block space-y-1">
            <span className="text-xs font-bold text-gov-gray-700 dark:text-dark-text">Nombre visible</span>
            <input
              value={displayName}
              onChange={(e) => {
                setDisplayName(clampInput(e.target.value, 128));
                if (!workerId) setWorkerId(slugifyId(e.target.value));
              }}
              maxLength={128}
              placeholder="Asistente de proyecto"
              className="w-full rounded-xl border px-3 py-2 text-sm dark:border-dark-border dark:bg-dark-bg"
            />
          </label>
          <label className="block space-y-1">
            <span className="text-xs font-bold text-gov-gray-700 dark:text-dark-text">ID técnico</span>
            <input
              value={workerId}
              onChange={(e) => setWorkerId(slugifyId(e.target.value))}
              placeholder="asistente-proyecto"
              className="w-full rounded-xl border px-3 py-2 font-mono text-sm dark:border-dark-border dark:bg-dark-bg"
            />
          </label>
          <label className="block space-y-1">
            <span className="text-xs font-bold text-gov-gray-700 dark:text-dark-text">Descripción (opcional)</span>
            <textarea
              value={description}
              onChange={(e) => setDescription(clampInput(e.target.value, 280))}
              rows={2}
              className="w-full rounded-xl border px-3 py-2 text-sm dark:border-dark-border dark:bg-dark-bg"
            />
          </label>
          {error && <p className="text-sm text-red-600">{error}</p>}
        </div>

        <div className="mt-6 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl border px-4 py-2 text-sm font-semibold dark:border-dark-border"
          >
            Cancelar
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => void submit()}
            className="inline-flex items-center gap-2 rounded-xl bg-gov-blue-700 px-4 py-2 text-sm font-bold text-white disabled:opacity-60"
          >
            {busy && <Loader2 size={16} className="animate-spin" />}
            Crear agente
          </button>
        </div>
      </div>
    </div>
  );
}
