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
  if (loading) return null;

  const isFrameworkScope = !projectId;
  const { totalChunks, readyWithChunks, indexing, allReady } = summarizeKnowledgeSources(sources);
  const playgroundHref = projectId
    ? `/playground?project=${encodeURIComponent(projectId)}${
        workerId ? `&worker=${encodeURIComponent(workerId)}` : ''
      }`
    : '/playground';
  const label = isFrameworkScope
    ? 'framework (todos los agentes)'
    : projectName || 'este proyecto';

  if (sources.length === 0) {
    return (
      <section className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-100">
        <p className="font-bold">
          {isFrameworkScope
            ? 'Aún no hay conocimiento global del framework.'
            : 'El agente no encontrará documentos hasta que subas algo aquí.'}
        </p>
        <p className="mt-1 text-amber-900/90 dark:text-amber-100/90">
          {isFrameworkScope ? (
            <>
              Importa archivos con alcance <strong>Framework</strong>. Ese RAG aplica a todos los chats del tenant.
            </>
          ) : (
            <>
              Después prueba en{' '}
              <Link href={playgroundHref} className="font-bold underline">
                Playground
              </Link>{' '}
              con el proyecto <strong>{label}</strong> seleccionado.
            </>
          )}
        </p>
      </section>
    );
  }

  if (indexing) {
    return (
      <section className="rounded-2xl border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-950 dark:border-sky-900 dark:bg-sky-950/30 dark:text-sky-100">
        <p className="font-bold">Indexando conocimiento…</p>
        <p className="mt-1">
          Espera un momento y pulsa Refrescar.
          {isFrameworkScope
            ? ' El contenido quedará disponible en todos los agentes.'
            : ' Luego abre Playground con el proyecto activo.'}
        </p>
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
          Vuelve a importar los archivos o revisa el alcance. Si el agente dice «0 registros», no uses SQL: el
          conocimiento vive aquí, no en tablas del agente.
        </p>
        {!isFrameworkScope && (
          <Link href={playgroundHref} className="mt-2 inline-block font-bold text-amber-950 underline dark:text-amber-100">
            Abrir Playground con {label} →
          </Link>
        )}
      </section>
    );
  }

  if (allReady && readyWithChunks > 0) {
    return (
      <section className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-950 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-100">
        <p className="font-bold">
          Listo para el chat — {totalChunks} fragmento{totalChunks === 1 ? '' : 's'} indexados
          {isFrameworkScope ? ' (framework)' : ''}.
        </p>
        <p className="mt-1">
          {isFrameworkScope ? (
            <>
              Este conocimiento se inyecta en cualquier chat del tenant (junto con el RAG de proyecto si existe).
            </>
          ) : (
            <>
              Si el agente no responde con ese contenido, abre Playground con el mismo proyecto. Si sigue fallando,
              revisa <span className="font-semibold">Base de datos de esta sesión</span> en Playground.
            </>
          )}
        </p>
        <Link
          href={playgroundHref}
          className="mt-2 inline-block rounded-xl bg-emerald-800 px-3 py-1.5 text-xs font-black text-white hover:bg-emerald-900"
        >
          {isFrameworkScope ? 'Abrir Playground' : 'Probar en Playground'}
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
