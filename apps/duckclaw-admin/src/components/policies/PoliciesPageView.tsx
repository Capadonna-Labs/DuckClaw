'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { adminService, type PromptPolicy, type PromptPolicyHealth } from '@/services/adminService';
import type { TemplateSummary } from '@/types/admin';
import { formatWriteTaskPollNotice, pollWriteTask } from '@/lib/pollWriteTask';
import { useAuthStore } from '@/store/authStore';
import type { EmbeddedViewProps } from '@/components/admin/embeddedView';

const MANAGED_DRAFT_POLICY_TYPE = 'manager_task';
const MANAGED_DRAFT_POLICY_NAME = 'admin_workspace_managed_draft';
const FRAMEWORK_POLICY_TYPE = 'system_prompt';
const FRAMEWORK_POLICY_NAME = 'default';

type PolicyTab = 'workspace' | 'framework';

const TAB_COPY: Record<
  PolicyTab,
  { label: string; hint: string; title: string; audience: string }
> = {
  framework: {
    label: 'Reglas base',
    hint: 'Cómo debe comportarse DuckClaw en general (tono, límites, RAG).',
    title: 'Reglas base de DuckClaw',
    audience: 'Afecta a todos los agentes. La mayoría de equipos solo revisa esto una vez.',
  },
  workspace: {
    label: 'Wizard de proyectos',
    hint: 'JSON avanzado del asistente al crear proyectos nuevos.',
    title: 'Borrador del asistente de proyectos',
    audience: 'Solo para quien personaliza el flujo «crear proyecto» en la consola.',
  },
};

function humanHealthSummary(health: PromptPolicyHealth): string {
  if (health.ok) {
    return `Todo en orden: ${health.checked_count} reglas necesarias están cargadas.`;
  }
  return `Faltan ${health.missing_count} de ${health.checked_count} reglas. Usa «Volver a reglas de fábrica» o «Copiar instrucciones a agentes».`;
}

function agentSkillsLabel(skills: string[] | undefined): string {
  if (skills?.length) {
    return `Herramientas: ${skills.join(', ')}`;
  }
  return 'Conversación y consultas a la base de datos (sin extras en el manifiesto).';
}

function prettyJson(raw: string): string {
  try {
    return JSON.stringify(JSON.parse(raw), null, 2);
  } catch {
    return raw;
  }
}

function latestVersion(policies: PromptPolicy[]): number {
  return policies.reduce((max, policy) => Math.max(max, Number(policy.version || 0)), 0);
}

