'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Bot, CheckCircle2, Database, Loader2, MessageCircle, Sparkles, X } from 'lucide-react';
import { adminService } from '@/services/adminService';
import type { UserAgentDraft } from '@/services/adminService';
import { useSkillsCatalog } from '@/components/skills/useSkillsCatalog';
import { WorkerCompositionPanel } from '@/components/templates/WorkerCompositionPanel';
import { WorkerMcpGrantsPicker } from '@/components/templates/WorkerMcpGrantsPicker';
import { WorkerRoleTemplatePicker } from '@/components/templates/WorkerRoleTemplatePicker';
import type { DraftComposition } from '@/lib/draftManifestYaml';
import {
  applyRoleTemplateToDraft,
  DEFAULT_TOOL_PROFILE,
  WORKER_ROLE_TEMPLATES,
  type WorkerRoleTemplateId,
} from '@/lib/workerRoleTemplates';
import { clampInput } from '@/lib/validation';
import { pollWriteTask } from '@/lib/pollWriteTask';
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

const INPUT_CLASS =
  'w-full rounded-lg border border-gov-gray-200 px-3 py-2 text-sm dark:border-dark-border dark:bg-dark-bg';

function normalizeAgentDraft(raw: UserAgentDraft): UserAgentDraft {
  return {
    ...raw,
    tool_profile: DEFAULT_TOOL_PROFILE,
    skills: raw.skills ?? [],
    browser_sandbox: raw.browser_sandbox ?? false,
    web_search: raw.web_search ?? false,
    questions: raw.questions ?? [],
  };
}

function mergeSuggestedSkills(draft: UserAgentDraft): UserAgentDraft {
  const merged = new Set(draft.skills.map((skill) => skill.trim()).filter(Boolean));
  for (const skill of draft.suggested_skills) {
    if (skill.available && skill.name.trim()) {
      merged.add(skill.name.trim());
    }
  }
  return { ...draft, skills: Array.from(merged) };
}

type CreateAgentDialogProps = {
  open: boolean;
  onClose: () => void;
  onCreated?: () => void;
};

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function DialogShell({
  children,
  scrollRef,
  labelledBy,
}: {
  children: React.ReactNode;
  scrollRef?: React.RefObject<HTMLDivElement>;
  labelledBy?: string;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div
        ref={scrollRef}
        role="dialog"
        aria-modal
        aria-labelledby={labelledBy}
        className="flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-lg border border-gov-gray-200 bg-white shadow-lg dark:border-dark-border dark:bg-dark-surface"
      >
        {children}
      </div>
    </div>
  );
}

