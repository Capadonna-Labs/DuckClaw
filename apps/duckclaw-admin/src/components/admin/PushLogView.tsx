'use client';

import { useEffect, useState } from 'react';
import { Bell } from 'lucide-react';
import { platformApi, type PushLogEntry } from '@/services/admin/platformApi';
import { ViewChrome, type EmbeddedViewProps } from '@/components/admin/embeddedView';
import SettingsSection from '@/components/settings/SettingsSection';

export default function PushLogView({ embedded = false }: EmbeddedViewProps) {
  const [entries, setEntries] = useState<PushLogEntry[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    platformApi
      .getPushLog(200)
      .then((r) => setEntries(r.entries ?? []))
      .catch((e) => setError(e instanceof Error ? e.message : 'Error'));
  }, []);

  return (
    <ViewChrome embedded={embedded}>
      {error && <p className="text-red-600 text-sm">{error}</p>}
      <SettingsSection
        titulo="Avisos enviados"
        descripcion="Cada notificación push (chat, metas y jobs de las extensiones) con su texto completo, por si se descartó en el teléfono"
        icono={<Bell size={22} />}
      >
        {entries.length === 0 ? (
          <p className="text-sm text-gov-gray-500 py-8 text-center">Sin avisos registrados aún.</p>
        ) : (
          <ul className="scrollbar-thin max-h-[70vh] space-y-2 overflow-y-auto">
            {entries.map((e) => (
              <li key={e.id} className="rounded-2xl border p-3 dark:border-dark-border">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span className="font-bold">{e.title}</span>
                  <span className="text-xs text-gov-gray-500">
                    {e.created_at.slice(0, 16)} UTC · {e.sent > 0 ? 'entregado' : 'no entregado'}
                    {e.error ? ` (${e.error})` : ''}
                  </span>
                </div>
                <p className="mt-1 whitespace-pre-wrap text-sm">{e.body}</p>
                <p className="mt-1 break-all font-mono text-[11px] text-gov-gray-500">{e.tag}</p>
              </li>
            ))}
          </ul>
        )}
      </SettingsSection>
    </ViewChrome>
  );
}
