'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { Bot, CheckCircle2, Circle, Database } from 'lucide-react';
import { adminService } from '@/services/adminService';

type StepState = 'pending' | 'ok';

type ChecklistStep = {
  id: 'agent' | 'knowledge';
  title: string;
  detail: string;
  state: StepState;
  href: string;
  cta: string;
  optional?: boolean;
};

function isPrimaryCta(step: ChecklistStep, steps: ChecklistStep[]): boolean {
  if (step.state === 'ok' || step.optional) return false;
  const firstPending = steps.find((s) => s.state !== 'ok' && !s.optional);
  return firstPending?.id === step.id;
}

export function HomeChecklist() {
  const [steps, setSteps] = useState<ChecklistStep[] | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      let agentOk = false;
      let agentDetail = 'Crea al menos un agente con instrucciones.';
      try {
        const templates = await adminService.listTemplates();
        const active = templates.filter((t) => t.active !== false);
        agentOk = active.length > 0;
        agentDetail = agentOk
          ? `${active.length} agente(s) en el catálogo`
          : 'Aún no hay agentes activos.';
      } catch {
        agentDetail = 'No se pudo leer el catálogo de agentes.';
      }

      if (cancelled) return;

      if (agentOk) {
        setSteps(null);
        return;
      }

      let knowledgeOk = false;
      let knowledgeDetail = 'Opcional: documentos para todo el framework.';
      try {
        const sources = await adminService.listKnowledgeSources({});
        knowledgeOk = sources.length > 0;
        knowledgeDetail = knowledgeOk
          ? `${sources.length} fuente(s) de conocimiento`
          : 'Sin fuentes aún (puedes omitir y chatear igual).';
      } catch {
        knowledgeDetail = 'No se pudo comprobar el gestor RAG.';
      }

      if (cancelled) return;

      setSteps([
        {
          id: 'agent',
          title: 'Crear un agente',
          detail: agentDetail,
          state: 'pending',
          href: '/templates',
          cta: 'Crear agente',
        },
        {
          id: 'knowledge',
          title: 'Conocimiento',
          detail: knowledgeDetail,
          state: knowledgeOk ? 'ok' : 'pending',
          href: '/knowledge',
          cta: knowledgeOk ? 'Gestionar' : 'Importar (opcional)',
          optional: true,
        },
      ]);
    }

    void load();

    return () => {
      cancelled = true;
    };
  }, []);

  if (!steps) {
    return null;
  }

  return (
    <section className="rounded-3xl border border-gov-gray-100 bg-white p-5 shadow-sm dark:border-dark-border dark:bg-dark-surface">
      <h2 className="text-lg font-black text-gov-gray-900 dark:text-dark-text">Primeros pasos</h2>
      <p className="mt-1 text-sm text-gov-gray-500 dark:text-dark-muted">
        Crea un agente para empezar. El chat está en el menú lateral.
      </p>

      <ol className="mt-4 space-y-3">
        {steps.map((step, index) => (
          <li
            key={step.id}
            className="flex flex-col gap-3 rounded-2xl border border-gov-gray-100 bg-gov-gray-50/50 p-4 dark:border-dark-border dark:bg-dark-bg sm:flex-row sm:items-center sm:justify-between"
          >
            <div className="flex items-start gap-3">
              <StepIcon step={step} index={index} />
              <div>
                <p className="font-black text-gov-gray-900 dark:text-dark-text">
                  {step.title}
                  {step.optional && (
                    <span className="ml-2 text-[10px] font-black uppercase tracking-wider text-gov-gray-400">
                      opcional
                    </span>
                  )}
                </p>
                <p className="mt-0.5 text-xs text-gov-gray-500 dark:text-dark-muted">{step.detail}</p>
              </div>
            </div>
            <Link
              href={step.href}
              className={`shrink-0 rounded-xl px-4 py-2 text-center text-sm font-bold ${
                isPrimaryCta(step, steps)
                  ? 'bg-gov-blue-700 text-white hover:bg-gov-blue-800'
                  : 'border border-gov-blue-200 text-gov-blue-800 hover:bg-gov-blue-50 dark:border-dark-border dark:text-dark-cyan'
              }`}
            >
              {step.cta}
            </Link>
          </li>
        ))}
      </ol>
    </section>
  );
}

function StepIcon({ step, index }: { step: ChecklistStep; index: number }) {
  const Icon = step.id === 'agent' ? Bot : Database;
  const StatusIcon = step.state === 'ok' ? CheckCircle2 : Circle;
  return (
    <div className="relative shrink-0">
      <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gov-blue-100 text-gov-blue-800 dark:bg-dark-bg dark:text-dark-cyan">
        <Icon size={18} />
      </div>
      <StatusIcon
        size={14}
        className={`absolute -bottom-1 -right-1 rounded-full bg-white dark:bg-dark-surface ${
          step.state === 'ok' ? 'text-emerald-600' : 'text-gov-gray-300'
        }`}
        aria-hidden
      />
      <span className="sr-only">
        Paso {index + 1}: {step.state === 'ok' ? 'completado' : 'pendiente'}
      </span>
    </div>
  );
}
