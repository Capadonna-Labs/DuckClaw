'use client';

import { useId, useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';

interface SettingsSectionProps {
  titulo: string;
  descripcion?: string;
  children: React.ReactNode;
  icono: React.ReactNode;
  /** Si false, la sección arranca colapsada (patrón Progressive Disclosure). */
  defaultOpen?: boolean;
  /** Desactiva acordeón (siempre visible, sin chevron). */
  collapsible?: boolean;
}

export default function SettingsSection({
  titulo,
  descripcion,
  children,
  icono,
  defaultOpen = true,
  collapsible = true,
}: SettingsSectionProps) {
  const [open, setOpen] = useState(defaultOpen);
  const panelId = useId();

  const toggle = () => {
    if (collapsible) setOpen((o) => !o);
  };

  return (
    <section className="bg-white dark:bg-dark-surface rounded-3xl border border-gov-gray-100 dark:border-dark-border shadow-sm overflow-hidden transition-all">
      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        aria-controls={panelId}
        disabled={!collapsible}
        className="w-full flex items-center gap-3 px-6 py-4 text-left bg-white dark:bg-dark-surface hover:bg-gov-gray-50/80 dark:hover:bg-dark-bg/50 transition-colors disabled:cursor-default disabled:hover:bg-white dark:disabled:hover:bg-dark-surface"
      >
        {collapsible ? (
          open ? (
            <ChevronDown size={18} className="shrink-0 text-gov-gray-500" aria-hidden />
          ) : (
            <ChevronRight size={18} className="shrink-0 text-gov-gray-500" aria-hidden />
          )
        ) : (
          <span className="w-[18px] shrink-0" aria-hidden />
        )}
        <span className="p-2.5 bg-gov-gray-50 dark:bg-dark-bg rounded-2xl text-gov-blue-700 dark:text-dark-cyan shrink-0">
          {icono}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-lg font-bold text-gov-gray-900 dark:text-dark-text tracking-tight">
            {titulo}
          </span>
          {descripcion && (
            <span className="block text-sm text-gov-gray-500 dark:text-dark-muted mt-0.5 truncate">
              {descripcion}
            </span>
          )}
        </span>
      </button>

      {open && (
        <Panel id={panelId} className="border-t border-gov-gray-100 dark:border-dark-border p-6">
          {children}
        </Panel>
      )}
    </section>
  );
}

function Panel({ id, className, children }: { id: string; className?: string; children: React.ReactNode }) {
  return (
    <div id={id} className={className}>
      {children}
    </div>
  );
}
