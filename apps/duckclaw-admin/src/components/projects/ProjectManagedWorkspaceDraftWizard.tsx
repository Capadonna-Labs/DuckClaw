'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowLeft, CheckCircle2, Database, Sparkles } from 'lucide-react';
import { adminService } from '@/services/adminService';
import type { ManagedWorkspaceDraft } from '@/services/adminService';

type WizardStep = 1 | 2 | 3 | 4;

const steps: { id: WizardStep; label: string }[] = [
  { id: 1, label: 'Objetivo' },
  { id: 2, label: 'Preguntas' },
  { id: 3, label: 'Borrador revisable' },
  { id: 4, label: 'Confirmacion DB-first' },
];

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

export function ProjectManagedWorkspaceDraftWizard() {
  const router = useRouter();
  const [step, setStep] = useState<WizardStep>(1);
  const [prompt, setPrompt] = useState('');
  const [draft, setDraft] = useState<ManagedWorkspaceDraft | null>(null);
  const [questionAnswers, setQuestionAnswers] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const promptReady = prompt.trim().length >= 10;

  const goBackToProjects = () => {
    router.push('/projects');
  };

  const generateDraft = async () => {
    if (!promptReady) {
      setError('Describe el objetivo con al menos 10 caracteres para analizarlo.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const nextDraft = await adminService.createManagedWorkspaceDraft({ prompt: prompt.trim() });
      setDraft(nextDraft);
      setQuestionAnswers({});
      setStep(2);
    } catch (e) {
      setError(errorMessage(e, 'No se pudo generar el borrador'));
    } finally {
      setBusy(false);
    }
  };

  const confirmDraft = async () => {
    if (!draft) return;
    setBusy(true);
    setError(null);
    try {
      await adminService.confirmManagedWorkspaceDraft(draft);
      router.push('/projects');
    } catch (e) {
      setError(errorMessage(e, 'No se pudo confirmar el borrador'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="space-y-5">
      <div className="rounded-3xl border border-gov-blue-100 bg-white p-5 shadow-sm dark:border-dark-border dark:bg-dark-surface">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="inline-flex items-center gap-2 rounded-full bg-gov-blue-700 px-3 py-1 text-[10px] font-black uppercase tracking-[0.18em] text-white">
              <Sparkles size={12} /> Paso {step} de 4
            </p>
            <h2 className="mt-3 text-2xl font-black text-gov-gray-900 dark:text-dark-text">
              {steps.find((item) => item.id === step)?.label}
            </h2>
            <p className="mt-1 text-sm text-gov-gray-500 dark:text-dark-muted">
              Nada se guarda en DuckDB hasta la confirmacion final.
            </p>
          </div>
          <button
            type="button"
            onClick={goBackToProjects}
            className="inline-flex items-center gap-2 rounded-xl border border-gov-blue-100 px-4 py-2 text-sm font-bold text-gov-blue-800 hover:bg-gov-blue-50 dark:border-dark-border dark:text-dark-cyan dark:hover:bg-dark-bg"
          >
            <ArrowLeft size={16} /> Volver a proyectos
          </button>
        </div>

        <ol className="mt-5 grid gap-2 md:grid-cols-4">
          {steps.map((item) => {
            const active = item.id === step;
            const done = item.id < step;
            return (
              <li
                key={item.id}
                className={`rounded-2xl border px-3 py-2 text-xs font-black ${
                  active
                    ? 'border-gov-blue-600 bg-gov-blue-50 text-gov-blue-900 dark:border-dark-cyan dark:bg-dark-bg dark:text-dark-cyan'
                    : 'border-gov-blue-100 text-gov-gray-500 dark:border-dark-border dark:text-dark-muted'
                }`}
              >
                <span className="flex items-center gap-2">
                  {done ? <CheckCircle2 size={14} /> : <span>{item.id}</span>}
                  {item.label}
                </span>
              </li>
            );
          })}
        </ol>
      </div>

      {error && (
        <p
          role="alert"
          className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-bold text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300"
        >
          {error}
        </p>
      )}

      <div className="rounded-3xl border border-gov-blue-100 bg-white p-5 shadow-sm dark:border-dark-border dark:bg-dark-surface">
        {step === 1 && (
          <div className="space-y-4">
            <div>
              <h3 className="text-xl font-black text-gov-gray-900 dark:text-dark-text">
                Describe el objetivo del proyecto
              </h3>
              <p className="mt-1 text-sm text-gov-gray-500 dark:text-dark-muted">
                Incluye resultado esperado, datos disponibles y el tipo de ayuda que debe preparar el flujo administrado.
              </p>
            </div>
            <label
              htmlFor="project-objective"
              className="block text-sm font-black text-gov-gray-900 dark:text-dark-text"
            >
              Objetivo del proyecto
            </label>
            <textarea
              id="project-objective"
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              rows={8}
              placeholder="Quiero un proyecto para..."
              className="w-full rounded-2xl border border-gov-blue-100 bg-white px-4 py-3 text-sm text-gov-gray-900 outline-none focus:border-gov-blue-500 dark:border-dark-border dark:bg-dark-bg dark:text-dark-text"
            />
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-xs text-gov-gray-500 dark:text-dark-muted">
                Minimo 10 caracteres. El borrador solo vive en memoria del navegador hasta confirmar.
              </p>
              <button
                type="button"
                disabled={busy}
                onClick={() => void generateDraft()}
                className="rounded-xl bg-gov-blue-700 px-4 py-2 text-sm font-black text-white hover:bg-gov-blue-900 disabled:opacity-50"
              >
                {busy ? 'Analizando...' : 'Analizar borrador administrado'}
              </button>
            </div>
          </div>
        )}

        {step === 2 && draft && (
          <div className="space-y-4">
            <div>
              <h3 className="text-xl font-black text-gov-gray-900 dark:text-dark-text">Preguntas faltantes</h3>
              <p className="mt-1 text-sm text-gov-gray-500 dark:text-dark-muted">
                Revisa lo que falta antes de validar el borrador administrado.
              </p>
            </div>
            <div className="grid gap-2">
              {draft.questions.length > 0 ? (
                draft.questions.map((question, index) => {
                  const answerKey = `${index}:${question}`;
                  const answerId = `managed-draft-question-${index}`;
                  return (
                    <div
                      key={answerKey}
                      className="rounded-2xl bg-gov-gray-50 p-3 text-sm text-gov-gray-700 dark:bg-dark-bg dark:text-dark-text"
                    >
                      <label
                        htmlFor={answerId}
                        className="block font-bold text-gov-gray-900 dark:text-dark-text"
                      >
                        {question}
                      </label>
                      <textarea
                        id={answerId}
                        value={questionAnswers[answerKey] ?? ''}
                        onChange={(event) =>
                          setQuestionAnswers((current) => ({
                            ...current,
                            [answerKey]: event.target.value,
                          }))
                        }
                        rows={3}
                        placeholder="Respuesta opcional"
                        className="mt-2 w-full rounded-xl border border-gov-blue-100 bg-white px-3 py-2 text-sm text-gov-gray-900 outline-none focus:border-gov-blue-500 dark:border-dark-border dark:bg-dark-surface dark:text-dark-text"
                      />
                    </div>
                  );
                })
              ) : (
                <div className="rounded-2xl bg-gov-gray-50 p-3 text-sm text-gov-gray-700 dark:bg-dark-bg dark:text-dark-text">
                  No hay preguntas faltantes para este borrador.
                </div>
              )}
            </div>
            <p className="rounded-2xl border border-gov-blue-100 bg-gov-blue-50 p-3 text-xs text-gov-blue-900 dark:border-dark-border dark:bg-dark-bg dark:text-dark-cyan">
              Las respuestas ayudan a revisar localmente. Para incorporarlas al borrador, ajusta el objetivo y vuelve a
              regenerar.
            </p>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setStep(1)}
                className="rounded-xl border border-gov-blue-100 px-4 py-2 text-sm font-bold text-gov-blue-800 dark:border-dark-border dark:text-dark-cyan"
              >
                Ajustar objetivo
              </button>
              <button
                type="button"
                onClick={() => setStep(3)}
                className="rounded-xl border border-gov-blue-100 px-4 py-2 text-sm font-bold text-gov-blue-800 dark:border-dark-border dark:text-dark-cyan"
              >
                Continuar sin responder
              </button>
              <button
                type="button"
                onClick={() => setStep(3)}
                className="rounded-xl bg-gov-blue-700 px-4 py-2 text-sm font-black text-white hover:bg-gov-blue-900"
              >
                Continuar al borrador
              </button>
            </div>
          </div>
        )}

        {step === 3 && draft && (
          <div className="space-y-4">
            <div>
              <h3 className="text-xl font-black text-gov-gray-900 dark:text-dark-text">Borrador revisable</h3>
              <p className="mt-1 text-sm text-gov-gray-500 dark:text-dark-muted">
                Análisis del borrador administrado: confirma proyecto, workers, skills sugeridas y contexto compartido
                antes de escribir en DB.
              </p>
            </div>
            <div className="rounded-2xl border border-gov-cyan-200 bg-gov-cyan-50 p-4 dark:border-dark-border dark:bg-dark-bg">
              <p className="text-xs font-black uppercase tracking-wide text-gov-blue-700 dark:text-dark-cyan">
                Análisis del borrador administrado
              </p>
              <p className="mt-2 text-sm text-gov-blue-900 dark:text-dark-text">
                El borrador resume el objetivo, separa contexto operativo y propone workers antes de guardar datos.
              </p>
            </div>
            <div className="rounded-2xl border border-gov-blue-100 p-4 dark:border-dark-border">
              <p className="text-xs font-black uppercase tracking-wide text-gov-gray-500 dark:text-dark-muted">
                Proyecto
              </p>
              <h4 className="mt-1 text-lg font-black text-gov-gray-900 dark:text-dark-text">
                {draft.project.name}
              </h4>
              <p className="mt-1 text-sm text-gov-gray-500 dark:text-dark-muted">{draft.project.description}</p>
            </div>
            <div className="grid gap-3 lg:grid-cols-2">
              <div className="rounded-2xl bg-gov-gray-50 p-4 dark:bg-dark-bg">
                <p className="text-xs font-black uppercase tracking-wide text-gov-gray-500 dark:text-dark-muted">
                  Workers nuevos o reutilizados
                </p>
                <div className="mt-3 grid gap-2">
                  {draft.workers.map((worker) => (
                    <div key={worker.worker_id} className="rounded-xl bg-white p-3 text-sm dark:bg-dark-surface">
                      <strong className="text-gov-gray-900 dark:text-dark-text">{worker.display_name}</strong>
                      <p className="mt-1 font-mono text-xs text-gov-gray-500 dark:text-dark-muted">
                        {worker.worker_id}
                      </p>
                      <p className="mt-1 text-xs text-gov-gray-500 dark:text-dark-muted">{worker.role}</p>
                    </div>
                  ))}
                </div>
              </div>
              <div className="rounded-2xl bg-gov-gray-50 p-4 dark:bg-dark-bg">
                <p className="text-xs font-black uppercase tracking-wide text-gov-gray-500 dark:text-dark-muted">
                  Skills sugeridas
                </p>
                <div className="mt-3 grid gap-2">
                  {draft.suggested_skills.map((skill) => (
                    <div key={skill.name} className="rounded-xl bg-white p-3 text-sm dark:bg-dark-surface">
                      <strong className="text-gov-gray-900 dark:text-dark-text">{skill.name}</strong>
                      <span className="ml-2 rounded-full bg-gov-blue-50 px-2 py-0.5 text-[10px] font-black uppercase text-gov-blue-800 dark:bg-dark-bg dark:text-dark-cyan">
                        {skill.available ? 'Disponible' : 'Sugerida'}
                      </span>
                      <p className="mt-1 text-xs text-gov-gray-500 dark:text-dark-muted">{skill.reason}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
            <div className="rounded-2xl border border-gov-blue-100 p-4 dark:border-dark-border">
              <p className="text-xs font-black uppercase tracking-wide text-gov-gray-500 dark:text-dark-muted">
                Contexto compartido
              </p>
              <p className="mt-2 whitespace-pre-wrap text-sm text-gov-gray-700 dark:text-dark-text">
                {draft.shared_context}
              </p>
            </div>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setStep(2)}
                className="rounded-xl border border-gov-blue-100 px-4 py-2 text-sm font-bold text-gov-blue-800 dark:border-dark-border dark:text-dark-cyan"
              >
                Ver preguntas
              </button>
              <button
                type="button"
                onClick={() => setStep(4)}
                className="rounded-xl bg-gov-blue-700 px-4 py-2 text-sm font-black text-white hover:bg-gov-blue-900"
              >
                Revisar confirmacion
              </button>
            </div>
          </div>
        )}

        {step === 4 && draft && (
          <div className="space-y-4">
            <div>
              <h3 className="flex items-center gap-2 text-xl font-black text-gov-gray-900 dark:text-dark-text">
                <Database size={20} /> Confirmacion DB-first
              </h3>
              <p className="mt-1 text-sm text-gov-gray-500 dark:text-dark-muted">
                Esta es la unica accion que persiste el proyecto. Revisa exactamente que escribe.
              </p>
            </div>
            <ul className="space-y-2 text-sm text-gov-gray-700 dark:text-dark-text">
              <li className="rounded-2xl bg-gov-gray-50 p-3 dark:bg-dark-bg">
                Crear fila en <code>main.admin_projects</code>: {draft.project.name}
              </li>
              <li className="rounded-2xl bg-gov-gray-50 p-3 dark:bg-dark-bg">
                Crear o reutilizar {draft.workers.length} worker(s) del borrador.
              </li>
              <li className="rounded-2xl bg-gov-gray-50 p-3 dark:bg-dark-bg">
                Crear asignaciones en <code>main.admin_project_agents</code>.
              </li>
              <li className="rounded-2xl bg-gov-gray-50 p-3 dark:bg-dark-bg">
                Guardar contexto compartido en <code>main.admin_worker_contexts</code>.
              </li>
              <li className="rounded-2xl border border-amber-200 bg-amber-50 p-3 font-bold text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-200">
                NO guarda secretos, NO escribe templates legacy y NO borra workers existentes.
              </li>
            </ul>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setStep(3)}
                className="rounded-xl border border-gov-blue-100 px-4 py-2 text-sm font-bold text-gov-blue-800 dark:border-dark-border dark:text-dark-cyan"
              >
                Revisar borrador
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => void confirmDraft()}
                className="rounded-xl bg-gov-blue-700 px-4 py-2 text-sm font-black text-white hover:bg-gov-blue-900 disabled:opacity-50"
              >
                {busy ? 'Confirmando...' : 'Confirmar y crear en DuckDB'}
              </button>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
