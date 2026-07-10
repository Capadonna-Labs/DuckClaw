'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Bot, CheckCircle2, Database, Loader2, MessageCircle, Sparkles, X } from 'lucide-react';
import { adminService } from '@/services/adminService';
import type { UserAgentDraft } from '@/services/adminService';
import { clampInput } from '@/lib/validation';
import { knowledgeHref, playgroundHref, writeLastCreatedWorker } from '@/lib/onboardingFlow';

function slugifyId(raw: string): string {
  return raw
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 64);
}

type WizardStep = 1 | 2;
type InstructionTab = 'system_prompt' | 'soul';

const MIN_SYSTEM_PROMPT_LEN = 80;
const MIN_SOUL_LEN = 20;

const steps: { id: WizardStep; label: string }[] = [
  { id: 1, label: 'Comportamiento' },
  { id: 2, label: 'Revisar y crear' },
];

function normalizeAgentDraft(raw: UserAgentDraft): UserAgentDraft {
  return {
    ...raw,
    tool_profile: raw.tool_profile || 'general',
    browser_sandbox: raw.browser_sandbox ?? false,
    web_search: raw.web_search ?? false,
    questions: raw.questions ?? [],
  };
}

type CreateAgentDialogProps = {
  open: boolean;
  onClose: () => void;
  onCreated?: () => void;
};

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

