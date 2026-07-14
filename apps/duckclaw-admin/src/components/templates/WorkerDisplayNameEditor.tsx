'use client';

import { useEffect, useState } from 'react';
import { Pencil, Check, X } from 'lucide-react';
import { adminService } from '@/services/adminService';
import { pollWriteTask } from '@/lib/pollWriteTask';
import { clampInput, LIMITS } from '@/lib/validation';

type WorkerDisplayNameEditorProps = {
  workerId: string;
  displayName: string;
  canEdit: boolean;
  onSaved: (displayName: string) => void;
};

export function WorkerDisplayNameEditor({
  workerId,
  displayName,
  canEdit,
  onSaved,
}: WorkerDisplayNameEditorProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(displayName);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!editing) {
      setDraft(displayName);
    }
  }, [displayName, editing]);

  const startEdit = () => {
    setDraft(displayName);
    setError(null);
    setEditing(true);
  };

  const cancelEdit = () => {
    setDraft(displayName);
    setError(null);
    setEditing(false);
  };

  const save = async () => {
    const next = clampInput(draft.trim(), LIMITS.displayName).trim();
    if (!next) {
      setError('El nombre no puede estar vacío.');
      return;
    }
    if (next === displayName.trim()) {
      setEditing(false);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const result = await adminService.patchTemplate(workerId, { display_name: next });
      if (result.task_id) {
        const polled = await pollWriteTask(result.task_id);
        if (polled.state === 'failed') {
          throw new Error(polled.detail || 'El rename no se aplicó en DB');
        }
        if (polled.state === 'timeout' || polled.state === 'not_found') {
          throw new Error('No se confirmó el rename en DB; reintenta o refresca.');
        }
      }
      onSaved(result.display_name || next);
      setEditing(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo guardar el nombre');
    } finally {
      setSaving(false);
    }
  };

  const title = displayName.trim() || 'Sin nombre';

  if (!canEdit) {
    return <h1 className="text-2xl font-black dark:text-dark-text">{title}</h1>;
  }

  if (editing) {
    return (
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <input
            value={draft}
            onChange={(e) => setDraft(clampInput(e.target.value, LIMITS.displayName))}
            maxLength={LIMITS.displayName}
            className="min-w-[16rem] flex-1 rounded-xl border border-gov-blue-200 px-3 py-2 text-2xl font-black dark:border-dark-border dark:bg-dark-bg dark:text-dark-text"
            aria-label="Nombre visible del worker"
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
            className="inline-flex items-center gap-1 rounded-xl bg-gov-blue-700 px-3 py-2 text-sm font-bold text-white disabled:opacity-50"
          >
            <Check size={16} />
            {saving ? 'Guardando…' : 'Guardar'}
          </button>
          <button
            type="button"
            onClick={cancelEdit}
            disabled={saving}
            className="inline-flex items-center gap-1 rounded-xl border border-gov-gray-200 px-3 py-2 text-sm font-bold dark:border-dark-border"
          >
            <X size={16} />
            Cancelar
          </button>
        </div>
        {error && <p className="text-sm text-red-600 dark:text-red-300">{error}</p>}
      </div>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <h1 className="text-2xl font-black dark:text-dark-text">{title}</h1>
      <button
        type="button"
        onClick={startEdit}
        className="inline-flex items-center gap-1 rounded-lg border border-gov-blue-100 px-2 py-1 text-xs font-bold text-gov-blue-800 hover:bg-gov-blue-50 dark:border-dark-border dark:text-dark-cyan"
        title="Editar nombre visible"
      >
        <Pencil size={12} />
        Renombrar
      </button>
    </div>
  );
}
