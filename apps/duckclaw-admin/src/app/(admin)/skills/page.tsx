'use client';

import { useEffect, useState } from 'react';
import { adminService, type SkillCatalogItem } from '@/services/adminService';
import { PageShell } from '@/components/admin/PageShell';
import SettingsSection from '@/components/settings/SettingsSection';
import { Blocks } from 'lucide-react';

export default function SkillsPage() {
  const [globalSkills, setGlobalSkills] = useState<SkillCatalogItem[]>([]);
  const [localSkills, setLocalSkills] = useState<SkillCatalogItem[]>([]);
  const [q, setQ] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    adminService
      .getSkillsCatalog()
      .then((r) => {
        setGlobalSkills(r.global ?? []);
        setLocalSkills(r.template_local ?? []);
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Error'));
  }, []);

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
      <header>
        <h1 className="text-3xl font-black dark:text-dark-text">Skills</h1>
        <p className="text-sm text-gov-gray-500 mt-1">
          Catálogo en <code className="text-xs font-mono">forge/skills/</code> y skills por worker
          en <code className="text-xs">forge/templates/&lt;id&gt;/skills/</code>
        </p>
      </header>

      {error && <p className="text-red-600 text-sm">{error}</p>}

      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Buscar skill…"
        maxLength={50}
        className="w-full max-w-md px-3 py-2 border rounded-xl dark:border-dark-border dark:bg-dark-surface text-sm"
      />

      <SettingsSection
        titulo="Skills globales (forge/skills)"
        descripcion="Bridges reutilizables entre workers"
        icono={<Blocks size={22} />}
      >
        <SkillTable items={filter(globalSkills)} />
      </SettingsSection>

      <SettingsSection
        titulo="Skills locales por plantilla"
        descripcion="Python específico de un worker"
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
