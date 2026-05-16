'use client';

import { useEffect, useState } from 'react';
import { adminService } from '@/services/adminService';
import { PageShell } from '@/components/admin/PageShell';
import SettingsSection from '@/components/settings/SettingsSection';
import type { FlyCommandEntry } from '@/types/admin';
import { Terminal } from 'lucide-react';
import { clampInput, LIMITS } from '@/lib/validation';

export default function CommandsPage() {
  const [header, setHeader] = useState('');
  const [commands, setCommands] = useState<FlyCommandEntry[]>([]);
  const [leila, setLeila] = useState(false);
  const [q, setQ] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    adminService
      .listFlyCommands()
      .then((r) => {
        setHeader(r.header ?? '');
        setCommands(r.commands ?? []);
        setLeila(r.leila_enabled ?? false);
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Error'));
  }, []);

  const needle = q.trim().toLowerCase();
  const filtered = needle
    ? commands.filter(
        (c) =>
          c.cmd.toLowerCase().includes(needle) || c.description.toLowerCase().includes(needle)
      )
    : commands;

  return (
    <PageShell>
      <header>
        <h1 className="text-3xl font-black dark:text-dark-text">Fly commands</h1>
        <p className="text-sm text-gov-gray-500 dark:text-dark-muted mt-1">
          Catálogo sincronizado con guardrails (mismos comandos que <code className="text-xs">/help</code>{' '}
          en Telegram)
        </p>
      </header>

      {error && <p className="text-red-600 text-sm">{error}</p>}

      <SettingsSection
        titulo="Referencia"
        descripcion={leila ? 'Incluye entradas Leila (DUCKCLAW_LEILA_FLY_COMMANDS)' : 'Base estándar'}
        icono={<Terminal size={22} />}
      >
        {header && (
          <p className="text-sm text-gov-gray-600 dark:text-dark-muted mb-4 whitespace-pre-wrap">
            {header}
          </p>
        )}
        <input
          value={q}
          onChange={(e) => setQ(clampInput(e.target.value, LIMITS.commandSearch))}
          maxLength={LIMITS.commandSearch}
          placeholder="Buscar comando…"
          className="w-full max-w-md mb-4 px-3 py-2 border rounded-xl dark:border-dark-border dark:bg-dark-bg text-sm"
        />
        <div className="overflow-hidden rounded-2xl border dark:border-dark-border max-h-[70vh] overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-gov-gray-50 dark:bg-dark-bg">
              <tr>
                <th className="px-4 py-2 text-left font-bold w-48">Comando</th>
                <th className="px-4 py-2 text-left font-bold">Descripción</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((c) => (
                <tr key={c.cmd} className="border-t dark:border-dark-border">
                  <td className="px-4 py-2 font-mono text-xs text-gov-blue-700 dark:text-dark-cyan align-top">
                    {c.cmd}
                  </td>
                  <td className="px-4 py-2 text-gov-gray-700 dark:text-dark-muted">{c.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-4 text-xs text-gov-gray-500">
          Gestión en vivo: usa Telegram con un usuario <strong>admin</strong> en la whitelist. Ver{' '}
          <code className="font-mono">docs/COMANDOS.md</code>.
        </p>
      </SettingsSection>
    </PageShell>
  );
}
