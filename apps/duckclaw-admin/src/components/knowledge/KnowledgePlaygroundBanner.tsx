'use client';

import Link from 'next/link';
import { MessageSquareWarning } from 'lucide-react';
import type { KnowledgeSource } from '@/services/adminService';
import { summarizeKnowledgeSources } from '@/components/knowledge/knowledgeStatusUi';

type KnowledgePlaygroundBannerProps = {
  projectId: string;
  projectName?: string;
  workerId?: string;
  sources: KnowledgeSource[];
  loading: boolean;
};

export function KnowledgePlaygroundBanner({
  projectId,
  projectName,
  workerId,
  sources,
  loading,
}: KnowledgePlaygroundBannerProps) {
  if (!projectId || loading) return null;

  const { totalChunks, readyWithChunks, indexing, allReady } = summarizeKnowledgeSources(sources);
  const playgroundHref = `/playground?project=${encodeURIComponent(projectId)}${
    workerId ? `&worker=${encodeURIComponent(workerId)}` : ''
  }`;
  const label = projectName || 'este proyecto';

  if (sources.length === 0) {
    return (
      <section className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-100">
        <p className="font-bold">El agente no encontrará documentos hasta que subas algo aquí.</p>
        <p className="mt-1 text-amber-900/90 dark:text-amber-100/90">
          Después prueba en{' '}
          <Link href={playgroundHref} className="font-bold underline">
            Playground
          </Link>{' '}
          con el proyecto <strong>{label}</strong> seleccionado.
        </p>
      </section>
    );
  }

  if (indexing) {
    return (
      <section className="rounded-2xl border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-950 dark:border-sky-900 dark:bg-sky-950/30 dark:text-sky-100">
        <p className="font-bold">Indexando conocimiento…</p>
        <p className="mt-1">Espera un momento y pulsa Refrescar. Luego abre Playground con el proyecto activo.</p>
      </section>
    );
  }

  if (totalChunks === 0) {
    return (
      <section className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-100">
        <p className="flex items-center gap-2 font-bold">
          <MessageSquareWarning size={16} aria-hidden />
          Hay fuentes registradas pero sin fragmentos (chunks) para el chat.
        </p>
        <p className="mt-1">
          Vuelve a importar los archivos o revisa que el proyecto sea el correcto. Si el agente dice «0 registros»,
          no uses SQL: el conocimiento vive aquí, no en tablas del agente.
        </p>
        <Link href={playgroundHref} className="mt-2 inline-block font-bold text-amber-950 underline dark:text-amber-100">
          Abrir Playground con {label} →
        </Link>
      </section>
    );
  }

  if (allReady && readyWithChunks > 0) {
    return (
      <section className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-950 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-100">
        <p className="font-bold">
          Listo para el chat — {totalChunks} fragmento{totalChunks === 1 ? '' : 's'} indexados.
        </p>
        <p className="mt-1">
          Si el agente no responde con ese contenido, abre Playground con el mismo proyecto. Si sigue fallando, revisa{' '}
          <span className="font-semibold">Base de datos de esta sesión</span> en Playground (debe ser la misma base
          donde guardaste el RAG).
        </p>
        <Link
          href={playgroundHref}
          className="mt-2 inline-block rounded-xl bg-emerald-800 px-3 py-1.5 text-xs font-black text-white hover:bg-emerald-900"
        >
          Probar en Playground
        </Link>
      </section>
    );
  }

  return (
    <section className="rounded-2xl border border-gov-blue-100 bg-gov-blue-50 px-4 py-3 text-sm text-gov-gray-800 dark:border-dark-border dark:bg-dark-bg dark:text-dark-text">
      <p className="font-bold">Algunas fuentes aún no están listas.</p>
      <p className="mt-1">
        Revisa el estado de cada fuente abajo. Cuando veas <strong>Listo</strong>, prueba en Playground.
      </p>
      <Link href={playgroundHref} className="mt-2 inline-block font-bold text-gov-blue-800 underline dark:text-dark-cyan">
        Ir a Playground →
      </Link>
    </section>
  );
}
