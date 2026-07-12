'use client';

import { useState } from 'react';
import { KeyRound, Loader2 } from 'lucide-react';
import { ViewChrome, type EmbeddedViewProps } from '@/components/admin/embeddedView';
import { adminService, type IntegrationCatalogItem } from '@/services/adminService';
import { pollWriteTask } from '@/lib/pollWriteTask';
import {
  integrationScopeLabel,
  type IntegrationCatalogScope,
} from '@/lib/integrationApiKeys';
import { useIntegrationCatalog } from '@/components/integrations/useIntegrationCatalog';
import { useAuthStore } from '@/store/authStore';

function IntegrationKeyRow({
  item,
  canWrite,
  scope,
  draft,
  onDraftChange,
  onSave,
  busy,
}: {
  item: IntegrationCatalogItem;
  canWrite: boolean;
  scope: IntegrationCatalogScope;
  draft: string;
  onDraftChange: (value: string) => void;
  onSave: () => void;
  busy: boolean;
}) {
  return (
    <li className="rounded-lg border border-gov-gray-200 bg-white p-4 dark:border-dark-border dark:bg-dark-surface">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-semibold text-gov-gray-900 dark:text-dark-text">{item.label}</p>
          <p className="mt-0.5 text-xs text-gov-gray-600 dark:text-dark-muted">{item.description}</p>
          <p className="mt-1 font-mono text-[10px] text-gov-gray-400">
            {item.domain}.{item.setting_key} · fallback {item.env_fallback}
          </p>
          {item.related_skills.length > 0 ? (
            <p className="mt-1 text-[10px] text-gov-gray-500 dark:text-dark-muted">
              Skills: {item.related_skills.join(', ')}
            </p>
          ) : null}
        </div>
        <span
          className={`rounded-lg px-2 py-1 text-[10px] font-semibold ${
            item.configured
              ? 'bg-emerald-50 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200'
              : 'bg-amber-50 text-amber-900 dark:bg-amber-950/30 dark:text-amber-200'
          }`}
        >
          {item.configured ? `Configurada (${item.source})` : 'Sin clave'}
        </span>
      </div>

      {canWrite ? (
        <div className="mt-3 flex flex-wrap items-end gap-2">
          <label className="min-w-[min(100%,20rem)] flex-1">
            <span className="sr-only">API key {item.label}</span>
            <input
              type="password"
              autoComplete="off"
              placeholder={item.configured ? 'Nueva clave (reemplaza)' : 'Pegar API key o token'}
              value={draft}
              onChange={(e) => onDraftChange(e.target.value)}
              className="w-full rounded-lg border border-gov-gray-200 px-3 py-2 text-sm dark:border-dark-border dark:bg-dark-bg"
            />
          </label>
          <button
            type="button"
            disabled={busy}
            onClick={onSave}
            className="rounded-lg bg-gov-blue-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
          >
            {busy ? 'Guardando…' : `Guardar (${integrationScopeLabel(scope)})`}
          </button>
          {item.docs_url ? (
            <a
              href={item.docs_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs font-semibold text-gov-blue-700 hover:underline dark:text-dark-cyan"
            >
              Obtener clave
            </a>
          ) : null}
        </div>
      ) : (
        <p className="mt-2 text-xs text-gov-gray-500">Solo administradores pueden guardar claves.</p>
      )}
    </li>
  );
}

export default function IntegrationApiKeysPageView({ embedded = false }: EmbeddedViewProps) {
  const { usuario } = useAuthStore();
  const canWrite = usuario?.rol === 'admin';
  const { catalog, loading, error, reload } = useIntegrationCatalog();
  const [scope, setScope] = useState<IntegrationCatalogScope>('tenant');
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [savingId, setSavingId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const saveKey = async (item: IntegrationCatalogItem) => {
    if (!canWrite) return;
    const value = (drafts[item.id] ?? '').trim();
    if (!value) {
      setNotice('Escribe la clave antes de guardar.');
      return;
    }
    setSavingId(item.id);
    setNotice(null);
    try {
      const result = await adminService.patchRuntimeSettings([
        {
          domain: item.domain,
          key: item.setting_key,
          value,
          scope,
          secret: true,
        },
      ]);
      if (result.task_id) {
        const polled = await pollWriteTask(result.task_id);
        if (polled.state === 'failed') {
          throw new Error(polled.detail || 'No se guardó la clave');
        }
      }
      setDrafts((prev) => ({ ...prev, [item.id]: '' }));
      setNotice(`Clave guardada en DuckDB (${integrationScopeLabel(scope)}).`);
      await reload();
    } catch (e) {
      setNotice(e instanceof Error ? e.message : 'Error al guardar');
    } finally {
      setSavingId(null);
    }
  };

  return (
    <ViewChrome embedded={embedded}>
      {!embedded && (
        <header>
          <h1 className="text-2xl font-bold dark:text-dark-text">API keys</h1>
          <p className="mt-1 text-sm text-gov-gray-500 dark:text-dark-muted">
            Catálogo empaquetado del framework — cada workspace configura sus integraciones sin tocar .env
          </p>
        </header>
      )}

      <section className="space-y-4 rounded-lg border border-gov-gray-200 bg-white p-4 dark:border-dark-border dark:bg-dark-surface">
        <div className="flex flex-wrap items-start justify-between gap-3 border-b border-gov-gray-100 pb-3 dark:border-dark-border">
          <div className="flex items-start gap-2">
            <KeyRound size={18} className="mt-0.5 text-gov-blue-700 dark:text-dark-cyan" aria-hidden />
            <div>
              <h2 className="text-sm font-semibold text-gov-gray-900 dark:text-dark-text">
                Claves de integración
              </h2>
              <p className="mt-0.5 text-xs text-gov-gray-500 dark:text-dark-muted">
                Catálogo:{' '}
                <code className="font-mono text-[10px]">
                  {catalog?.pack_version ?? '…'}
                </code>
                {catalog?.pack_source ? (
                  <>
                    {' '}
                    ·{' '}
                    <span className="font-mono text-[10px] break-all">{catalog.pack_source}</span>
                  </>
                ) : null}
              </p>
            </div>
          </div>
          {canWrite ? (
            <label className="text-xs text-gov-gray-600 dark:text-dark-muted">
              <span className="mb-1 block font-medium">Ámbito al guardar</span>
              <select
                value={scope}
                onChange={(e) => setScope(e.target.value as IntegrationCatalogScope)}
                className="rounded-lg border border-gov-gray-200 px-2 py-1.5 text-sm dark:border-dark-border dark:bg-dark-bg"
              >
                <option value="tenant">Workspace (tenant) — recomendado</option>
                <option value="global">Global plataforma</option>
                <option value="actor">Personal (solo este usuario)</option>
              </select>
            </label>
          ) : null}
        </div>

        <p className="text-xs text-gov-gray-600 dark:text-dark-muted">
          Precedencia: DuckDB ({integrationScopeLabel('tenant')} → global → actor) → fallback{' '}
          <code className="font-mono text-[10px]">.env</code> bootstrap. Mismo catálogo para todos los
          nichos; cada tenant activa solo las skills que necesita en sus agentes.
        </p>

        {catalog?.tenant_id ? (
          <p className="text-[10px] text-gov-gray-400">
            Tenant: <span className="font-mono">{catalog.tenant_id}</span>
            {catalog.actor_email ? (
              <>
                {' '}
                · Actor: <span className="font-mono">{catalog.actor_email}</span>
              </>
            ) : null}
          </p>
        ) : null}

        {loading ? (
          <p className="flex items-center gap-2 text-sm text-gov-gray-500">
            <Loader2 size={16} className="animate-spin" />
            Cargando catálogo…
          </p>
        ) : null}
        {error ? <p className="text-sm text-red-600">{error}</p> : null}
        {notice ? (
          <p className="rounded-lg bg-gov-gray-50 px-3 py-2 text-sm dark:bg-dark-bg">{notice}</p>
        ) : null}

        {!loading && !error && catalog?.groups.length === 0 ? (
          <p className="text-sm text-gov-gray-500">No hay integraciones en el catálogo empaquetado.</p>
        ) : null}

        <div className="space-y-6">
          {(catalog?.groups ?? []).map((group) => (
            <section key={group.id} className="space-y-2">
              <header>
                <h3 className="text-sm font-semibold text-gov-gray-900 dark:text-dark-text">
                  {group.title}
                </h3>
                {group.description ? (
                  <p className="text-xs text-gov-gray-500 dark:text-dark-muted">{group.description}</p>
                ) : null}
              </header>
              <ul className="space-y-3">
                {group.integrations.map((item) => (
                  <IntegrationKeyRow
                    key={item.id}
                    item={item}
                    canWrite={canWrite}
                    scope={scope}
                    draft={drafts[item.id] ?? ''}
                    onDraftChange={(value) => setDrafts((prev) => ({ ...prev, [item.id]: value }))}
                    onSave={() => void saveKey(item)}
                    busy={savingId === item.id}
                  />
                ))}
              </ul>
            </section>
          ))}
        </div>
      </section>
    </ViewChrome>
  );
}
