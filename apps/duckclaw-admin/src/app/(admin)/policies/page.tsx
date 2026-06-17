'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { adminService, type PromptPolicy, type PromptPolicyHealth } from '@/services/adminService';
import { useAuthStore } from '@/store/authStore';

const MANAGED_DRAFT_POLICY_TYPE = 'manager_task';
const MANAGED_DRAFT_POLICY_NAME = 'admin_workspace_managed_draft';
const FRAMEWORK_POLICY_TYPE = 'system_prompt';
const FRAMEWORK_POLICY_NAME = 'default';

type PolicyTab = 'workspace' | 'framework';

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

export default function PromptPoliciesPage() {
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

  useEffect(() => {
    load();
    loadFramework();
    loadHealth();
  }, [load, loadFramework, loadHealth]);

  const reloadAll = () => {
    load();
    loadFramework();
    loadHealth();
  };

  const restoreFramework = async () => {
    if (!canWrite || restoringFramework) return;
    const confirmed = window.confirm(
      'Restaurar framework_policy_pack_v1 desde el repo. No modifica system_prompt/<worker>. ¿Continuar?'
    );
    if (!confirmed) return;
    setRestoringFramework(true);
    setError(null);
    setMessage(null);
    try {
      const result = await adminService.restoreFrameworkPolicies();
      setMessage(`Framework restaurado: ${result.applied.join(', ') || 'sin cambios'}`);
      reloadAll();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo restaurar framework');
    } finally {
      setRestoringFramework(false);
    }
  };

  const syncCatalog = async () => {
    if (!canWrite || syncingCatalog) return;
    const confirmed = window.confirm(
      'Sincronizar system_prompt/<worker> desde snapshots del catálogo. Workers con policy activa se omiten salvo force. ¿Continuar?'
    );
    if (!confirmed) return;
    setSyncingCatalog(true);
    setError(null);
    setMessage(null);
    try {
      const result = await adminService.syncCatalogPrompts(false);
      const parts = [
        result.synced.length ? `synced: ${result.synced.join(', ')}` : null,
        result.skipped.length ? `skipped: ${result.skipped.join(', ')}` : null,
        result.failed.length ? `failed: ${result.failed.join(', ')}` : null,
      ].filter(Boolean);
      setMessage(parts.length ? `Catálogo sincronizado — ${parts.join(' · ')}` : 'Catálogo sincronizado sin cambios');
      reloadAll();
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
      setMessage(`Versión ${result.policy.version} encolada en db-writer.`);
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
      <header>
        <p className="text-xs font-black uppercase tracking-[0.18em] text-gov-blue-700 dark:text-dark-cyan">
          Configuración DB-first
        </p>
        <h1 className="mt-1 text-3xl font-black text-gov-gray-900 dark:text-dark-text">Prompt policies</h1>
        <p className="mt-1 max-w-3xl text-sm text-gov-gray-500 dark:text-dark-muted">
          Administra versiones activas de policies desde DuckDB. El wizard de proyectos lee esta policy al
          preparar borradores; el código no debe cambiar para ajustar el comportamiento.
        </p>
      </header>

      <section className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
        <p className="font-bold">Cambios sensibles</p>
        <p className="mt-1">
          Guardar crea una nueva versión activa vía db-writer. Valida el JSON y prueba el wizard antes de
          asumir que el nuevo contrato está listo para usuarios.
        </p>
      </section>

      {error && <p className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}
      {message && <p className="rounded-xl bg-green-50 px-4 py-3 text-sm text-green-700">{message}</p>}

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => setActiveTab('framework')}
          className={`rounded-xl px-4 py-2 text-sm font-black ${
            activeTab === 'framework'
              ? 'bg-gov-blue-700 text-white'
              : 'border border-gov-blue-200 text-gov-blue-800 dark:border-dark-border dark:text-dark-cyan'
          }`}
        >
          Framework pack
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('workspace')}
          className={`rounded-xl px-4 py-2 text-sm font-black ${
            activeTab === 'workspace'
              ? 'bg-gov-blue-700 text-white'
              : 'border border-gov-blue-200 text-gov-blue-800 dark:border-dark-border dark:text-dark-cyan'
          }`}
        >
          Workspace draft
        </button>
      </div>

      {activeTab === 'framework' ? (
        <section className="grid gap-4 lg:grid-cols-[1fr_280px]">
          <div className="rounded-3xl border border-gov-blue-100 bg-white p-5 dark:border-dark-border dark:bg-dark-surface">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-xs font-black uppercase tracking-wide text-gov-gray-500 dark:text-dark-muted">
                  Framework pack v1
                </p>
                <p className="mt-1 font-mono text-sm text-gov-gray-900 dark:text-dark-text">
                  system_prompt/default + capability/*
                </p>
              </div>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={reloadAll}
                  className="rounded-xl border border-gov-blue-200 px-3 py-2 text-xs font-black text-gov-blue-800 hover:bg-gov-blue-50 dark:border-dark-border dark:text-dark-cyan"
                >
                  Recargar
                </button>
                <button
                  type="button"
                  onClick={syncCatalog}
                  disabled={!canWrite || syncingCatalog}
                  className="rounded-xl border border-gov-blue-200 px-3 py-2 text-xs font-black text-gov-blue-800 hover:bg-gov-blue-50 disabled:cursor-not-allowed disabled:opacity-60 dark:border-dark-border dark:text-dark-cyan"
                >
                  {syncingCatalog ? 'Sincronizando...' : 'Sync catálogo'}
                </button>
                <button
                  type="button"
                  onClick={restoreFramework}
                  disabled={!canWrite || restoringFramework}
                  className="rounded-xl bg-amber-600 px-3 py-2 text-xs font-black text-white hover:bg-amber-700 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {restoringFramework ? 'Restaurando...' : 'Restaurar defaults'}
                </button>
              </div>
            </div>
            <textarea
              value={frameworkContent}
              readOnly
              spellCheck={false}
              className="min-h-[420px] w-full rounded-2xl border border-gov-blue-100 bg-gov-gray-50 p-4 font-mono text-xs leading-5 text-gov-gray-800 outline-none dark:border-dark-border dark:bg-dark-bg dark:text-dark-text"
              aria-label="system_prompt/default activo"
            />
            <p className="mt-3 text-xs text-gov-gray-500 dark:text-dark-muted">
              Vista de lectura del prompt base. Restaurar re-aplica el JSON del repo sin tocar policies por worker.
            </p>
            <div className="mt-4 space-y-2">
              {frameworkPolicies.map((policy) => (
                <p
                  key={policy.policy_id}
                  className="rounded-xl border border-gov-blue-50 px-3 py-2 font-mono text-xs dark:border-dark-border"
                >
                  {policy.policy_type}/{policy.policy_name} v{policy.version}{' '}
                  {policy.active ? '· activa' : '· inactiva'}
                </p>
              ))}
            </div>
          </div>
          <aside className="space-y-4">
            <section className="rounded-3xl border border-gov-blue-100 bg-white p-5 dark:border-dark-border dark:bg-dark-surface">
              <p className="text-xs font-black uppercase tracking-wide text-gov-gray-500 dark:text-dark-muted">
                Health de policies
              </p>
              {healthError ? (
                <p className="mt-3 rounded-xl bg-red-50 px-3 py-2 text-xs text-red-700">{healthError}</p>
              ) : health ? (
                <div className="mt-3 space-y-3 text-sm">
                  <p
                    className={`rounded-xl px-3 py-2 font-bold ${
                      health.ok ? 'bg-green-50 text-green-700' : 'bg-amber-50 text-amber-800'
                    }`}
                  >
                    {health.ok
                      ? `OK: ${health.checked_count} requirements`
                      : `${health.missing_count} missing de ${health.checked_count}`}
                  </p>
                  {health.inherited_count > 0 && (
                    <div className="space-y-2">
                      <p className="text-xs font-black uppercase tracking-wide text-sky-700 dark:text-sky-300">
                        Herencia ({health.inherited_count})
                      </p>
                      {health.inherited.slice(0, 6).map((item) => (
                        <p
                          key={`${item.policy_type}:${item.policy_name}:${item.source}`}
                          className="break-all rounded-xl border border-sky-200 px-3 py-2 font-mono text-xs text-sky-900 dark:border-sky-900 dark:text-sky-200"
                        >
                          {item.policy_type}/{item.policy_name}
                          <span className="block pt-1 font-sans text-[11px] opacity-80">{item.warning}</span>
                        </p>
                      ))}
                    </div>
                  )}
                </div>
              ) : null}
            </section>
          </aside>
        </section>
      ) : (
      <section className="grid gap-4 lg:grid-cols-[1fr_280px]">
        <div className="rounded-3xl border border-gov-blue-100 bg-white p-5 dark:border-dark-border dark:bg-dark-surface">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-xs font-black uppercase tracking-wide text-gov-gray-500 dark:text-dark-muted">
                Policy administrada
              </p>
              <p className="mt-1 font-mono text-sm text-gov-gray-900 dark:text-dark-text">
                {MANAGED_DRAFT_POLICY_TYPE}/{MANAGED_DRAFT_POLICY_NAME}
              </p>
            </div>
            <button
              type="button"
              onClick={reloadAll}
              className="rounded-xl border border-gov-blue-200 px-3 py-2 text-xs font-black text-gov-blue-800 hover:bg-gov-blue-50 dark:border-dark-border dark:text-dark-cyan"
            >
              Recargar
            </button>
          </div>

          {loading ? (
            <p className="text-sm text-gov-gray-500 dark:text-dark-muted">Cargando policy...</p>
          ) : (
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              spellCheck={false}
              className="min-h-[520px] w-full rounded-2xl border border-gov-blue-100 bg-gov-gray-50 p-4 font-mono text-xs leading-5 text-gov-gray-800 outline-none focus:border-gov-blue-400 dark:border-dark-border dark:bg-dark-bg dark:text-dark-text"
              aria-label="Contenido JSON de la prompt policy"
              readOnly={!canWrite}
            />
          )}

          <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
            <p className="text-xs text-gov-gray-500 dark:text-dark-muted">
              Próxima versión: <span className="font-mono">{nextVersion}</span>
              {!canWrite && ' - Solo lectura para usuarios no admin.'}
            </p>
            <button
              type="button"
              onClick={save}
              disabled={!canWrite || saving || loading}
              className="rounded-xl bg-gov-blue-700 px-4 py-2 text-sm font-black text-white hover:bg-gov-blue-900 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {saving ? 'Guardando...' : 'Guardar nueva versión'}
            </button>
          </div>
        </div>

        <aside className="space-y-4">
          <section className="rounded-3xl border border-gov-blue-100 bg-white p-5 dark:border-dark-border dark:bg-dark-surface">
            <div className="flex items-center justify-between gap-3">
              <p className="text-xs font-black uppercase tracking-wide text-gov-gray-500 dark:text-dark-muted">
                Health de policies
              </p>
              <button
                type="button"
                onClick={loadHealth}
                className="rounded-xl border border-gov-blue-200 px-3 py-1.5 text-[11px] font-black text-gov-blue-800 hover:bg-gov-blue-50 dark:border-dark-border dark:text-dark-cyan"
              >
                Auditar
              </button>
            </div>
            {healthError ? (
              <p className="mt-3 rounded-xl bg-red-50 px-3 py-2 text-xs text-red-700">{healthError}</p>
            ) : health ? (
              <div className="mt-3 space-y-3 text-sm">
                <p
                  className={
                    health.ok
                      ? 'rounded-xl bg-green-50 px-3 py-2 font-bold text-green-700'
                      : 'rounded-xl bg-amber-50 px-3 py-2 font-bold text-amber-800'
                  }
                >
                  {health.ok
                    ? `OK: ${health.checked_count} requirements activos`
                    : `${health.missing_count} de ${health.checked_count} requirements faltan`}
                </p>
                {health.inherited_count > 0 && (
                  <div className="space-y-2">
                    <p className="text-xs font-black uppercase tracking-wide text-sky-700 dark:text-sky-300">
                      Herencia ({health.inherited_count})
                    </p>
                    {health.inherited.slice(0, 8).map((item) => (
                      <p
                        key={`${item.policy_type}:${item.policy_name}:${item.source}`}
                        className="break-all rounded-xl border border-sky-200 px-3 py-2 font-mono text-xs text-sky-900 dark:border-sky-900 dark:text-sky-200"
                      >
                        {item.policy_type}/{item.policy_name}
                        <span className="block pt-1 font-sans text-[11px] opacity-80">{item.warning}</span>
                      </p>
                    ))}
                  </div>
                )}
                {health.missing_count > 0 && (
                  <div className="space-y-2">
                    <p className="text-xs font-black uppercase tracking-wide text-amber-800 dark:text-amber-200">
                      Missing ({health.missing_count})
                    </p>
                    {health.missing.slice(0, 8).map((item) => (
                      <p
                        key={`${item.policy_type}:${item.policy_name}:${item.source}`}
                        className="break-all rounded-xl border border-amber-200 px-3 py-2 font-mono text-xs text-amber-900 dark:border-amber-900 dark:text-amber-200"
                      >
                        {item.policy_type}/{item.policy_name}
                        <span className="block pt-1 font-sans text-[11px] opacity-70">{item.source}</span>
                      </p>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <p className="mt-3 text-sm text-gov-gray-500 dark:text-dark-muted">Auditando requirements...</p>
            )}
          </section>

          <section className="rounded-3xl border border-gov-blue-100 bg-white p-5 dark:border-dark-border dark:bg-dark-surface">
            <p className="text-xs font-black uppercase tracking-wide text-gov-gray-500 dark:text-dark-muted">
              Versiones
            </p>
          <div className="mt-3 space-y-2">
            {policies.length === 0 && (
              <p className="text-sm text-gov-gray-500 dark:text-dark-muted">Sin versiones registradas.</p>
            )}
            {policies.map((policy) => (
              <div
                key={policy.policy_id}
                className="rounded-2xl border border-gov-blue-50 p-3 text-sm dark:border-dark-border"
              >
                <div className="flex items-center justify-between gap-2">
                  <p className="font-mono font-black">v{policy.version}</p>
                  <span className="rounded-full bg-gov-gray-100 px-2 py-0.5 text-[11px] font-bold text-gov-gray-600 dark:bg-dark-bg dark:text-dark-muted">
                    {policy.active ? policy.status : 'inactiva'}
                  </span>
                </div>
                <p className="mt-1 break-all font-mono text-[11px] text-gov-gray-500 dark:text-dark-muted">
                  {policy.checksum.slice(0, 16)}
                </p>
                <button
                  type="button"
                  onClick={() => deactivateVersion(policy)}
                  disabled={!canWrite || !policy.active || deactivatingVersion === policy.version}
                  className="mt-3 w-full rounded-xl border border-red-200 px-3 py-2 text-xs font-black text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-red-900 dark:text-red-300 dark:hover:bg-red-950/30"
                >
                  {deactivatingVersion === policy.version
                    ? 'Desactivando...'
                    : policy.active
                      ? 'Desactivar versión'
                      : 'Versión inactiva'}
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
