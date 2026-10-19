'use client';

import { useCallback, useEffect, useState } from 'react';
import { Download } from 'lucide-react';
import { adminService } from '@/services/adminService';
import { pollWriteTask } from '@/lib/pollWriteTask';

type SeedTemplate = {
  template_id: string;
  worker_id: string;
  name: string;
  description: string;
  imported: boolean;
};

/** Optional agents bundled with DuckClaw (forge/seed) that are not in the catalog yet. */
export function BundledTemplatesPanel({ onImported }: { onImported: () => void }) {
  const [items, setItems] = useState<SeedTemplate[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const reload = useCallback(() => {
    adminService
      .listSeedTemplates()
      .then((res) => setItems(res.templates.filter((t) => !t.imported)))
      .catch(() => setItems([]));
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const importTemplate = async (template: SeedTemplate) => {
    setBusy(template.template_id);
    setMessage(null);
    try {
      const { task_id } = await adminService.importSeedTemplate(template.template_id);
      const result = await pollWriteTask(task_id, { intervalMs: 1500, maxAttempts: 40 });
      if (result.state === 'success') {
        setMessage(`«${template.name}» agregado a tus agentes.`);
        reload();
        onImported();
      } else {
        const detail = 'detail' in result && result.detail ? `: ${result.detail}` : '';
        setMessage(`No se pudo importar «${template.name}» (${result.state}${detail}).`);
      }
    } catch (e) {
      setMessage(e instanceof Error ? e.message : 'Error al importar');
    } finally {
      setBusy(null);
    }
  };

  if (!items.length && !message) {
    return null;
  }

  return (
    <section className="rounded-xl border border-gov-gray-200 p-4 dark:border-dark-border">
      <h2 className="text-sm font-semibold text-gov-gray-900 dark:text-dark-text">Plantillas disponibles</h2>
      <p className="mt-1 text-xs text-gov-gray-600 dark:text-dark-muted">
        Agentes opcionales incluidos en DuckClaw. Importarlos los agrega a tu catálogo; no se activan solos.
      </p>
      <ul className="mt-3 grid gap-3 md:grid-cols-2">
        {items.map((t) => (
          <li
            key={t.template_id}
            className="flex items-start justify-between gap-3 rounded-lg border border-gov-gray-200 p-3 dark:border-dark-border"
          >
            <div className="min-w-0">
              <p className="text-sm font-medium text-gov-gray-900 dark:text-dark-text">{t.name}</p>
              <p className="mt-1 line-clamp-3 text-xs text-gov-gray-600 dark:text-dark-muted">{t.description}</p>
            </div>
            <button
              type="button"
              disabled={busy !== null}
              onClick={() => void importTemplate(t)}
              className="inline-flex shrink-0 items-center gap-1 rounded-lg border border-gov-gray-300 px-3 py-1.5 text-xs font-semibold disabled:opacity-50 dark:border-dark-border"
            >
              <Download size={14} />
              {busy === t.template_id ? 'Importando…' : 'Importar'}
            </button>
          </li>
        ))}
      </ul>
      {message ? <p className="mt-3 text-xs text-gov-gray-700 dark:text-dark-muted">{message}</p> : null}
    </section>
  );
}