export function CreateAgentDialog({ open, onClose, onCreated }: CreateAgentDialogProps) {
  const router = useRouter();
  const [step, setStep] = useState<WizardStep>(1);
  const [displayName, setDisplayName] = useState('');
  const [workerId, setWorkerId] = useState('');
  const [behaviorPrompt, setBehaviorPrompt] = useState('');
  const [draft, setDraft] = useState<UserAgentDraft | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [createdId, setCreatedId] = useState<string | null>(null);
  const [instructionTab, setInstructionTab] = useState<InstructionTab>('system_prompt');
  const dialogScrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    dialogScrollRef.current?.scrollTo({ top: 0, behavior: 'smooth' });
  }, [step]);

  if (!open) return null;

  const effectiveId = workerId.trim() || slugifyId(displayName);
  const promptReady = behaviorPrompt.trim().length >= 10;
  const systemPromptLen = draft?.system_prompt.trim().length ?? 0;
  const soulLen = draft?.soul.trim().length ?? 0;
  const instructionsReady =
    systemPromptLen >= MIN_SYSTEM_PROMPT_LEN && soulLen >= MIN_SOUL_LEN;

  const resetState = () => {
    setStep(1);
    setDisplayName('');
    setWorkerId('');
    setBehaviorPrompt('');
    setDraft(null);
    setError(null);
    setCreatedId(null);
    setInstructionTab('system_prompt');
  };

  const resetAndClose = () => {
    resetState();
    onClose();
  };

  const generateDraft = async () => {
    if (!promptReady) {
      setError('Describe el comportamiento con al menos 10 caracteres.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const nextDraft = await adminService.createUserAgentDraft({
        prompt: behaviorPrompt.trim(),
        display_name: displayName.trim(),
        worker_id: effectiveId,
      });
      setDraft(normalizeAgentDraft(nextDraft));
      setStep(2);
      setInstructionTab('system_prompt');
    } catch (e) {
      setError(errorMessage(e, 'No se pudo analizar el comportamiento'));
    } finally {
      setBusy(false);
    }
  };

  const confirmDraft = async () => {
    if (!draft || !instructionsReady) {
      setError(
        `Completa instrucciones (mín. ${MIN_SYSTEM_PROMPT_LEN} caracteres) y personalidad (mín. ${MIN_SOUL_LEN}).`
      );
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const result = await adminService.confirmUserAgentDraft(draft);
      const id = result.worker_id || draft.worker_id;
      writeLastCreatedWorker(id);
      onCreated?.();
      setCreatedId(id);
    } catch (e) {
      setError(errorMessage(e, 'No se pudo crear el agente'));
    } finally {
      setBusy(false);
    }
  };

  const updateDraft = (patch: Partial<UserAgentDraft>) => {
    setDraft((current) => (current ? { ...current, ...patch } : current));
  };

  if (createdId) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
        <div
          role="dialog"
          aria-modal
          className="w-full max-w-lg rounded-3xl border border-emerald-200 bg-white p-6 shadow-xl dark:border-emerald-900 dark:bg-dark-surface"
        >
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="flex items-center gap-2 text-lg font-black text-emerald-800 dark:text-emerald-300">
                <Sparkles size={20} />
                Agente listo
              </p>
              <p className="mt-1 text-sm text-gov-gray-600 dark:text-dark-muted">
                <strong className="font-mono">{createdId}</strong> incluye system prompt, soul, manifest y reglas
                en DuckDB listas para chatear.
              </p>
            </div>
            <button type="button" onClick={resetAndClose} className="rounded-lg p-1 hover:bg-gov-gray-100 dark:hover:bg-dark-bg">
              <X size={18} />
            </button>
          </div>
          <div className="mt-5 grid gap-2">
            <Link
              href={knowledgeHref(undefined, createdId)}
              onClick={resetAndClose}
              className="flex items-center gap-3 rounded-2xl border border-gov-blue-100 bg-gov-blue-50 px-4 py-3 text-sm font-bold text-gov-blue-900 hover:bg-gov-blue-100 dark:border-dark-border dark:bg-dark-bg dark:text-dark-cyan"
            >
              <Database size={18} />
              Conectar documentos (RAG)
            </Link>
            <Link
              href={`/templates/${encodeURIComponent(createdId)}?focus=system_prompt.md&created=1`}
              onClick={resetAndClose}
              className="flex items-center gap-3 rounded-2xl border px-4 py-3 text-sm font-bold hover:bg-gov-gray-50 dark:border-dark-border dark:hover:bg-dark-bg"
            >
              <Bot size={18} />
              Editar instrucciones
            </Link>
            <Link
              href={playgroundHref(undefined, createdId)}
              onClick={resetAndClose}
              className="flex items-center gap-3 rounded-2xl bg-gov-blue-700 px-4 py-3 text-sm font-bold text-white hover:bg-gov-blue-800"
            >
              <MessageCircle size={18} />
              Probar en Playground
            </Link>
          </div>
          <button
            type="button"
            onClick={() => {
              resetAndClose();
              router.push('/templates');
            }}
            className="mt-4 w-full text-center text-xs font-semibold text-gov-gray-500 hover:underline"
          >
            Volver al listado de agentes
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div
        ref={dialogScrollRef}
        role="dialog"
        aria-modal
        aria-labelledby="create-agent-title"
        className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-3xl border border-gov-gray-100 bg-white p-6 shadow-xl dark:border-dark-border dark:bg-dark-surface"
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <p id="create-agent-title" className="flex items-center gap-2 text-lg font-black dark:text-dark-text">
              <Bot size={20} className="text-gov-blue-700 dark:text-dark-cyan" />
              Nuevo agente
            </p>
            <p className="mt-1 text-sm text-gov-gray-500 dark:text-dark-muted">
              Describe el comportamiento; la IA genera system prompt y soul editables antes de guardar.
            </p>
          </div>
          <button type="button" onClick={resetAndClose} className="rounded-lg p-1 hover:bg-gov-gray-100 dark:hover:bg-dark-bg">
            <X size={18} />
          </button>
        </div>

        <ol className="mt-4 grid gap-2 sm:grid-cols-3">
          {steps.map((item) => {
            const active = item.id === step;
            const done = item.id < step;
            return (
              <li
                key={item.id}
                className={`rounded-xl border px-3 py-2 text-xs font-black ${
                  active
                    ? 'border-gov-blue-600 bg-gov-blue-50 text-gov-blue-900 dark:border-dark-cyan dark:bg-dark-bg dark:text-dark-cyan'
                    : 'border-gov-gray-100 text-gov-gray-500 dark:border-dark-border dark:text-dark-muted'
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

        {error && (
          <p role="alert" className="mt-4 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300">
            {error}
          </p>
        )}

        <div className="mt-5 space-y-4">
          {step === 1 && (
            <>
              <label className="block space-y-1">
                <span className="text-xs font-bold text-gov-gray-700 dark:text-dark-text">Nombre visible (opcional)</span>
                <input
                  value={displayName}
                  onChange={(e) => {
                    setDisplayName(clampInput(e.target.value, 128));
                    if (!workerId) setWorkerId(slugifyId(e.target.value));
                  }}
                  maxLength={128}
                  placeholder="Marco-DevOps"
                  className="w-full rounded-xl border px-3 py-2 text-sm dark:border-dark-border dark:bg-dark-bg"
                />
              </label>
              <label className="block space-y-1">
                <span className="text-xs font-bold text-gov-gray-700 dark:text-dark-text">ID técnico (opcional)</span>
                <input
                  value={workerId}
                  onChange={(e) => setWorkerId(slugifyId(e.target.value))}
                  placeholder="marco-devops"
                  className="w-full rounded-xl border px-3 py-2 font-mono text-sm dark:border-dark-border dark:bg-dark-bg"
                />
              </label>
              <label className="block space-y-1">
                <span className="text-xs font-bold text-gov-gray-700 dark:text-dark-text">
                  ¿Qué debe hacer este agente?
                </span>
                <textarea
                  value={behaviorPrompt}
                  onChange={(e) => setBehaviorPrompt(clampInput(e.target.value, 4000))}
                  rows={6}
                  placeholder="Ej: Agente DevOps que revisa logs PM2, diagnostica el gateway y propone fixes en sandbox..."
                  className="w-full rounded-xl border px-3 py-2 text-sm dark:border-dark-border dark:bg-dark-bg"
                />
                <p className="text-xs text-gov-gray-500 dark:text-dark-muted">
                  Mínimo 10 caracteres ({behaviorPrompt.trim().length}/4000). Nada se guarda hasta confirmar.
                </p>
              </label>
            </>
          )}

          {step === 2 && draft && (
            <>
              {draft.questions.length > 0 && (
                <div className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-200">
                  <p className="text-xs font-bold">Opcional — la IA sugiere aclarar:</p>
                  <p className="mt-1">{draft.questions[0]}</p>
                </div>
              )}
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="block space-y-1">
                  <span className="text-xs font-bold">Nombre visible</span>
                  <input
                    value={draft.display_name}
                    onChange={(e) => updateDraft({ display_name: clampInput(e.target.value, 128) })}
                    className="w-full rounded-xl border px-3 py-2 text-sm dark:border-dark-border dark:bg-dark-bg"
                  />
                </label>
                <label className="block space-y-1">
                  <span className="text-xs font-bold">ID técnico</span>
                  <input
                    value={draft.worker_id}
                    onChange={(e) => updateDraft({ worker_id: slugifyId(e.target.value) })}
                    className="w-full rounded-xl border px-3 py-2 font-mono text-sm dark:border-dark-border dark:bg-dark-bg"
                  />
                </label>
              </div>
              <label className="block space-y-1">
                <span className="text-xs font-bold">Descripción</span>
                <textarea
                  value={draft.description}
                  onChange={(e) => updateDraft({ description: clampInput(e.target.value, 2048) })}
                  rows={4}
                  className="w-full rounded-xl border px-3 py-2 text-sm dark:border-dark-border dark:bg-dark-bg"
                />
                <p className="text-xs text-gov-gray-500 dark:text-dark-muted">
                  {draft.description.length}/2048 caracteres
                </p>
              </label>
              <div className="rounded-xl border p-3 dark:border-dark-border">
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => setInstructionTab('system_prompt')}
                    className={`rounded-lg px-3 py-1.5 text-xs font-bold ${
                      instructionTab === 'system_prompt'
                        ? 'bg-gov-blue-700 text-white'
                        : 'bg-gov-gray-100 text-gov-gray-700 dark:bg-dark-bg dark:text-dark-muted'
                    }`}
                  >
                    System prompt ({systemPromptLen})
                  </button>
                  <button
                    type="button"
                    onClick={() => setInstructionTab('soul')}
                    className={`rounded-lg px-3 py-1.5 text-xs font-bold ${
                      instructionTab === 'soul'
                        ? 'bg-gov-blue-700 text-white'
                        : 'bg-gov-gray-100 text-gov-gray-700 dark:bg-dark-bg dark:text-dark-muted'
                    }`}
                  >
                    Soul ({soulLen})
                  </button>
                </div>
                {instructionTab === 'system_prompt' ? (
                  <label className="mt-3 block space-y-1">
                    <span className="text-xs font-bold text-gov-gray-700 dark:text-dark-text">
                      Qué hace el agente (rol, herramientas, reglas)
                    </span>
                    <textarea
                      value={draft.system_prompt}
                      onChange={(e) => updateDraft({ system_prompt: clampInput(e.target.value, 12000) })}
                      rows={10}
                      className="w-full rounded-xl border px-3 py-2 font-mono text-xs dark:border-dark-border dark:bg-dark-bg"
                    />
                    <p
                      className={`text-xs ${
                        systemPromptLen >= MIN_SYSTEM_PROMPT_LEN
                          ? 'text-green-700 dark:text-green-300'
                          : 'text-amber-700 dark:text-amber-300'
                      }`}
                    >
                      Mínimo {MIN_SYSTEM_PROMPT_LEN} caracteres ({systemPromptLen}/{MIN_SYSTEM_PROMPT_LEN}).
                    </p>
                  </label>
                ) : (
                  <label className="mt-3 block space-y-1">
                    <span className="text-xs font-bold text-gov-gray-700 dark:text-dark-text">
                      Cómo habla y se comporta (tono, estilo, valores)
                    </span>
                    <textarea
                      value={draft.soul}
                      onChange={(e) => updateDraft({ soul: clampInput(e.target.value, 4000) })}
                      rows={8}
                      className="w-full rounded-xl border px-3 py-2 font-mono text-xs dark:border-dark-border dark:bg-dark-bg"
                    />
                    <p
                      className={`text-xs ${
                        soulLen >= MIN_SOUL_LEN
                          ? 'text-green-700 dark:text-green-300'
                          : 'text-amber-700 dark:text-amber-300'
                      }`}
                    >
                      Mínimo {MIN_SOUL_LEN} caracteres ({soulLen}/{MIN_SOUL_LEN}).
                    </p>
                  </label>
                )}
              </div>
              <section className="rounded-xl border border-gov-blue-100 bg-gov-blue-50/50 p-4 dark:border-dark-border dark:bg-dark-bg/60">
                <p className="text-xs font-black uppercase tracking-wide text-gov-blue-800 dark:text-dark-cyan">
                  Capacidades incluidas
                </p>
                <p className="mt-1 text-sm text-gov-gray-700 dark:text-dark-muted">
                  Perfil <strong>Asistente completo</strong>: consulta datos, documentos, informes y scripts en
                  sandbox. Ajusta herramientas concretas después en el editor del agente.
                </p>
              </section>
              {draft.suggested_skills.length > 0 && (
                <div className="rounded-xl border p-3 dark:border-dark-border">
                  <p className="text-xs font-black uppercase tracking-wide text-gov-gray-500">Skills sugeridas</p>
                  <div className="mt-2 grid gap-2">
                    {draft.suggested_skills.map((skill) => (
                      <div key={skill.name} className="rounded-lg bg-gov-gray-50 p-2 text-sm dark:bg-dark-bg">
                        <strong>{skill.name}</strong>
                        <span className="ml-2 text-[10px] font-black uppercase text-gov-blue-700">
                          {skill.available ? 'Disponible' : 'Sugerida'}
                        </span>
                        <p className="mt-1 text-xs text-gov-gray-500">{skill.reason}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        <div className="mt-6 flex flex-wrap justify-end gap-2">
          <button
            type="button"
            onClick={resetAndClose}
            className="rounded-xl border px-4 py-2 text-sm font-semibold dark:border-dark-border"
          >
            Cancelar
          </button>
          {step === 1 && (
            <button
              type="button"
              disabled={busy}
              onClick={() => void generateDraft()}
              className="inline-flex items-center gap-2 rounded-xl bg-gov-blue-700 px-4 py-2 text-sm font-bold text-white disabled:opacity-60"
            >
              {busy && <Loader2 size={16} className="animate-spin" />}
              {busy ? 'Analizando…' : 'Analizar con LLM'}
            </button>
          )}
          {step === 2 && (
            <>
              <button
                type="button"
                onClick={() => setStep(1)}
                className="rounded-xl border px-4 py-2 text-sm font-semibold dark:border-dark-border"
              >
                Cambiar descripción
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => void generateDraft()}
                className="rounded-xl border px-4 py-2 text-sm font-semibold dark:border-dark-border"
              >
                Regenerar con IA
              </button>
              <button
                type="button"
                disabled={busy || !instructionsReady}
                onClick={() => void confirmDraft()}
                className="inline-flex items-center gap-2 rounded-xl bg-gov-blue-700 px-4 py-2 text-sm font-bold text-white disabled:opacity-60"
              >
                {busy && <Loader2 size={16} className="animate-spin" />}
                Crear agente
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