export function CreateAgentDialog({ open, onClose, onCreated }: CreateAgentDialogProps) {
  const router = useRouter();
  const { globalSkills, localSkills } = useSkillsCatalog();
  const [step, setStep] = useState<WizardStep>(1);
  const [displayName, setDisplayName] = useState('');
  const [workerId, setWorkerId] = useState('');
  const [behaviorPrompt, setBehaviorPrompt] = useState('');
  const [draft, setDraft] = useState<UserAgentDraft | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [createdId, setCreatedId] = useState<string | null>(null);
  const [instructionTab, setInstructionTab] = useState<InstructionTab>('system_prompt');
  const [pendingMcpConnectorIds, setPendingMcpConnectorIds] = useState<string[]>([]);
  const [mcpGrantSummary, setMcpGrantSummary] = useState<string | null>(null);
  const [selectedRoleId, setSelectedRoleId] = useState<WorkerRoleTemplateId>('general');
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
    setPendingMcpConnectorIds([]);
    setMcpGrantSummary(null);
    setSelectedRoleId('general');
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
      setDraft(
        applyRoleTemplateToDraft(
          mergeSuggestedSkills(normalizeAgentDraft(nextDraft)),
          selectedRoleId
        )
      );
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
      const polled = await pollWriteTask(result.task_id);
      if (polled.state === 'failed') {
        throw new Error(polled.detail || 'El agente no se guardó en DuckDB');
      }
      const id = result.worker_id || draft.worker_id;

      if (pendingMcpConnectorIds.length > 0) {
        let granted = 0;
        const grantFailures: string[] = [];
        for (const connectorId of pendingMcpConnectorIds) {
          try {
            const grantResult = await adminService.grantMcpConnector(connectorId, id);
            const grantPoll = await pollWriteTask(grantResult.task_id);
            if (grantPoll.state === 'failed') {
              grantFailures.push(`${connectorId}: ${grantPoll.detail || 'grant falló'}`);
            } else {
              granted += 1;
            }
          } catch (grantError) {
            grantFailures.push(
              `${connectorId}: ${grantError instanceof Error ? grantError.message : 'grant falló'}`
            );
          }
        }
        if (grantFailures.length > 0) {
          setMcpGrantSummary(
            `Agente creado. MCP: ${granted} autorizado(s), ${grantFailures.length} fallo(s).`
          );
        } else {
          setMcpGrantSummary(`${granted} conector(es) MCP autorizado(s).`);
        }
      }

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
      <DialogShell>
        <div className="border-b border-gov-gray-200 px-5 py-4 dark:border-dark-border">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="flex items-center gap-2 text-lg font-semibold text-emerald-800 dark:text-emerald-300">
                <Sparkles size={18} />
                Agente listo
              </p>
              <p className="mt-1 text-sm text-gov-gray-600 dark:text-dark-muted">
                <span className="font-mono font-semibold">{createdId}</span> incluye system prompt, soul, manifest y
                reglas en DuckDB.
              </p>
              {mcpGrantSummary ? (
                <p className="mt-2 text-xs text-emerald-700 dark:text-emerald-300">{mcpGrantSummary}</p>
              ) : null}
            </div>
            <button
              type="button"
              onClick={resetAndClose}
              className="rounded-lg p-1 hover:bg-gov-gray-100 dark:hover:bg-dark-bg"
            >
              <X size={18} />
            </button>
          </div>
        </div>
        <div className="space-y-2 px-5 py-4">
          <Link
            href={knowledgeHref(undefined, createdId)}
            onClick={resetAndClose}
            className="flex items-center gap-3 rounded-lg border border-gov-gray-200 px-4 py-3 text-sm font-semibold hover:bg-gov-gray-50 dark:border-dark-border dark:hover:bg-dark-bg"
          >
            <Database size={18} className="text-gov-blue-700 dark:text-dark-cyan" />
            Conectar documentos (RAG)
          </Link>
          <Link
            href={`/templates/${encodeURIComponent(createdId)}?focus=system_prompt.md&created=1`}
            onClick={resetAndClose}
            className="flex items-center gap-3 rounded-lg border border-gov-gray-200 px-4 py-3 text-sm font-semibold hover:bg-gov-gray-50 dark:border-dark-border dark:hover:bg-dark-bg"
          >
            <Bot size={18} />
            Editar instrucciones
          </Link>
          <Link
            href={playgroundHref(undefined, createdId)}
            onClick={resetAndClose}
            className="flex items-center gap-3 rounded-lg bg-gov-blue-700 px-4 py-3 text-sm font-semibold text-white hover:bg-gov-blue-800"
          >
            <MessageCircle size={18} />
            Probar en Playground
          </Link>
          <button
            type="button"
            onClick={() => {
              resetAndClose();
              router.push('/templates');
            }}
            className="w-full pt-2 text-center text-xs font-medium text-gov-gray-500 hover:underline"
          >
            Volver al listado de agentes
          </button>
        </div>
      </DialogShell>
    );
  }

  return (
    <DialogShell scrollRef={dialogScrollRef} labelledBy="create-agent-title">
      <div className="border-b border-gov-gray-200 px-5 py-4 dark:border-dark-border">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p id="create-agent-title" className="flex items-center gap-2 text-lg font-semibold dark:text-dark-text">
              <Bot size={18} className="text-gov-blue-700 dark:text-dark-cyan" />
              Nuevo agente
            </p>
            <p className="mt-1 text-sm text-gov-gray-500 dark:text-dark-muted">
              Describe el comportamiento; la IA genera system prompt y soul editables antes de guardar.
            </p>
          </div>
          <button
            type="button"
            onClick={resetAndClose}
            className="rounded-lg p-1 hover:bg-gov-gray-100 dark:hover:bg-dark-bg"
          >
            <X size={18} />
          </button>
        </div>
        <nav className="mt-4 flex border-b border-gov-gray-100 dark:border-dark-border" aria-label="Pasos">
          {steps.map((item) => {
            const active = item.id === step;
            const done = item.id < step;
            return (
              <div
                key={item.id}
                className={`flex items-center gap-2 border-b-2 px-3 py-2 text-xs font-semibold ${
                  active
                    ? 'border-gov-blue-700 text-gov-blue-800 dark:border-dark-cyan dark:text-dark-cyan'
                    : done
                      ? 'border-transparent text-emerald-700 dark:text-emerald-300'
                      : 'border-transparent text-gov-gray-400 dark:text-dark-muted'
                }`}
              >
                {done ? <CheckCircle2 size={14} /> : <span>{item.id}.</span>}
                {item.label}
              </div>
            );
          })}
        </nav>
      </div>

      <div className="flex-1 overflow-y-auto px-5 py-4">
        {error ? (
          <p
            role="alert"
            className="mb-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300"
          >
            {error}
          </p>
        ) : null}

        <div className="space-y-4">
          {step === 1 && (
            <>
              <WorkerRoleTemplatePicker
                selectedId={selectedRoleId}
                disabled={busy}
                onSelect={(role) => {
                  setSelectedRoleId(role.id);
                  const templatePrompt = role.promptTemplate.trim();
                  const current = behaviorPrompt.trim();
                  const matchesOtherTemplate = WORKER_ROLE_TEMPLATES.some(
                    (item) => item.id !== role.id && item.promptTemplate.trim() === current
                  );
                  if (!current || matchesOtherTemplate) {
                    setBehaviorPrompt(templatePrompt);
                  }
                }}
              />
              <label className="block space-y-1">
                <span className="text-xs font-medium text-gov-gray-700 dark:text-dark-text">
                  Nombre visible (opcional)
                </span>
                <input
                  value={displayName}
                  onChange={(e) => {
                    setDisplayName(clampInput(e.target.value, 128));
                    if (!workerId) setWorkerId(slugifyId(e.target.value));
                  }}
                  maxLength={128}
                  placeholder="Marco-DevOps"
                  className={INPUT_CLASS}
                />
              </label>
              <label className="block space-y-1">
                <span className="text-xs font-medium text-gov-gray-700 dark:text-dark-text">ID técnico (opcional)</span>
                <input
                  value={workerId}
                  onChange={(e) => setWorkerId(slugifyId(e.target.value))}
                  placeholder="marco-devops"
                  className={`${INPUT_CLASS} font-mono`}
                />
              </label>
              <label className="block space-y-1">
                <span className="text-xs font-medium text-gov-gray-700 dark:text-dark-text">
                  ¿Qué debe hacer este agente?
                </span>
                <textarea
                  value={behaviorPrompt}
                  onChange={(e) => setBehaviorPrompt(clampInput(e.target.value, 4000))}
                  rows={6}
                  placeholder="Ej: Agente DevOps que revisa logs PM2, diagnostica el gateway y propone fixes en sandbox..."
                  className={INPUT_CLASS}
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
                <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-200">
                  <p className="text-xs font-semibold">Opcional — la IA sugiere aclarar:</p>
                  <p className="mt-1">{draft.questions[0]}</p>
                </div>
              )}
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="block space-y-1">
                  <span className="text-xs font-medium">Nombre visible</span>
                  <input
                    value={draft.display_name}
                    onChange={(e) => updateDraft({ display_name: clampInput(e.target.value, 128) })}
                    className={INPUT_CLASS}
                  />
                </label>
                <label className="block space-y-1">
                  <span className="text-xs font-medium">ID técnico</span>
                  <input
                    value={draft.worker_id}
                    onChange={(e) => updateDraft({ worker_id: slugifyId(e.target.value) })}
                    className={`${INPUT_CLASS} font-mono`}
                  />
                </label>
              </div>
              <label className="block space-y-1">
                <span className="text-xs font-medium">Descripción</span>
                <textarea
                  value={draft.description}
                  onChange={(e) => updateDraft({ description: clampInput(e.target.value, 2048) })}
                  rows={4}
                  className={INPUT_CLASS}
                />
                <p className="text-xs text-gov-gray-500 dark:text-dark-muted">
                  {draft.description.length}/2048 caracteres
                </p>
              </label>
              <section className="rounded-lg border border-gov-gray-200 dark:border-dark-border">
                <div className="flex border-b border-gov-gray-100 dark:border-dark-border">
                  {(['system_prompt', 'soul'] as const).map((tab) => (
                    <button
                      key={tab}
                      type="button"
                      onClick={() => setInstructionTab(tab)}
                      className={`border-b-2 px-3 py-2 text-xs font-semibold ${
                        instructionTab === tab
                          ? 'border-gov-blue-700 text-gov-blue-800 dark:border-dark-cyan dark:text-dark-cyan'
                          : 'border-transparent text-gov-gray-500 dark:text-dark-muted'
                      }`}
                    >
                      {tab === 'system_prompt' ? `System prompt (${systemPromptLen})` : `Soul (${soulLen})`}
                    </button>
                  ))}
                </div>
                <div className="p-3">
                  {instructionTab === 'system_prompt' ? (
                    <label className="block space-y-1">
                      <span className="text-xs font-medium text-gov-gray-700 dark:text-dark-text">
                        Qué hace el agente (rol, herramientas, reglas)
                      </span>
                      <textarea
                        value={draft.system_prompt}
                        onChange={(e) => updateDraft({ system_prompt: clampInput(e.target.value, 12000) })}
                        rows={10}
                        className={`${INPUT_CLASS} font-mono text-xs`}
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
                    <label className="block space-y-1">
                      <span className="text-xs font-medium text-gov-gray-700 dark:text-dark-text">
                        Cómo habla y se comporta (tono, estilo, valores)
                      </span>
                      <textarea
                        value={draft.soul}
                        onChange={(e) => updateDraft({ soul: clampInput(e.target.value, 4000) })}
                        rows={8}
                        className={`${INPUT_CLASS} font-mono text-xs`}
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
              </section>
              <WorkerCompositionPanel
                composition={{
                  tool_profile: draft.tool_profile,
                  skills: draft.skills,
                  browser_sandbox: draft.browser_sandbox,
                  web_search: draft.web_search,
                }}
                onCompositionChange={(next: DraftComposition) =>
                  updateDraft({
                    tool_profile: DEFAULT_TOOL_PROFILE,
                    skills: next.skills,
                    browser_sandbox: next.browser_sandbox,
                    web_search: next.web_search,
                  })
                }
                disabled={busy}
                workerId={draft.worker_id}
                globalSkills={globalSkills}
                localSkills={localSkills}
              />
              <WorkerMcpGrantsPicker
                selectedConnectorIds={pendingMcpConnectorIds}
                onSelectionChange={setPendingMcpConnectorIds}
                disabled={busy}
              />
              {draft.suggested_skills.some((skill) => !skill.available) && (
                <div className="rounded-lg border border-amber-200 bg-amber-50/80 p-3 dark:border-amber-900/50 dark:bg-amber-950/20">
                  <p className="text-xs font-semibold text-amber-900 dark:text-amber-200">
                    Skills sugeridas no instaladas
                  </p>
                  <ul className="mt-2 space-y-1.5">
                    {draft.suggested_skills
                      .filter((skill) => !skill.available)
                      .map((skill) => (
                        <li key={skill.name} className="text-xs text-amber-950 dark:text-amber-100">
                          <span className="font-mono font-semibold">{skill.name}</span>
                          <span className="text-amber-800 dark:text-amber-300"> — {skill.reason}</span>
                        </li>
                      ))}
                  </ul>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      <div className="flex flex-wrap justify-end gap-2 border-t border-gov-gray-200 px-5 py-3 dark:border-dark-border">
        <button
          type="button"
          onClick={resetAndClose}
          className="rounded-lg border border-gov-gray-200 px-4 py-2 text-sm font-medium dark:border-dark-border"
        >
          Cancelar
        </button>
        {step === 1 && (
          <button
            type="button"
            disabled={busy}
            onClick={() => void generateDraft()}
            className="inline-flex items-center gap-2 rounded-lg bg-gov-blue-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-60"
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
              className="rounded-lg border border-gov-gray-200 px-4 py-2 text-sm font-medium dark:border-dark-border"
            >
              Cambiar descripción
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => void generateDraft()}
              className="rounded-lg border border-gov-gray-200 px-4 py-2 text-sm font-medium dark:border-dark-border"
            >
              Regenerar con IA
            </button>
            <button
              type="button"
              disabled={busy || !instructionsReady}
              onClick={() => void confirmDraft()}
              className="inline-flex items-center gap-2 rounded-lg bg-gov-blue-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-60"
            >
              {busy && <Loader2 size={16} className="animate-spin" />}
              Crear agente
            </button>
          </>
        )}
      </div>
    </DialogShell>
  );
}
