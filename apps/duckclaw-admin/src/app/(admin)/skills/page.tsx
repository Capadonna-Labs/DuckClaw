'use client';

import { type FormEvent, useEffect, useState } from 'react';
import { adminService, type SkillCatalogItem } from '@/services/adminService';
import { PageShell } from '@/components/admin/PageShell';
import SettingsSection from '@/components/settings/SettingsSection';
import { Blocks, Plus, Search } from 'lucide-react';

const EMPTY_SKILL_FORM = {
  name: '',
  description: '',
  skillType: 'python',
  implementationRef: '',
};

export default function SkillsPage() {
  const [globalSkills, setGlobalSkills] = useState<SkillCatalogItem[]>([]);
  const [localSkills, setLocalSkills] = useState<SkillCatalogItem[]>([]);
  const [q, setQ] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState(EMPTY_SKILL_FORM);
  const [saving, setSaving] = useState(false);
  const [filterScope, setFilterScope] = useState<'all' | 'global' | 'local'>('all');

  const loadSkills = () =>
    adminService.getSkillsCatalog().then((r) => {
      setGlobalSkills(r.global ?? []);
      setLocalSkills(r.template_local ?? []);
    });

  useEffect(() => {
    loadSkills().catch((e) => setError(e instanceof Error ? e.message : 'Error'));
  }, []);

  const defaultImplementationRef = (name: string) => {
    const slug = name.trim().toLowerCase().replace(/[^a-z0-9_.-]+/g, '_');
    return slug ? `db://skills/${slug}.py` : '';
  };

  const createSkill = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
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
      setForm(EMPTY_SKILL_FORM);
      setShowCreate(false);
      await loadSkills();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error creando skill');
    } finally {
      setSaving(false);
    }
  };

  const needle = q.trim().toLowerCase();
  const filter = (items: SkillCatalogItem[]) =>
    !needle
      ? items
      : items.filter(
          (s) =>
            s.id.toLowerCase().includes(needle) ||
            s.path.toLowerCase().includes(needle) ||
            (s.worker_id ?? '').toLowerCase().includes(needle)
        );
  const filteredGlobalSkills = filter(globalSkills);
  const filteredLocalSkills = filter(localSkills);
  const totalSkills = globalSkills.length + localSkills.length;
  const hasAnySkill = totalSkills > 0;
  const showGlobalSkills = filterScope === 'all' || filterScope === 'global';
  const showLocalSkills = filterScope === 'all' || filterScope === 'local';

  return (
    <PageShell>
      <header className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <h1 className="text-3xl font-black dark:text-dark-text">Skills</h1>
          <p className="mt-1 max-w-2xl text-sm text-gov-gray-500 dark:text-dark-muted">
            Crea metadata DB-first y revisa capacidades globales o locales sin mezclar
            responsabilidades con MCP.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setShowCreate((v) => !v)}
          className="inline-flex items-center justify-center gap-2 rounded-xl bg-gov-blue-800 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-gov-blue-700 dark:bg-dark-cyan dark:text-slate-950"
        >
          <Plus size={18} />
          Nueva skill
        </button>
      </header>

      <section className="rounded-3xl border border-gov-gray-100 bg-white p-5 shadow-sm dark:border-dark-border dark:bg-dark-surface">
        <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-lg font-black text-gov-gray-900 dark:text-dark-text">
              Resumen de skills
            </h2>
            <p className="text-sm text-gov-gray-500 dark:text-dark-muted">
              Vista separada para inventario, búsqueda y creación de capacidades.
            </p>
          </div>
        </div>
        <div className="grid gap-3 md:grid-cols-3">
          <SkillSummaryCard label="Total" value={totalSkills} />
          <SkillSummaryCard label="Globales" value={globalSkills.length} />
          <SkillSummaryCard label="Locales" value={localSkills.length} />
        </div>
      </section>

      {showCreate && (
        <form
          onSubmit={createSkill}
          className="grid gap-4 rounded-3xl border border-gov-gray-100 bg-white p-5 shadow-sm dark:border-dark-border dark:bg-dark-surface lg:grid-cols-2"
        >
          <div className="lg:col-span-2">
            <h2 className="text-lg font-black dark:text-dark-text">Crear skill</h2>
            <p className="text-sm text-gov-gray-500">
              Quedará disponible para tus agentes.
            </p>
          </div>
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
          <div className="flex gap-2 lg:col-span-2">
            <button
              type="submit"
              disabled={saving}
              className="rounded-xl bg-slate-950 px-4 py-2 text-sm font-semibold text-white disabled:opacity-60 dark:bg-white dark:text-slate-950"
            >
              {saving ? 'Creando...' : 'Crear skill'}
            </button>
            <button
              type="button"
              onClick={() => {
                setShowCreate(false);
                setForm(EMPTY_SKILL_FORM);
              }}
              className="rounded-xl border px-4 py-2 text-sm font-semibold dark:border-dark-border"
            >
              Cancelar
            </button>
          </div>
        </form>
      )}

      {error && <p className="text-red-600 text-sm">{error}</p>}

      <section className="flex flex-col gap-3 rounded-3xl border border-gov-gray-100 bg-white p-4 shadow-sm dark:border-dark-border dark:bg-dark-surface lg:flex-row lg:items-center lg:justify-between">
        <div className="relative max-w-md flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gov-gray-400" size={18} />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Buscar skill…"
            maxLength={50}
            className="w-full rounded-xl border py-2 pl-10 pr-3 text-sm dark:border-dark-border dark:bg-dark-bg"
          />
        </div>
        <div className="flex flex-wrap gap-2">
          {[
            ['all', 'Todas'],
            ['global', 'Globales'],
            ['local', 'Locales'],
          ].map(([value, label]) => (
            <button
              key={value}
              type="button"
              onClick={() => setFilterScope(value as 'all' | 'global' | 'local')}
              className={`rounded-xl px-3 py-2 text-xs font-black transition-colors ${
                filterScope === value
                  ? 'bg-gov-blue-700 text-white'
                  : 'border border-gov-gray-200 text-gov-gray-600 hover:border-gov-blue-300 dark:border-dark-border dark:text-dark-muted'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </section>

      {!hasAnySkill && <EmptySkillsState onCreate={() => setShowCreate(true)} />}

      {showGlobalSkills && (
        <SettingsSection
          titulo="Mis skills globales"
          descripcion="Capacidades reutilizables entre mis agentes"
          icono={<Blocks size={22} />}
        >
          <SkillTable items={filteredGlobalSkills} />
        </SettingsSection>
      )}

      {showLocalSkills && (
        <SettingsSection
          titulo="Skills locales de mis agentes"
          descripcion="Capacidades específicas de cada agente"
          icono={<Blocks size={22} />}
        >
          <SkillTable items={filteredLocalSkills} showWorker />
        </SettingsSection>
      )}
    </PageShell>
  );
}

function SkillSummaryCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-2xl border border-gov-gray-100 bg-gov-gray-50 p-4 dark:border-dark-border dark:bg-dark-bg">
      <p className="text-xs font-black uppercase tracking-[0.18em] text-gov-gray-500 dark:text-dark-muted">
        {label}
      </p>
      <p className="mt-2 text-3xl font-black text-gov-gray-900 dark:text-dark-text">{value}</p>
    </div>
  );
}

function EmptySkillsState({ onCreate }: { onCreate: () => void }) {
  return (
    <section className="rounded-3xl border border-dashed border-gov-blue-200 bg-gov-blue-50/50 p-6 text-center dark:border-dark-border dark:bg-dark-bg">
      <h2 className="text-lg font-black text-gov-gray-900 dark:text-dark-text">
        Todavía no hay skills DB-first
      </h2>
      <p className="mx-auto mt-2 max-w-xl text-sm text-gov-gray-500 dark:text-dark-muted">
        Crea una skill global para reutilizarla entre agentes. Las skills locales aparecen desde
        snapshots activos de workers.
      </p>
      <button
        type="button"
        onClick={onCreate}
        className="mt-4 inline-flex items-center justify-center gap-2 rounded-xl bg-gov-blue-700 px-4 py-2 text-sm font-black text-white hover:bg-gov-blue-800"
      >
        <Plus size={16} />
        Crear primera skill
      </button>
    </section>
  );
}

function SkillTable({
  items,
  showWorker,
}: {
  items: SkillCatalogItem[];
  showWorker?: boolean;
}) {
  if (items.length === 0) {
    return <p className="text-sm text-gov-gray-500 py-4">Sin resultados.</p>;
  }
  return (
    <div className="overflow-x-auto rounded-2xl border dark:border-dark-border max-h-[50vh]">
      <table className="w-full text-sm">
        <thead className="bg-gov-gray-50 dark:bg-dark-bg sticky top-0">
          <tr>
            <th className="px-3 py-2 text-left">ID</th>
            {showWorker && <th className="px-3 py-2 text-left">Worker</th>}
            <th className="px-3 py-2 text-left">Ruta</th>
          </tr>
        </thead>
        <tbody>
          {items.map((s) => (
            <tr key={`${s.worker_id ?? ''}-${s.id}`} className="border-t dark:border-dark-border">
              <td className="px-3 py-2 font-mono text-xs">{s.id}</td>
              {showWorker && <td className="px-3 py-2 text-xs">{s.worker_id}</td>}
              <td className="px-3 py-2 font-mono text-[10px] text-gov-gray-500">{s.path}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
