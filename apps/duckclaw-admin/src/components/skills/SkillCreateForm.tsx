'use client';

import { type FormEvent, useState } from 'react';
import { Plus } from 'lucide-react';
import { adminService } from '@/services/adminService';
import {
  defaultImplementationRef,
  EMPTY_SKILL_FORM,
  type SkillFormState,
} from '@/components/skills/useSkillsCatalog';

export function SkillCreateForm({ onCreated }: { onCreated?: () => Promise<void> | void }) {
  const [form, setForm] = useState<SkillFormState>(EMPTY_SKILL_FORM);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<string | null>(null);

  const createSkill = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setCreated(null);
    setSaving(true);
    try {
      const implementationRef = form.implementationRef.trim() || defaultImplementationRef(form.name);
      await adminService.createSkill({
        name: form.name.trim(),
        description: form.description.trim(),
        skill_type: form.skillType.trim() || 'python',
        implementation_ref: implementationRef,
        visibility: 'private',
      });
      setCreated(form.name.trim());
      setForm(EMPTY_SKILL_FORM);
      await onCreated?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error creando skill');
    } finally {
      setSaving(false);
    }
  };

  return (
    <form
      onSubmit={createSkill}
      className="grid gap-4 rounded-3xl border border-gov-gray-100 bg-white p-5 shadow-sm dark:border-dark-border dark:bg-dark-surface lg:grid-cols-2"
    >
      <div className="lg:col-span-2">
        <h2 className="text-lg font-black dark:text-dark-text">Nueva skill</h2>
        <p className="text-sm text-gov-gray-500 dark:text-dark-muted">
          Crea metadata DB-first reutilizable por tus agentes.
        </p>
      </div>
      {error && <p className="text-sm text-red-600 lg:col-span-2">{error}</p>}
      {created && (
        <p className="rounded-xl bg-green-50 px-3 py-2 text-sm font-bold text-green-700 dark:bg-green-950/30 dark:text-green-300 lg:col-span-2">
          Skill creada: {created}
        </p>
      )}
      <label className="space-y-1 text-sm font-semibold">
        <span>Nombre</span>
        <input
          value={form.name}
          onChange={(e) =>
            setForm((prev) => ({
              ...prev,
              name: e.target.value,
              implementationRef: prev.implementationRef || defaultImplementationRef(e.target.value),
            }))
          }
          required
          placeholder="customer_lookup"
          className="w-full rounded-xl border px-3 py-2 text-sm dark:border-dark-border dark:bg-dark-bg"
        />
      </label>
      <label className="space-y-1 text-sm font-semibold">
        <span>Tipo</span>
        <input
          value={form.skillType}
          onChange={(e) => setForm((prev) => ({ ...prev, skillType: e.target.value }))}
          className="w-full rounded-xl border px-3 py-2 text-sm dark:border-dark-border dark:bg-dark-bg"
        />
      </label>
      <label className="space-y-1 text-sm font-semibold lg:col-span-2">
        <span>Referencia implementación</span>
        <input
          value={form.implementationRef}
          onChange={(e) => setForm((prev) => ({ ...prev, implementationRef: e.target.value }))}
          required
          placeholder="db://skills/customer_lookup.py"
          className="w-full rounded-xl border px-3 py-2 font-mono text-sm dark:border-dark-border dark:bg-dark-bg"
        />
      </label>
      <label className="space-y-1 text-sm font-semibold lg:col-span-2">
        <span>Descripción</span>
        <textarea
          value={form.description}
          onChange={(e) => setForm((prev) => ({ ...prev, description: e.target.value }))}
          rows={3}
          className="w-full rounded-xl border px-3 py-2 text-sm dark:border-dark-border dark:bg-dark-bg"
        />
      </label>
      <button
        type="submit"
        disabled={saving}
        className="inline-flex w-fit items-center gap-2 rounded-xl bg-gov-blue-700 px-4 py-2 text-sm font-black text-white hover:bg-gov-blue-800 disabled:opacity-60 lg:col-span-2"
      >
        <Plus size={16} />
        {saving ? 'Creando...' : 'Crear skill'}
      </button>
    </form>
  );
}
