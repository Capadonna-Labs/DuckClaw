'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { Bot, CheckCircle2, Circle, Database, MessageCircle, Server } from 'lucide-react';
import { adminService } from '@/services/adminService';
import { playgroundHref, readLastCreatedWorker, readLastProjectId } from '@/lib/onboardingFlow';
import { friendlyGatewayError } from '@/lib/adminErrors';

type StepState = 'pending' | 'ok' | 'warn';

type ChecklistStep = {
  id: string;
  title: string;
  detail: string;
  state: StepState;
  href: string;
  cta: string;
  optional?: boolean;
};

export function HomeChecklist() {
  const [steps, setSteps] = useState<ChecklistStep[]>([]);
  const [loading, setLoading] = useState(true);
  const [stackError, setStackError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setStackError(null);

      let stackOk = false;
      let stackDetail = 'Comprobando gateway y Redis…';
      try {
        const health = await adminService.health();
        stackOk = health.status === 'ok' && health.redis;
        stackDetail = stackOk
          ? `Gateway OK · Redis ${health.redis ? 'conectado' : 'pendiente'}`
          : `Gateway: ${health.status} · Redis: ${health.redis ? 'sí' : 'no'}`;
      } catch (e) {
        stackDetail = friendlyGatewayError(e instanceof Error ? e.message : 'Sin conexión');
        setStackError(stackDetail);
      }

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

      const workerId = readLastCreatedWorker();
      const projectId = readLastProjectId();
      const chatHref = playgroundHref(projectId, workerId);

      if (cancelled) return;

      setSteps([
        {
          id: 'stack',
          title: 'Stack local',
          detail: stackDetail,
          state: stackOk ? 'ok' : 'warn',
          href: '/overview',
          cta: 'Ver estado',
        },
        {
          id: 'agent',
          title: 'Agente listo',
          detail: agentDetail,
          state: agentOk ? 'ok' : 'pending',
          href: '/templates',
          cta: agentOk ? 'Ver agentes' : 'Crear agente',
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
        {
          id: 'chat',
          title: 'Probar en chat',
          detail: agentOk
            ? 'Abre Playground con tu agente y envía un mensaje.'
            : 'Necesitas un agente antes de chatear.',
          state: agentOk ? 'pending' : 'pending',
          href: chatHref,
          cta: 'Ir al chat',
        },
      ]);
      setLoading(false);
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  const readyToChat = steps.some((s) => s.id === 'agent' && s.state === 'ok');

  return (
    <section className="rounded-3xl border border-gov-blue-100 bg-gradient-to-br from-gov-blue-50 to-white p-5 dark:border-dark-border dark:from-dark-bg dark:to-dark-surface">
      <h2 className="text-lg font-black text-gov-gray-900 dark:text-dark-text">Tu camino</h2>
      <p className="mt-1 text-sm text-gov-gray-500 dark:text-dark-muted">
        Un solo hilo: stack → agente → (opcional) conocimiento → chat. Lo demás está en{' '}
        <strong className="font-bold">Más</strong> del menú lateral.
      </p>

      {stackError && (
        <p className="mt-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-100">
          {stackError}
        </p>
      )}

      <ol className="mt-4 space-y-3">
        {loading ? (
          <li className="text-sm text-gov-gray-500 dark:text-dark-muted">Cargando checklist…</li>
        ) : (
          steps.map((step, index) => (
            <li
              key={step.id}
              className="flex flex-col gap-3 rounded-2xl border border-white/80 bg-white/90 p-4 shadow-sm dark:border-dark-border dark:bg-dark-surface sm:flex-row sm:items-center sm:justify-between"
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
                  step.id === 'chat' && readyToChat
                    ? 'bg-gov-blue-700 text-white hover:bg-gov-blue-800'
                    : 'border border-gov-blue-200 text-gov-blue-800 hover:bg-gov-blue-50 dark:border-dark-border dark:text-dark-cyan'
                }`}
              >
                {step.cta}
              </Link>
            </li>
          ))
        )}
      </ol>
    </section>
  );
}

function StepIcon({ step, index }: { step: ChecklistStep; index: number }) {
  const Icon =
    step.id === 'stack'
      ? Server
      : step.id === 'agent'
        ? Bot
        : step.id === 'knowledge'
          ? Database
          : MessageCircle;
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
