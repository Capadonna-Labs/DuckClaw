'use client';

import { type FormEvent, useEffect, useState } from 'react';
import { adminService, type SkillCatalogItem } from '@/services/adminService';
import { PageShell } from '@/components/admin/PageShell';
import SettingsSection from '@/components/settings/SettingsSection';
import Link from 'next/link';
import { Blocks, Cable, Plus } from 'lucide-react';

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

  return (
    <PageShell>
      <header className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <h1 className="text-3xl font-black dark:text-dark-text">Skills</h1>
          <p className="text-sm text-gov-gray-500 mt-1">
            Átomos Python globales compartidos y skills locales de tus workers DB-first.
            Para integraciones empaquetadas (GitHub, Telegram, Reddit…), usa{' '}
            <Link href="/mcp" className="text-gov-blue-700 dark:text-dark-cyan font-semibold hover:underline">
              MCP
            </Link>{' '}
            primero.
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

      {showCreate && (
        <form
          onSubmit={createSkill}
          className="grid gap-4 rounded-3xl border border-gov-gray-100 bg-white p-5 shadow-sm dark:border-dark-border dark:bg-dark-surface lg:grid-cols-2"
        >
          <div className="lg:col-span-2">
            <h2 className="text-lg font-black dark:text-dark-text">Crear skill DB-first</h2>
            <p className="text-sm text-gov-gray-500">
              Esta metadata queda asociada a tu usuario autenticado. No se registra en carpetas compartidas.
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

      <div className="flex items-start gap-3 p-4 rounded-2xl border border-sky-200 bg-sky-50 dark:bg-sky-950/25 dark:border-sky-800/60 text-sm">
        <Cable className="shrink-0 mt-0.5 text-sky-700 dark:text-sky-300" size={20} />
        <p className="text-sky-950 dark:text-sky-100">
          <strong>MCP primero:</strong> paquetes y bridges ya integrados (servidor HTTP DuckClaw,
          stdio en <code className="text-xs font-mono">config/mcp_servers.yaml</code>, catálogo
          oficial). Esta página es para skills Python custom cuando no hay servidor MCP listo.
        </p>
      </div>

      {error && <p className="text-red-600 text-sm">{error}</p>}

      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Buscar skill…"
        maxLength={50}
        className="w-full max-w-md px-3 py-2 border rounded-xl dark:border-dark-border dark:bg-dark-surface text-sm"
      />

      <SettingsSection
        titulo="Mis skills globales"
        descripcion="Skills DB-first reutilizables entre mis workers"
        icono={<Blocks size={22} />}
      >
        <SkillTable items={filter(globalSkills)} />
      </SettingsSection>

      <SettingsSection
        titulo="Skills locales de mis agentes"
        descripcion="Python específico de workers visibles en tu catálogo DB-first"
        icono={<Blocks size={22} />}
      >
        <SkillTable items={filter(localSkills)} showWorker />
      </SettingsSection>
    </PageShell>
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
