'use client';

import Link from 'next/link';
import { BookOpen, ChevronDown, Database, FileCode, Layers, Puzzle } from 'lucide-react';
import { useState } from 'react';

const LAYERS = [
  {
    icon: Puzzle,
    title: '1. Skill de plataforma',
    storage: 'Código en `packages/agents` (bridges)',
    activation: 'Manifest del agente → array `skills:` + categorías en editor Herramientas',
    example: 'github, search_project_knowledge, comfyui',
    note: 'No aparece en `admin_skills`. Se activa por nombre en el manifest.',
  },
  {
    icon: Database,
    title: '2. Skill de catálogo (global)',
    storage: 'DuckDB gateway → `main.admin_skills`',
    activation: 'Crear metadata aquí + `implementation_ref` válido + marcar en manifest del agente',
    example: 'customer_lookup → db://skills/customer_lookup.py',
    note: 'Reutilizable entre agentes del tenant. Por defecto visibility private.',
  },
  {
    icon: FileCode,
    title: '3. Skill local del agente',
    storage: 'Snapshot del worker en `admin_worker_versions` → `skills/*.py`',
    activation: 'Archivo Python en el bundle del agente; se carga con `get_tools()`',
    example: 'db://admin_worker_catalog/{uid}/skills/mi_tool.py',
    note: 'Atada a un solo agente. Ideal para lógica muy específica.',
  },
] as const;

export function SkillsConceptPanel({ defaultOpen = false }: { defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <section className="rounded-3xl border border-gov-blue-100 bg-gradient-to-br from-gov-blue-50/80 to-white dark:border-dark-border dark:from-dark-bg dark:to-dark-surface">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-start justify-between gap-3 p-5 text-left"
        aria-expanded={open}
      >
        <div className="flex items-start gap-3">
          <span className="rounded-2xl bg-white p-2.5 text-gov-blue-700 shadow-sm dark:bg-dark-surface dark:text-dark-cyan">
            <BookOpen size={20} aria-hidden />
          </span>
          <div>
            <h2 className="text-base font-black text-gov-gray-900 dark:text-dark-text">
              ¿Qué es una skill en DuckClaw?
            </h2>
            <p className="mt-1 max-w-2xl text-sm text-gov-gray-600 dark:text-dark-muted">
              Una <strong className="font-bold">skill</strong> es una capacidad que el LLM invoca como{' '}
              <em>tool</em> (función). Hay tres capas; crear metadata en DB no basta — hay que{' '}
              <strong className="font-bold">activarla en el manifest</strong> del agente.
            </p>
          </div>
        </div>
        <ChevronDown
          size={18}
          className={`mt-1 shrink-0 text-gov-gray-400 transition-transform ${open ? 'rotate-180' : ''}`}
          aria-hidden
        />
      </button>

      {open ? (
        <div className="space-y-3 border-t border-gov-blue-100/80 px-5 pb-5 pt-4 dark:border-dark-border">
          <div className="grid gap-3 lg:grid-cols-3">
            {LAYERS.map((layer) => (
              <article
                key={layer.title}
                className="rounded-2xl border border-white/80 bg-white/90 p-4 shadow-sm dark:border-dark-border dark:bg-dark-surface"
              >
                <div className="flex items-center gap-2">
                  <layer.icon size={16} className="text-gov-blue-600 dark:text-dark-cyan" aria-hidden />
                  <h3 className="text-sm font-black text-gov-gray-900 dark:text-dark-text">{layer.title}</h3>
                </div>
                <dl className="mt-3 space-y-2 text-xs text-gov-gray-600 dark:text-dark-muted">
                  <div>
                    <dt className="font-bold text-gov-gray-800 dark:text-dark-text">Dónde vive</dt>
                    <dd className="mt-0.5 font-mono text-[10px]">{layer.storage}</dd>
                  </div>
                  <div>
                    <dt className="font-bold text-gov-gray-800 dark:text-dark-text">Cómo se activa</dt>
                    <dd className="mt-0.5 leading-relaxed">{layer.activation}</dd>
                  </div>
                  <div>
                    <dt className="font-bold text-gov-gray-800 dark:text-dark-text">Ejemplo</dt>
                    <dd className="mt-0.5 font-mono text-[10px]">{layer.example}</dd>
                  </div>
                </dl>
                <p className="mt-2 text-[10px] leading-relaxed text-gov-gray-500 dark:text-dark-muted">
                  {layer.note}
                </p>
              </article>
            ))}
          </div>

          <p className="flex flex-wrap items-center gap-2 rounded-2xl border border-gov-blue-100 bg-white/70 px-4 py-3 text-xs text-gov-blue-900 dark:border-dark-border dark:bg-dark-bg dark:text-dark-cyan">
            <Layers size={14} aria-hidden />
            <span>
              Flujo típico: creas catálogo → implementas bridge Python → activas en{' '}
              <Link href="/templates" className="font-bold underline">
                Editor de agente → Herramientas
              </Link>
              . MCP es otro canal (servidor HTTP), no confundir con skills.
            </span>
          </p>
        </div>
      ) : null}
    </section>
  );
}
