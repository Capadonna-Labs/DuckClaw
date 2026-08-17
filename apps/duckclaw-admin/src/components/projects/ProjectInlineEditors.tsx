'use client';

import { useEffect, useState } from 'react';
import { Check, FolderKanban, Pencil, X } from 'lucide-react';
import { adminService } from '@/services/adminService';
import { pollWriteTask } from '@/lib/pollWriteTask';
import { clampInput, LIMITS } from '@/lib/validation';
import type { WorkspaceProjectSummary } from '@/services/adminService';

type ProjectNameEditorProps = {
  project: WorkspaceProjectSummary;
  canEdit: boolean;
  onSaved: (project: WorkspaceProjectSummary) => void;
};

export function ProjectNameEditor({ project, canEdit, onSaved }: ProjectNameEditorProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(project.name);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!editing) setDraft(project.name);
  }, [project.name, editing]);

  const cancel = () => {
    setDraft(project.name);
    setError(null);
    setEditing(false);
  };

  const save = async () => {
    const next = clampInput(draft.trim(), LIMITS.projectName).trim();
    if (!next) {
      setError('El nombre no puede estar vacío.');
      return;
    }
    if (next === project.name.trim()) {
      setEditing(false);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const result = await adminService.updateWorkspaceProject(project.project_id, { name: next });
      if (result.task_id) {
        const polled = await pollWriteTask(result.task_id);
        if (polled.state === 'failed') {
          throw new Error(polled.detail || 'No se pudo guardar el nombre');
        }
        if (polled.state === 'timeout' || polled.state === 'not_found') {
          throw new Error('No se confirmó el cambio; reintenta o refresca.');
        }
      }
      onSaved({ ...project, ...(result.project || {}), name: next });
      setEditing(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo guardar el nombre');
    } finally {
      setSaving(false);
    }
  };

  if (!canEdit) {
    return (
      <h1 className="flex items-center gap-2 text-3xl font-black text-gov-gray-900 dark:text-dark-text">
        <FolderKanban size={28} /> {project.name}
      </h1>
    );
  }

  if (editing) {
    return (
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <FolderKanban size={28} className="shrink-0 text-gov-blue-700 dark:text-dark-cyan" />
          <input
            value={draft}
            onChange={(e) => setDraft(clampInput(e.target.value, LIMITS.projectName))}
            maxLength={LIMITS.projectName}
            className="min-w-[16rem] flex-1 rounded-xl border border-gov-blue-200 px-3 py-2 text-2xl font-black dark:border-dark-border dark:bg-dark-bg dark:text-dark-text"
            aria-label="Nombre del proyecto"
            autoFocus
            onKeyDown={(e) => {
              if (e.key === 'Enter') void save();
              if (e.key === 'Escape') cancel();
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
            onClick={cancel}
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
      <h1 className="flex items-center gap-2 text-3xl font-black text-gov-gray-900 dark:text-dark-text">
        <FolderKanban size={28} /> {project.name}
      </h1>
      <button
        type="button"
        onClick={() => {
          setDraft(project.name);
          setError(null);
          setEditing(true);
        }}
        className="inline-flex items-center rounded-lg border border-gov-blue-100 p-1.5 text-gov-blue-800 hover:bg-gov-blue-50 dark:border-dark-border dark:text-dark-cyan"
        title="Editar nombre del proyecto"
        aria-label="Editar nombre del proyecto"
      >
        <Pencil size={14} />
      </button>
    </div>
  );
}

type ProjectContextEditorProps = {
  project: WorkspaceProjectSummary;
  canEdit: boolean;
  onSaved: (project: WorkspaceProjectSummary) => void;
};

export function ProjectContextEditor({ project, canEdit, onSaved }: ProjectContextEditorProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(project.description || '');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!editing) setDraft(project.description || '');
  }, [project.description, editing]);

  const cancel = () => {
    setDraft(project.description || '');
    setError(null);
    setEditing(false);
  };

  const save = async () => {
    const next = clampInput(draft, LIMITS.projectDescription);
    if (next.trim() === (project.description || '').trim()) {
      setEditing(false);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const result = await adminService.updateWorkspaceProject(project.project_id, {
        description: next,
      });
      if (result.task_id) {
        const polled = await pollWriteTask(result.task_id);
        if (polled.state === 'failed') {
          throw new Error(polled.detail || 'No se pudo guardar el contexto');
        }
        if (polled.state === 'timeout' || polled.state === 'not_found') {
          throw new Error('No se confirmó el cambio; reintenta o refresca.');
        }
      }
      onSaved({ ...project, ...(result.project || {}), description: next });
      setEditing(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo guardar el contexto');
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="rounded-3xl border border-gov-blue-100 bg-white p-5 dark:border-dark-border dark:bg-dark-surface">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-black text-gov-gray-900 dark:text-dark-text">Contexto del proyecto</h2>
          <p className="text-sm text-gov-gray-500 dark:text-dark-muted">
            Este bloque se inyecta al Playground cuando envías mensajes con `project_id`.
          </p>
        </div>
        {canEdit && !editing && (
          <button
            type="button"
            onClick={() => {
              setDraft(project.description || '');
              setError(null);
              setEditing(true);
            }}
            className="inline-flex shrink-0 items-center rounded-lg border border-gov-blue-100 p-1.5 text-gov-blue-800 hover:bg-gov-blue-50 dark:border-dark-border dark:text-dark-cyan"
            title="Editar contexto del proyecto"
            aria-label="Editar contexto del proyecto"
          >
            <Pencil size={14} />
          </button>
        )}
      </div>

      {editing ? (
        <div className="space-y-3">
          <textarea
            value={draft}
            onChange={(e) => setDraft(clampInput(e.target.value, LIMITS.projectDescription))}
            maxLength={LIMITS.projectDescription}
            rows={8}
            className="w-full rounded-2xl border border-gov-blue-200 bg-gov-gray-50 p-4 text-sm dark:border-dark-border dark:bg-dark-bg dark:text-dark-text"
            aria-label="Contexto / descripción del proyecto"
            autoFocus
          />
          <div className="flex flex-wrap gap-2">
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
              onClick={cancel}
              disabled={saving}
              className="inline-flex items-center gap-1 rounded-xl border border-gov-gray-200 px-3 py-2 text-sm font-bold dark:border-dark-border"
            >
              <X size={16} />
              Cancelar
            </button>
          </div>
          {error && <p className="text-sm text-red-600 dark:text-red-300">{error}</p>}
        </div>
      ) : (
        <div className="rounded-2xl bg-gov-gray-50 p-4 text-sm dark:bg-dark-bg">
          <p className="font-black text-gov-gray-900 dark:text-dark-text">{project.name}</p>
          <p className="mt-2 whitespace-pre-wrap text-gov-gray-600 dark:text-dark-muted">
            {project.description?.trim() || 'Sin descripción.'}
          </p>
        </div>
      )}
    </section>
  );
}
