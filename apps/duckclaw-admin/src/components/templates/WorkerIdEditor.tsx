'use client';

import { useEffect, useState } from 'react';
import { Pencil, Check, X } from 'lucide-react';
import { adminService } from '@/services/adminService';
import { pollWriteTask } from '@/lib/pollWriteTask';
import { slugifyWorkerId, validateWorkerId } from '@/lib/validation';
import { useGatewayHealthStore } from '@/store/gatewayHealthStore';

type WorkerIdEditorProps = {
  workerId: string;
  canEdit: boolean;
  onRenamed: (newWorkerId: string) => void;
};

export function WorkerIdEditor({ workerId, canEdit, onRenamed }: WorkerIdEditorProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(workerId);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!editing) {
      setDraft(workerId);
    }
  }, [workerId, editing]);

  const startEdit = () => {
    setDraft(workerId);
    setError(null);
    setEditing(true);
  };

  const cancelEdit = () => {
    setDraft(workerId);
    setError(null);
    setEditing(false);
  };

  const save = async () => {
    const next = slugifyWorkerId(draft);
    const validationError = validateWorkerId(next);
    if (validationError) {
      setError(validationError);
      return;
    }
    if (next === workerId) {
      setEditing(false);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const result = await adminService.renameTemplate(workerId, next);
      if (result.task_id) {
        const polled = await pollWriteTask(result.task_id);
        if (polled.state === 'failed') {
          throw new Error(polled.detail || 'El rename no se aplicó en DB');
        }
        if (polled.state === 'timeout' || polled.state === 'not_found') {
          throw new Error('No se confirmó el rename en DB; reintenta o refresca.');
        }
      }
      const renamedId = result.worker_id || next;
      setEditing(false);
      void useGatewayHealthStore.getState().refresh(true);
      onRenamed(renamedId);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo renombrar el ID');
    } finally {
      setSaving(false);
    }
  };

  if (!canEdit) {
    return (
      <p className="font-mono text-xs text-gov-gray-500 dark:text-dark-muted" title="ID técnico">
        {workerId}
      </p>
    );
  }

  if (editing) {
    return (
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <input
            value={draft}
            onChange={(e) => setDraft(slugifyWorkerId(e.target.value))}
            maxLength={64}
            className="min-w-[14rem] flex-1 rounded-lg border border-gov-blue-200 px-2.5 py-1.5 font-mono text-xs dark:border-dark-border dark:bg-dark-bg dark:text-dark-text"
            aria-label="ID técnico del worker"
            autoFocus
            onKeyDown={(e) => {
              if (e.key === 'Enter') void save();
              if (e.key === 'Escape') cancelEdit();
            }}
          />
          <button
            type="button"
            onClick={() => void save()}
            disabled={saving}
            className="inline-flex items-center gap-1 rounded-lg bg-gov-blue-700 px-2.5 py-1.5 text-xs font-bold text-white disabled:opacity-50"
          >
            <Check size={14} />
            {saving ? 'Guardando…' : 'Guardar'}
          </button>
          <button
            type="button"
            onClick={cancelEdit}
            disabled={saving}
            className="inline-flex items-center gap-1 rounded-lg border border-gov-gray-200 px-2.5 py-1.5 text-xs font-bold dark:border-dark-border"
          >
            <X size={14} />
            Cancelar
          </button>
        </div>
        {error && <p className="text-sm text-red-600 dark:text-red-300">{error}</p>}
      </div>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <p className="font-mono text-xs text-gov-gray-500 dark:text-dark-muted" title="ID técnico">
        {workerId}
      </p>
      <button
        type="button"
        onClick={startEdit}
        className="inline-flex items-center rounded-md border border-gov-blue-100 p-1 text-gov-blue-800 hover:bg-gov-blue-50 dark:border-dark-border dark:text-dark-cyan"
        title="Editar ID técnico"
        aria-label="Editar ID técnico"
      >
        <Pencil size={12} />
      </button>
    </div>
  );
}
