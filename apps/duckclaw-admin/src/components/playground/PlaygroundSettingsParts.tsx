'use client';

import { useEffect, useState, type ReactNode } from 'react';
import Link from 'next/link';
import { ChevronRight, Copy, Terminal, X } from 'lucide-react';
import { adminService } from '@/services/adminService';
import { KnowledgeScopeControl } from '@/components/playground/KnowledgeScopeControl';
import { workerOptionId, workerOptionLabel } from '@/lib/workerOptions';
import type { KnowledgeScope } from '@/lib/knowledgeScope';
import type { FlyCommandEntry } from '@/types/admin';

import type { PlaygroundConfig } from './playgroundTypes';

const FREQUENT_CHAT_COMMANDS = new Set(['/team', '/vault', '/model', '/workers']);

export function SettingsModal({
  title,
  description,
  onClose,
  size = 'default',
  children,
}: {
  title: string;
  description: string;
  onClose: () => void;
  size?: 'default' | 'wide';
  children: ReactNode;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-gov-blue-950/40 p-3 backdrop-blur-sm sm:items-center">
      <button
        type="button"
        className="absolute inset-0"
        aria-label="Cerrar modal"
        onClick={onClose}
      />
      <section
        className={`relative z-10 flex max-h-[min(760px,92dvh)] w-full flex-col overflow-hidden rounded-[2rem] border border-gov-blue-100 bg-white shadow-2xl dark:border-dark-border dark:bg-dark-surface ${
          size === 'wide' ? 'max-w-lg' : 'max-w-md'
        }`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <header className="flex items-start justify-between gap-3 border-b border-gov-gray-100 p-4 dark:border-dark-border">
          <div className="min-w-0">
            <h3 className="text-base font-black dark:text-dark-text">{title}</h3>
            <p className="mt-1 text-xs text-gov-gray-500 dark:text-dark-muted">{description}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full p-2 text-gov-gray-500 hover:bg-gov-gray-100 dark:hover:bg-dark-bg"
            aria-label="Cerrar"
          >
            <X size={18} />
          </button>
        </header>
        <div className="scrollbar-thin min-h-0 flex-1 overflow-y-auto p-4">{children}</div>
      </section>
    </div>
  );
}

export function SettingValue({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl bg-gov-gray-50 px-4 py-3 dark:bg-dark-bg">
      <p className="text-[11px] font-bold uppercase tracking-wide text-gov-gray-500">{label}</p>
      <p className="mt-1 truncate text-base font-semibold dark:text-dark-text" title={value}>
        {value}
      </p>
    </div>
  );
}

export function ProjectAgentControls({
  config,
  projectId,
  knowledgeScope,
  activeProject,
  projectWorkerIds,
  selectableWorkers,
  workerId,
  onProjectChange,
  onWorkerChange,
  onKnowledgeScopeChange,
}: {
  config: PlaygroundConfig | null;
  projectId: string;
  knowledgeScope: KnowledgeScope;
  activeProject?: NonNullable<PlaygroundConfig['projects']>[number];
  projectWorkerIds: string[];
  selectableWorkers: NonNullable<PlaygroundConfig['workers']>;
  workerId: string;
  onProjectChange: (projectId: string) => void;
  onWorkerChange: (workerId: string) => void;
  onKnowledgeScopeChange: (scope: KnowledgeScope) => void;
}) {
  return (
    <div className="space-y-5">
      {(config?.projects?.length ?? 0) > 0 && (
        <label className="block space-y-1.5">
          <span className="text-xs font-bold text-gov-gray-500">Proyecto</span>
          <select
            value={projectId}
            onChange={(e) => onProjectChange(e.target.value)}
            className="w-full rounded-xl border px-3 py-2 text-sm dark:border-dark-border dark:bg-dark-bg"
          >
            <option value="">Todos los agentes</option>
            {(config?.projects ?? []).map((p) => (
              <option key={p.project_id} value={p.project_id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
      )}

      <label className="block space-y-1.5">
        <span className="text-xs font-bold text-gov-gray-500">
          {activeProject ? 'Agente guía' : 'Agente'}
        </span>
        <select
          value={workerId}
          onChange={(e) => onWorkerChange(e.target.value)}
          className="w-full rounded-xl border px-3 py-2 text-sm dark:border-dark-border dark:bg-dark-bg"
        >
          {selectableWorkers.map((w) => {
            const id = workerOptionId(w);
            const label = workerOptionLabel(w);
            return (
              <option key={id} value={id}>
                {label}
              </option>
            );
          })}
        </select>
      </label>

      <KnowledgeScopeControl
        value={knowledgeScope}
        projectId={projectId}
        onChange={onKnowledgeScopeChange}
      />

      <p className="rounded-2xl border border-gov-blue-100 bg-gov-blue-50/70 p-3 text-xs text-gov-blue-800 dark:border-dark-border dark:bg-dark-bg dark:text-dark-cyan">
        {activeProject
          ? projectWorkerIds.length > 0
            ? `Proyecto ${activeProject.name}: solo agentes asignados.`
            : `Proyecto ${activeProject.name}: sin agentes asignados, se muestran todos.`
          : 'Sin filtro de proyecto.'}
      </p>

      {workerId && (
        <Link
          href={`/templates/${workerId}`}
          className="inline-flex items-center gap-1 text-xs font-bold text-gov-blue-700 dark:text-dark-cyan"
        >
          Editar agente <ChevronRight size={12} />
        </Link>
      )}
    </div>
  );
}

export function ChatCommandsPanel() {
  const [showAll, setShowAll] = useState(false);
  const [commands, setCommands] = useState<FlyCommandEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    adminService
      .listFlyCommands()
      .then((res) => {
        if (!cancelled) setCommands(res.commands ?? []);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'No se pudieron cargar los comandos');
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const frequentCommands = commands.filter((command) =>
    FREQUENT_CHAT_COMMANDS.has(command.cmd.trim().split(/\s+/)[0] ?? '')
  );
  const defaultCommands = frequentCommands.length > 0 ? frequentCommands : commands.slice(0, 4);
  const visibleCommands = showAll ? commands : defaultCommands;
  const canExpand = commands.length > defaultCommands.length;

  const copyCommand = async (cmd: string) => {
    try {
      await navigator.clipboard.writeText(cmd);
      setCopied(cmd);
      window.setTimeout(() => setCopied(null), 1500);
    } catch {
      /* clipboard unavailable */
    }
  };

  return (
    <div className="space-y-3">
          <p className="text-xs text-gov-gray-500 flex items-center gap-2">
            <Terminal size={14} />
            Comandos del chat para usar dentro del Playground.
          </p>
          <div className="flex items-center justify-between gap-3">
            <p className="text-[10px] font-black uppercase tracking-wide text-gov-gray-500">
              Comandos frecuentes
            </p>
            {canExpand && (
              <button
                type="button"
                onClick={() => setShowAll((value) => !value)}
                className="text-xs font-bold text-gov-blue-700 dark:text-dark-cyan"
              >
                {showAll ? 'Ver frecuentes' : 'Ver todos'}
              </button>
            )}
          </div>

          {error && (
            <p className="text-xs text-amber-800 dark:text-amber-200 bg-amber-50 dark:bg-amber-950/40 rounded-xl p-3">
              {error}
            </p>
          )}

          <div className="space-y-2">
            {visibleCommands.map((command) => (
              <button
                key={command.cmd}
                type="button"
                onClick={() => void copyCommand(command.cmd)}
                className="w-full text-left rounded-2xl border dark:border-dark-border p-3 hover:border-gov-blue-400 hover:bg-gov-blue-50/50 dark:hover:bg-dark-bg transition-colors"
              >
                <span className="flex items-start justify-between gap-2">
                  <span className="min-w-0">
                    <span className="block font-mono text-xs font-black text-gov-blue-700 dark:text-dark-cyan truncate">
                      {command.cmd}
                    </span>
                    <span className="block text-xs text-gov-gray-500 mt-1">
                      {command.description}
                    </span>
                  </span>
                  <Copy size={14} className="text-gov-gray-400 shrink-0 mt-0.5" />
                </span>
                {copied === command.cmd && (
                  <span className="block text-[10px] font-bold text-emerald-700 dark:text-emerald-400 mt-2">
                    Copiado
                  </span>
                )}
              </button>
            ))}
            {!error && visibleCommands.length === 0 && (
              <p className="text-xs text-gov-gray-500 rounded-xl border border-dashed dark:border-dark-border p-3">
                Sin comandos disponibles por ahora.
              </p>
            )}
          </div>
    </div>
  );
}
