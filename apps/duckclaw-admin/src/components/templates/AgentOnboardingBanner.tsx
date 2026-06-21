'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { Database, MessageCircle, Sparkles, X } from 'lucide-react';
import { knowledgeHref, playgroundHref, readLastProjectId } from '@/lib/onboardingFlow';

type AgentOnboardingBannerProps = {
  workerId: string;
  onDismiss?: () => void;
};

export function AgentOnboardingBanner({ workerId, onDismiss }: AgentOnboardingBannerProps) {
  const [projectId, setProjectId] = useState('');

  useEffect(() => {
    setProjectId(readLastProjectId());
  }, []);

  return (
    <section className="rounded-2xl border border-emerald-200 bg-emerald-50/80 p-4 dark:border-emerald-900/50 dark:bg-emerald-950/20">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="flex items-center gap-2 text-sm font-black text-emerald-900 dark:text-emerald-200">
            <Sparkles size={16} />
            Agente creado — siguiente paso
          </p>
          <p className="mt-1 text-xs text-emerald-900/80 dark:text-emerald-100/80">
            Conecta documentos para RAG o prueba el agente en Playground. Exporta informes a Word/PDF desde el chat.
          </p>
        </div>
        {onDismiss && (
          <button
            type="button"
            onClick={onDismiss}
            className="rounded-lg p-1 text-emerald-800 hover:bg-emerald-100 dark:text-emerald-200 dark:hover:bg-emerald-950/40"
            aria-label="Cerrar"
          >
            <X size={16} />
          </button>
        )}
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <Link
          href={knowledgeHref(projectId, workerId)}
          className="inline-flex items-center gap-2 rounded-xl bg-white px-3 py-2 text-xs font-bold text-gov-blue-800 shadow-sm hover:bg-gov-blue-50 dark:bg-dark-surface dark:text-dark-cyan dark:hover:bg-dark-bg"
        >
          <Database size={14} />
          Conectar RAG
        </Link>
        <Link
          href={playgroundHref(projectId, workerId)}
          className="inline-flex items-center gap-2 rounded-xl bg-gov-blue-700 px-3 py-2 text-xs font-bold text-white hover:bg-gov-blue-800"
        >
          <MessageCircle size={14} />
          Playground
        </Link>
      </div>
    </section>
  );
}