export default function PromptPoliciesPage({ embedded = false }: EmbeddedViewProps) {
  const { usuario } = useAuthStore();
  const canWrite = usuario?.rol === 'admin';

  const [policies, setPolicies] = useState<PromptPolicy[]>([]);
  const [content, setContent] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deactivatingVersion, setDeactivatingVersion] = useState<number | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [health, setHealth] = useState<PromptPolicyHealth | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<PolicyTab>('framework');
  const [frameworkPolicies, setFrameworkPolicies] = useState<PromptPolicy[]>([]);
  const [frameworkContent, setFrameworkContent] = useState('');
  const [restoringFramework, setRestoringFramework] = useState(false);
  const [syncingCatalog, setSyncingCatalog] = useState(false);
  const [agents, setAgents] = useState<TemplateSummary[]>([]);
  const [workerPromptPolicies, setWorkerPromptPolicies] = useState<Set<string>>(new Set());
  const [agentsLoading, setAgentsLoading] = useState(true);
  const [agentsError, setAgentsError] = useState<string | null>(null);

  const agentsWithoutPrompt = useMemo(
    () =>
      agents.filter((agent) => {
        const workerId = agent.worker_id ?? agent.id;
        return !workerPromptPolicies.has(workerId);
      }),
    [agents, workerPromptPolicies]
  );

  const nextVersion = useMemo(() => latestVersion(policies) + 1, [policies]);

  const loadFramework = useCallback(() => {
    adminService
      .listPromptPolicies({
        policy_type: 'capability',
        include_inactive: true,
      })
      .then((rows) => {
        const frameworkRows = rows.filter((row) =>
          ['generic_worker', 'axis_coordinator', 'default_fallback'].includes(row.policy_name)
        );
        return adminService
          .listPromptPolicies({
            policy_type: FRAMEWORK_POLICY_TYPE,
            policy_name: FRAMEWORK_POLICY_NAME,
            include_inactive: true,
          })
          .then((systemRows) => {
            const merged = [...systemRows, ...frameworkRows];
            setFrameworkPolicies(merged);
            const activeDefault = systemRows.find((row) => row.active) ?? systemRows[0];
            setFrameworkContent(activeDefault?.content ?? '');
          });
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'No se pudo cargar framework pack'));
  }, []);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    adminService
      .listPromptPolicies({
        policy_type: MANAGED_DRAFT_POLICY_TYPE,
        policy_name: MANAGED_DRAFT_POLICY_NAME,
        include_inactive: true,
      })
      .then((rows) => {
        setPolicies(rows);
        const editablePolicy = rows.find((policy) => policy.active) ?? rows[0];
        setContent(editablePolicy?.content ? prettyJson(editablePolicy.content) : '');
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'No se pudo cargar la policy'))
      .finally(() => setLoading(false));
  }, []);

  const loadHealth = useCallback(() => {
    setHealthError(null);
    adminService
      .getPromptPolicyHealth()
      .then(setHealth)
      .catch((e) => setHealthError(e instanceof Error ? e.message : 'No se pudo auditar prompt policies'));
  }, []);

  const loadAgents = useCallback(() => {
    setAgentsLoading(true);
    setAgentsError(null);
    Promise.all([
      adminService.listTemplates({ include_inactive: false }),
      adminService.listPromptPolicies({ policy_type: 'system_prompt', include_inactive: false }),
    ])
      .then(([templates, policies]) => {
        setAgents(templates);
        const activeWorkerPrompts = new Set(
          policies
            .filter((policy) => policy.active && policy.policy_name !== 'default')
            .map((policy) => policy.policy_name)
        );
        setWorkerPromptPolicies(activeWorkerPrompts);
      })
      .catch((e) =>
        setAgentsError(e instanceof Error ? e.message : 'No se pudo cargar capacidades por agente')
      )
      .finally(() => setAgentsLoading(false));
  }, []);

  useEffect(() => {
    load();
    loadFramework();
    loadHealth();
    loadAgents();
  }, [load, loadFramework, loadHealth, loadAgents]);

  const reloadAll = () => {
    load();
    loadFramework();
    loadHealth();
    loadAgents();
  };

  const restoreFramework = async () => {
    if (!canWrite || restoringFramework) return;
    const confirmed = window.confirm(
      '¿Volver a las reglas de fábrica del repositorio?\n\nNo cambia las instrucciones ya guardadas por agente en el catálogo.'
    );
    if (!confirmed) return;
    setRestoringFramework(true);
    setError(null);
    setMessage(null);
    const busyLabel = 'Restauración de reglas base';
    try {
      const result = await adminService.restoreFrameworkPolicies();
      if (result.accepted && result.task_id) {
        setMessage(`${busyLabel}…`);
        const pollResult = await pollWriteTask(result.task_id, {
          onTick: (status) => {
            if (status === 'pending') {
              setMessage(`${busyLabel} (pendiente)…`);
            }
          },
        });
        reloadAll();
        const notice = formatWriteTaskPollNotice(pollResult, busyLabel);
        if (pollResult.state === 'success') {
          setMessage(notice);
        } else {
          setError(notice);
        }
      } else {
        setMessage(result.message || `${busyLabel} encolada.`);
        reloadAll();
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo restaurar framework');
    } finally {
      setRestoringFramework(false);
    }
  };

  const syncCatalog = async () => {
    if (!canWrite || syncingCatalog) return;
    const confirmed = window.confirm(
      '¿Copiar las instrucciones del catálogo a cada agente?\n\nLos que ya tienen instrucciones propias no se sobrescriben.'
    );
    if (!confirmed) return;
    setSyncingCatalog(true);
    setError(null);
    setMessage(null);
    const busyLabel = 'Copia de instrucciones a agentes';
    try {
      const result = await adminService.syncCatalogPrompts(false);
      if (result.accepted && result.task_id) {
        setMessage(`${busyLabel}…`);
        const pollResult = await pollWriteTask(result.task_id, {
          onTick: (status) => {
            if (status === 'pending') {
              setMessage(`${busyLabel} (pendiente)…`);
            }
          },
        });
        reloadAll();
        const notice = formatWriteTaskPollNotice(pollResult, busyLabel);
        if (pollResult.state === 'success') {
          setMessage(notice);
        } else {
          setError(notice);
        }
      } else {
        setMessage(result.message || `${busyLabel} encolada.`);
        reloadAll();
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo sincronizar catálogo');
    } finally {
      setSyncingCatalog(false);
    }
  };

  const save = async () => {
    if (!canWrite || saving) return;
    setError(null);
    setMessage(null);

    let compactContent = '';
    try {
      compactContent = JSON.stringify(JSON.parse(content));
    } catch {
      setError('El contenido debe ser JSON válido antes de guardar una nueva versión.');
      return;
    }

    setSaving(true);
    try {
      const result = await adminService.upsertPromptPolicy({
        policy_type: MANAGED_DRAFT_POLICY_TYPE,
        policy_name: MANAGED_DRAFT_POLICY_NAME,
        version: nextVersion,
        status: 'active',
        content: compactContent,
        metadata: {
          source: 'admin_ui',
          surface: 'managed_workspace_draft',
        },
      });
      setMessage(`Versión ${result.policy.version} guardada. Los cambios se aplican en unos segundos.`);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo guardar la policy');
    } finally {
      setSaving(false);
    }
  };

  const deactivateVersion = async (policy: PromptPolicy) => {
    if (!canWrite || deactivatingVersion !== null || !policy.active) return;
    const confirmed = window.confirm(
      `Esta acción desactiva solo la versión v${policy.version} de ${MANAGED_DRAFT_POLICY_TYPE}/${MANAGED_DRAFT_POLICY_NAME}.\n\nNo se borrará físicamente ni se migrará contenido. ¿Continuar?`
    );
    if (!confirmed) return;

    setError(null);
    setMessage(null);
    setDeactivatingVersion(policy.version);
    try {
      const result = await adminService.deactivatePromptPolicy(
        MANAGED_DRAFT_POLICY_TYPE,
        MANAGED_DRAFT_POLICY_NAME,
        policy.version
      );
      setMessage(`Versión ${result.version} encolada para desactivación en db-writer.`);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo desactivar la versión');
    } finally {
      setDeactivatingVersion(null);
    }
  };

  return (
    <div className="space-y-6">
      {!embedded && (
        <header>
          <p className="text-xs font-black uppercase tracking-[0.18em] text-gov-blue-700 dark:text-dark-cyan">
            Comportamiento de los agentes
          </p>
          <h1 className="mt-1 text-3xl font-black text-gov-gray-900 dark:text-dark-text">
            Instrucciones y reglas
          </h1>
          <p className="mt-1 max-w-3xl text-sm text-gov-gray-600 dark:text-dark-muted">
            Aquí defines <strong className="font-bold text-gov-gray-800 dark:text-dark-text">cómo hablan y qué pueden hacer</strong>{' '}
            tus agentes. No hace falta tocar código: guardas texto y DuckClaw lo aplica en el chat.
          </p>
        </header>
      )}

      {!embedded && (
      <section className="rounded-2xl border border-gov-blue-100 bg-white p-5 dark:border-dark-border dark:bg-dark-surface">
        <p className="text-sm font-black text-gov-gray-900 dark:text-dark-text">¿Qué sigue?</p>
        <ol className="mt-3 space-y-2 text-sm text-gov-gray-700 dark:text-dark-muted">
          <li className="flex gap-2">
            <span className="font-black text-gov-blue-700 dark:text-dark-cyan">1.</span>
            <span>
              Revisa <strong className="font-bold">Reglas base</strong> (pestaña abajo). Si algo falló al instalar, pulsa{' '}
              <em>Volver a reglas de fábrica</em>.
            </span>
          </li>
          <li className="flex gap-2">
            <span className="font-black text-gov-blue-700 dark:text-dark-cyan">2.</span>
            <span>
              Comprueba que cada agente tenga instrucciones: en la columna derecha, badge{' '}
              <em>Listo</em> o pulsa <em>Copiar instrucciones a agentes</em>
              {agentsWithoutPrompt.length > 0
                ? ` (${agentsWithoutPrompt.length} sin instrucciones aún).`
                : '.'}
            </span>
          </li>
          <li className="flex gap-2">
            <span className="font-black text-gov-blue-700 dark:text-dark-cyan">3.</span>
            <span>
              Opcional: sube documentos en{' '}
              <Link href="/knowledge" className="font-bold text-gov-blue-800 underline dark:text-dark-cyan">
                Gestor RAG
              </Link>{' '}
              con alcance <em>Framework</em> (global) o por proyecto. Prueba en{' '}
              <Link href="/playground" className="font-bold text-gov-blue-800 underline dark:text-dark-cyan">
                Playground
              </Link>
              .
            </span>
          </li>
        </ol>
      </section>
      )}

      {activeTab === 'workspace' && (
        <section className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
          <p className="font-bold">Zona avanzada</p>
          <p className="mt-1">
            Este JSON solo lo usa el asistente al crear proyectos nuevos. Si no sabes qué es, quédate en{' '}
            <button
              type="button"
              onClick={() => setActiveTab('framework')}
              className="font-bold underline"
            >
              Reglas base
            </button>
            .
          </p>
        </section>
      )}

      {error && <p className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}
      {message && <p className="rounded-xl bg-green-50 px-4 py-3 text-sm text-green-700">{message}</p>}

      <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end">
        {(Object.keys(TAB_COPY) as PolicyTab[]).map((tab) => {
          const copy = TAB_COPY[tab];
          const selected = activeTab === tab;
          return (
            <button
              key={tab}
              type="button"
              onClick={() => setActiveTab(tab)}
              className={`rounded-xl px-4 py-3 text-left sm:min-w-[200px] ${
                selected
                  ? 'bg-gov-blue-700 text-white'
                  : 'border border-gov-blue-200 text-gov-blue-800 dark:border-dark-border dark:text-dark-cyan'
              }`}
            >
              <span className="block text-sm font-black">{copy.label}</span>
              <span
                className={`mt-0.5 block text-xs font-normal ${
                  selected ? 'text-blue-100' : 'text-gov-gray-500 dark:text-dark-muted'
                }`}
              >
                {copy.hint}
              </span>
            </button>
          );
        })}
      </div>

      <p className="text-sm text-gov-gray-500 dark:text-dark-muted">{TAB_COPY[activeTab].audience}</p>

      {activeTab === 'framework' ? (
        <section className="grid gap-4 lg:grid-cols-[1fr_300px]">
          <div className="rounded-3xl border border-gov-blue-100 bg-white p-5 dark:border-dark-border dark:bg-dark-surface">
            <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="text-lg font-black text-gov-gray-900 dark:text-dark-text">
                  {TAB_COPY.framework.title}
                </h2>
                <p className="mt-1 text-sm text-gov-gray-600 dark:text-dark-muted">
                  Texto maestro: idioma, tono, cuándo usar herramientas y cómo tratar el conocimiento (RAG).
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={reloadAll}
                  className="rounded-xl border border-gov-blue-200 px-3 py-2 text-xs font-black text-gov-blue-800 hover:bg-gov-blue-50 dark:border-dark-border dark:text-dark-cyan"
                >
                  Actualizar vista
                </button>
                <button
                  type="button"
                  onClick={syncCatalog}
                  disabled={!canWrite || syncingCatalog}
                  title="Lleva las instrucciones del catálogo a cada agente que aún no las tenga"
                  className="rounded-xl border border-gov-blue-200 px-3 py-2 text-xs font-black text-gov-blue-800 hover:bg-gov-blue-50 disabled:cursor-not-allowed disabled:opacity-60 dark:border-dark-border dark:text-dark-cyan"
                >
                  {syncingCatalog ? 'Copiando…' : 'Copiar instrucciones a agentes'}
                </button>
                <button
                  type="button"
                  onClick={restoreFramework}
                  disabled={!canWrite || restoringFramework}
                  title="Restaura el paquete de reglas que viene con el repositorio"
                  className="rounded-xl bg-amber-600 px-3 py-2 text-xs font-black text-white hover:bg-amber-700 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {restoringFramework ? 'Restaurando…' : 'Volver a reglas de fábrica'}
                </button>
              </div>
            </div>
            <details className="group mb-4 rounded-2xl border border-gov-blue-50 dark:border-dark-border">
              <summary className="cursor-pointer list-none px-4 py-3 text-sm font-bold text-gov-blue-800 dark:text-dark-cyan">
                Ver texto técnico (solo lectura)
              </summary>
              <textarea
                value={frameworkContent}
                readOnly
                spellCheck={false}
                className="min-h-[320px] w-full border-t border-gov-blue-50 bg-gov-gray-50 p-4 font-mono text-xs leading-5 text-gov-gray-800 outline-none dark:border-dark-border dark:bg-dark-bg dark:text-dark-text"
                aria-label="Reglas base activas"
              />
            </details>
            <p className="text-xs text-gov-gray-500 dark:text-dark-muted">
              «Volver a reglas de fábrica» no borra las instrucciones personalizadas de cada agente en el catálogo.
            </p>
          </div>
          <aside className="space-y-4">
            <section className="rounded-3xl border border-gov-blue-100 bg-white p-5 dark:border-dark-border dark:bg-dark-surface">
              <p className="text-sm font-black text-gov-gray-900 dark:text-dark-text">Estado</p>
              <p className="mt-0.5 text-xs text-gov-gray-500 dark:text-dark-muted">
                Comprueba que DuckClaw tenga todas las reglas mínimas para funcionar.
              </p>
              {healthError ? (
                <p className="mt-3 rounded-xl bg-red-50 px-3 py-2 text-xs text-red-700">{healthError}</p>
              ) : health ? (
                <div className="mt-3 space-y-3 text-sm">
                  <p
                    className={`rounded-xl px-3 py-2 ${
                      health.ok ? 'bg-green-50 text-green-800' : 'bg-amber-50 text-amber-900'
                    }`}
                  >
                    {humanHealthSummary(health)}
                  </p>
                  {!health.ok && health.missing_count > 0 && (
                    <p className="text-xs text-gov-gray-600 dark:text-dark-muted">
                      Detalle: faltan {health.missing_count} entradas en la base de datos de reglas.
                    </p>
                  )}
                  {health.inherited_count > 0 && (
                    <div className="space-y-2">
                      <p className="text-xs font-bold text-sky-800 dark:text-sky-300">
                        Algunas reglas se heredan del paquete base ({health.inherited_count})
                      </p>
                      {health.inherited.slice(0, 4).map((item) => (
                        <p
                          key={`${item.policy_type}:${item.policy_name}:${item.source}`}
                          className="rounded-xl border border-sky-200 px-3 py-2 text-xs text-sky-900 dark:border-sky-900 dark:text-sky-200"
                        >
                          {item.warning}
                        </p>
                      ))}
                    </div>
                  )}
                </div>
              ) : null}
            </section>
            <section className="rounded-3xl border border-gov-blue-100 bg-white p-5 dark:border-dark-border dark:bg-dark-surface">
              <p className="text-sm font-black text-gov-gray-900 dark:text-dark-text">Tus agentes</p>
              <p className="mt-0.5 text-xs text-gov-gray-500 dark:text-dark-muted">
                ¿Pueden chatear con instrucciones cargadas? Edita cada uno en Plantillas.
              </p>
              {agentsError ? (
                <p className="mt-3 rounded-xl bg-red-50 px-3 py-2 text-xs text-red-700">{agentsError}</p>
              ) : agentsLoading ? (
                <p className="mt-3 text-sm text-gov-gray-500 dark:text-dark-muted">Cargando agentes…</p>
              ) : agents.length === 0 ? (
                <p className="mt-3 text-sm text-gov-gray-500 dark:text-dark-muted">
                  No hay agentes en el catálogo. Importa o crea uno en Plantillas.
                </p>
              ) : (
                <div className="mt-3 space-y-3">
                  {agents.map((agent) => {
                    const workerId = agent.worker_id ?? agent.id;
                    const hasPrompt = workerPromptPolicies.has(workerId);
                    return (
                      <div
                        key={agent.id}
                        className="rounded-xl border border-gov-blue-50 px-3 py-3 text-sm dark:border-dark-border"
                      >
                        <div className="flex flex-wrap items-start justify-between gap-2">
                          <div>
                            <Link
                              href={`/templates/${encodeURIComponent(agent.id)}`}
                              className="font-bold text-gov-blue-800 hover:underline dark:text-dark-cyan"
                            >
                              {agent.name ?? workerId}
                            </Link>
                          </div>
                          <div className="flex flex-wrap justify-end gap-1">
                            {hasPrompt ? (
                              <span className="rounded-full bg-green-50 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-green-700 dark:bg-green-950/40 dark:text-green-300">
                                Listo
                              </span>
                            ) : (
                              <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
                                Falta instrucciones
                              </span>
                            )}
                          </div>
                        </div>
                        <p className="mt-2 text-xs text-gov-gray-600 dark:text-dark-muted">
                          {agentSkillsLabel(agent.skills_list)}
                        </p>
                        {!hasPrompt && (
                          <Link
                            href={`/templates/${encodeURIComponent(agent.id)}?focus=system_prompt.md`}
                            className="mt-2 inline-block text-xs font-bold text-gov-blue-800 underline dark:text-dark-cyan"
                          >
                            Configurar instrucciones →
                          </Link>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </section>
          </aside>
        </section>
      ) : (
      <section className="grid gap-4 lg:grid-cols-[1fr_300px]">
        <div className="rounded-3xl border border-gov-blue-100 bg-white p-5 dark:border-dark-border dark:bg-dark-surface">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-black text-gov-gray-900 dark:text-dark-text">
                {TAB_COPY.workspace.title}
              </h2>
              <p className="mt-1 text-sm text-gov-gray-600 dark:text-dark-muted">
                Contrato JSON que lee el asistente al preparar un proyecto nuevo (avanzado).
              </p>
            </div>
            <button
              type="button"
              onClick={reloadAll}
              className="rounded-xl border border-gov-blue-200 px-3 py-2 text-xs font-black text-gov-blue-800 hover:bg-gov-blue-50 dark:border-dark-border dark:text-dark-cyan"
            >
              Actualizar vista
            </button>
          </div>

          {loading ? (
            <p className="text-sm text-gov-gray-500 dark:text-dark-muted">Cargando borrador…</p>
          ) : (
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              spellCheck={false}
              className="min-h-[520px] w-full rounded-2xl border border-gov-blue-100 bg-gov-gray-50 p-4 font-mono text-xs leading-5 text-gov-gray-800 outline-none focus:border-gov-blue-400 dark:border-dark-border dark:bg-dark-bg dark:text-dark-text"
              aria-label="JSON del borrador del wizard de proyectos"
              readOnly={!canWrite}
            />
          )}

          <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
            <p className="text-xs text-gov-gray-500 dark:text-dark-muted">
              Siguiente versión al guardar: <span className="font-mono">{nextVersion}</span>
              {!canWrite && ' — Solo administradores pueden editar.'}
            </p>
            <button
              type="button"
              onClick={save}
              disabled={!canWrite || saving || loading}
              className="rounded-xl bg-gov-blue-700 px-4 py-2 text-sm font-black text-white hover:bg-gov-blue-900 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {saving ? 'Guardando…' : 'Guardar borrador'}
            </button>
          </div>
        </div>

        <aside className="space-y-4">
          <section className="rounded-3xl border border-gov-blue-100 bg-white p-5 dark:border-dark-border dark:bg-dark-surface">
            <div className="flex items-center justify-between gap-3">
              <p className="text-sm font-black text-gov-gray-900 dark:text-dark-text">Estado</p>
              <button
                type="button"
                onClick={loadHealth}
                className="rounded-xl border border-gov-blue-200 px-3 py-1.5 text-[11px] font-black text-gov-blue-800 hover:bg-gov-blue-50 dark:border-dark-border dark:text-dark-cyan"
              >
                Comprobar
              </button>
            </div>
            {healthError ? (
              <p className="mt-3 rounded-xl bg-red-50 px-3 py-2 text-xs text-red-700">{healthError}</p>
            ) : health ? (
              <div className="mt-3 space-y-3 text-sm">
                <p
                  className={
                    health.ok
                      ? 'rounded-xl bg-green-50 px-3 py-2 text-green-800'
                      : 'rounded-xl bg-amber-50 px-3 py-2 text-amber-900'
                  }
                >
                  {humanHealthSummary(health)}
                </p>
                {health.missing_count > 0 && (
                  <div className="space-y-2">
                    <p className="text-xs font-bold text-amber-800 dark:text-amber-200">Qué falta</p>
                    {health.missing.slice(0, 6).map((item) => (
                      <p
                        key={`${item.policy_type}:${item.policy_name}:${item.source}`}
                        className="rounded-xl border border-amber-200 px-3 py-2 text-xs text-amber-900 dark:border-amber-900 dark:text-amber-200"
                      >
                        {item.policy_name || item.policy_type}
                      </p>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <p className="mt-3 text-sm text-gov-gray-500 dark:text-dark-muted">Comprobando…</p>
            )}
          </section>

          <section className="rounded-3xl border border-gov-blue-100 bg-white p-5 dark:border-dark-border dark:bg-dark-surface">
            <p className="text-sm font-black text-gov-gray-900 dark:text-dark-text">Historial de versiones</p>
          <div className="mt-3 space-y-2">
            {policies.length === 0 && (
              <p className="text-sm text-gov-gray-500 dark:text-dark-muted">Aún no hay versiones guardadas.</p>
            )}
            {policies.map((policy) => (
              <div
                key={policy.policy_id}
                className="rounded-2xl border border-gov-blue-50 p-3 text-sm dark:border-dark-border"
              >
                <div className="flex items-center justify-between gap-2">
                  <p className="font-black">Versión {policy.version}</p>
                  <span className="rounded-full bg-gov-gray-100 px-2 py-0.5 text-[11px] font-bold text-gov-gray-600 dark:bg-dark-bg dark:text-dark-muted">
                    {policy.active ? 'En uso' : 'Antigua'}
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => deactivateVersion(policy)}
                  disabled={!canWrite || !policy.active || deactivatingVersion === policy.version}
                  className="mt-3 w-full rounded-xl border border-red-200 px-3 py-2 text-xs font-black text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-red-900 dark:text-red-300 dark:hover:bg-red-950/30"
                >
                  {deactivatingVersion === policy.version
                    ? 'Desactivando…'
                    : policy.active
                      ? 'Dejar de usar esta versión'
                      : 'Versión antigua'}
                </button>
              </div>
            ))}
          </div>
          </section>
        </aside>
      </section>
      )}
    </div>
  );
}
