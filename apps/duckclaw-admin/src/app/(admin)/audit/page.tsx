'use client';

import { useEffect, useState } from 'react';
import { adminService, type AuditEntry } from '@/services/adminService';
import { PageShell } from '@/components/admin/PageShell';
import SettingsSection from '@/components/settings/SettingsSection';
import { ClipboardList } from 'lucide-react';
import { useAuthStore } from '@/store/authStore';
import { useRouter } from 'next/navigation';

export default function AuditPage() {
  const { usuario } = useAuthStore();
  const router = useRouter();
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (usuario?.rol !== 'admin') {
      router.replace('/overview');
      return;
    }
    adminService
      .getAuditLog(200)
      .then((r) => setEntries(r.entries ?? []))
      .catch((e) => setError(e instanceof Error ? e.message : 'Error'));
  }, [usuario?.rol, router]);

  if (usuario?.rol !== 'admin') {
    return null;
  }

  return (
    <PageShell>
      <header>
        <h1 className="text-3xl font-black dark:text-dark-text">Auditoría</h1>
        <p className="text-sm text-gov-gray-500 dark:text-dark-muted mt-1">
          Cambios realizados desde la consola (solo rol admin). Archivo:{' '}
          <code className="text-xs">.duckclaw/admin-audit.jsonl</code>
        </p>
      </header>

      {error && <p className="text-red-600 text-sm">{error}</p>}

      <SettingsSection
        titulo="Registro de eventos"
        descripcion="Plantillas, env, runtime, whitelist Telegram"
        icono={<ClipboardList size={22} />}
      >
        <AuditTable entries={entries} />
      </SettingsSection>
    </PageShell>
  );
}

function AuditTable({ entries }: { entries: AuditEntry[] }) {
  if (entries.length === 0) {
    return (
      <p className="text-sm text-gov-gray-500 py-8 text-center">
        Sin eventos aún. Las acciones de escritura quedarán registradas aquí.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto rounded-2xl border dark:border-dark-border max-h-[70vh]">
      <table className="w-full text-sm">
        <thead className="sticky top-0 bg-gov-gray-50 dark:bg-dark-bg text-left">
          <tr>
            <th className="px-3 py-2 font-bold">Fecha (UTC)</th>
            <th className="px-3 py-2 font-bold">Actor</th>
            <th className="px-3 py-2 font-bold">Acción</th>
            <th className="px-3 py-2 font-bold">Recurso</th>
            <th className="px-3 py-2 font-bold">Detalle</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((e, i) => (
            <tr key={`${e.ts}-${i}`} className="border-t dark:border-dark-border">
              <td className="px-3 py-2 text-xs whitespace-nowrap">{e.ts}</td>
              <td className="px-3 py-2 text-xs">{e.actor}</td>
              <td className="px-3 py-2 font-mono text-xs">{e.action}</td>
              <td className="px-3 py-2 font-mono text-xs max-w-[140px] truncate" title={e.resource}>
                {e.resource}
              </td>
              <td className="px-3 py-2 font-mono text-xs break-all">{e.detail}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
