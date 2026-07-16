'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { FileText, FolderOpen, HardDrive, Trash2, Upload } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import ConfirmDangerModal from '@/components/admin/ConfirmDangerModal';
import { ProductivityVaultBrowser } from '@/components/productivity/ProductivityVaultBrowser';
import ReportsPageView from '@/components/reports/ReportsPageView';
import { adminService, type ProductivityArtifact } from '@/services/adminService';
import { pollWriteTask } from '@/lib/pollWriteTask';
import { cn } from '@/lib/utils';

/** Filtro de origen en bandeja — sin «informe»: eso es la vista Editor Word. */
type OriginFilter = 'all' | 'storage' | 'vault';
type PanelView = 'lista' | 'vault' | 'informes';

function parseView(raw: string | null): PanelView {
  if (raw === 'vault' || raw === 'informes' || raw === 'lista') return raw;
  return 'lista';
}

function originLabel(origin: OriginFilter): string {
  if (origin === 'storage') return 'Storage';
  if (origin === 'vault') return 'Vault';
  return 'Todos';
}

function laneBadge(lane: string): string {
  if (lane === 'report') return 'Word';
  if (lane === 'vault') return 'Vault';
  if (lane === 'storage') return 'Storage';
  return lane;
}

function laneIcon(lane: string) {
  if (lane === 'report') return <FileText size={16} className="text-sky-600" />;
  if (lane === 'vault') return <FolderOpen size={16} className="text-emerald-600" />;
  return <HardDrive size={16} className="text-gov-blue-700" />;
}

function formatBytes(n: number): string {
  if (!n || n <= 0) return '—';
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

const VIEW_TABS: { id: PanelView; label: string; hint: string }[] = [
  { id: 'lista', label: 'Bandeja', hint: 'Todo lo generado' },
  { id: 'vault', label: 'Vault', hint: 'Explorar OUTPUT' },
  { id: 'informes', label: 'Editor Word', hint: 'Plantillas y preview' },
];

export function ProductivityArtifactsPanel() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [view, setView] = useState<PanelView>(() => parseView(searchParams.get('view')));
  const [items, setItems] = useState<ProductivityArtifact[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [origin, setOrigin] = useState<OriginFilter>('all');
  const [pending, setPending] = useState<ProductivityArtifact | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [promotingId, setPromotingId] = useState('');

  useEffect(() => {
    setView(parseView(searchParams.get('view')));
  }, [searchParams]);

  const selectView = (next: PanelView) => {
    setView(next);
    router.replace(`/productividad?tab=artefactos&view=${next}`, { scroll: false });
  };

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await adminService.listProductivityArtifacts({
        lane: origin === 'all' ? undefined : origin,
        limit: 100,
      });
      // Bandeja muestra storage + vault + word; si origin=all no filtramos report.
      // Si el usuario filtró storage/vault, el API ya excluye report.
      setItems(res.artifacts);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudieron cargar los artefactos');
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [origin]);

  useEffect(() => {
    if (view === 'lista') void load();
  }, [load, view]);

  async function confirmDelete() {
    if (!pending) return;
    setDeleting(true);
    setError('');
    setNotice('');
    const target = pending;
    try {
      const res = await adminService.deleteProductivityArtifact(target.artifact_id);
      const polled = await pollWriteTask(res.task_id, { intervalMs: 400, maxAttempts: 60 });
      if (polled.state === 'failed') {
        throw new Error(polled.detail || 'No se pudo eliminar');
      }
      setItems((prev) => prev.filter((i) => i.artifact_id !== target.artifact_id));
      setPending(null);
      setNotice(`Eliminado: ${target.title}`);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo eliminar');
    } finally {
      setDeleting(false);
    }
  }

  async function promoteToVault(item: ProductivityArtifact) {
    setPromotingId(item.artifact_id);
    setError('');
    setNotice('');
    try {
      const res = await adminService.promoteProductivityArtifactToVault(item.artifact_id, {
        relative_dir: 'Productividad',
        remove_from_storage: false,
      });
      setNotice(`Copiado al vault: ${res.relative_path}`);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo promover al vault');
    } finally {
      setPromotingId('');
    }
  }

  return (
    <div className="space-y-4">
      {/* Una sola franja de navegación — sin segunda fila “Informe” vs “Informes” */}
      <div
        role="tablist"
        aria-label="Vistas de artefactos"
        className="flex flex-wrap gap-1 rounded-2xl border border-gov-blue-100 bg-gov-gray-50 p-1 dark:border-dark-border dark:bg-dark-bg"
      >
        {VIEW_TABS.map((t) => {
          const selected = view === t.id;
          return (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={selected}
              onClick={() => selectView(t.id)}
              className={cn(
                'min-w-[7.5rem] flex-1 rounded-xl px-3 py-2.5 text-left transition sm:flex-none',
                selected
                  ? 'bg-gov-blue-700 text-white'
                  : 'text-gov-blue-800 hover:bg-white dark:text-dark-cyan dark:hover:bg-dark-surface'
              )}
            >
              <span className="block text-sm font-black">{t.label}</span>
              <span
                className={cn(
                  'mt-0.5 block text-[11px] font-normal',
                  selected ? 'text-blue-100' : 'text-gov-gray-500 dark:text-dark-muted'
                )}
              >
                {t.hint}
              </span>
            </button>
          );
        })}
      </div>

      {view === 'vault' ? (
        <ProductivityVaultBrowser
          onIndexed={() => {
            setNotice('Archivo indexado. Ábrelo en Bandeja.');
          }}
        />
      ) : view === 'informes' ? (
        <div className="min-h-[calc(100vh-14rem)] overflow-hidden rounded-2xl border border-gov-blue-100 dark:border-dark-border">
          <ReportsPageView />
        </div>
      ) : (
        <>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="mr-1 text-xs font-semibold text-gov-gray-500 dark:text-dark-muted">
                Origen
              </span>
              {(['all', 'storage', 'vault'] as const).map((id) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => setOrigin(id)}
                  className={cn(
                    'rounded-full px-2.5 py-1 text-[11px] font-bold',
                    origin === id
                      ? 'bg-gov-blue-700 text-white'
                      : 'bg-white text-gov-gray-600 ring-1 ring-gov-gray-200 dark:bg-dark-surface dark:text-dark-muted dark:ring-dark-border'
                  )}
                >
                  {originLabel(id)}
                </button>
              ))}
            </div>
            <button
              type="button"
              onClick={() => void load()}
              className="text-xs font-semibold text-gov-blue-700 hover:underline dark:text-dark-cyan"
            >
              Actualizar
            </button>
          </div>

          {error ? (
            <p className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
              {error}
            </p>
          ) : null}
          {notice ? <p className="text-sm text-emerald-700 dark:text-emerald-300">{notice}</p> : null}

          {loading ? (
            <p className="text-sm text-gov-gray-500">Cargando…</p>
          ) : items.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-gov-blue-200 px-6 py-10 text-center dark:border-dark-border">
              <p className="font-semibold dark:text-dark-text">Bandeja vacía</p>
              <p className="mt-2 text-sm text-gov-gray-500 dark:text-dark-muted">
                Genera algo en el Chat, indexa desde Vault, o crea un documento en Editor Word.
              </p>
              <button
                type="button"
                onClick={() => selectView('informes')}
                className="mt-4 text-sm font-bold text-gov-blue-700 dark:text-dark-cyan"
              >
                Abrir Editor Word →
              </button>
            </div>
          ) : (
            <ul className="divide-y divide-gov-gray-100 overflow-hidden rounded-2xl border border-gov-blue-100 dark:divide-dark-border dark:border-dark-border">
              {items.map((item) => (
                <li
                  key={item.artifact_id}
                  className="flex items-start gap-3 bg-white px-4 py-3 dark:bg-dark-surface"
                >
                  <div className="mt-0.5 shrink-0">{laneIcon(item.lane)}</div>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="truncate font-semibold dark:text-dark-text">{item.title}</p>
                      <span className="rounded-full bg-gov-gray-100 px-2 py-0.5 text-[10px] font-bold uppercase text-gov-gray-600 dark:bg-dark-bg dark:text-dark-muted">
                        {laneBadge(item.lane)}
                      </span>
                    </div>
                    <p className="mt-0.5 truncate font-mono text-[11px] text-gov-gray-500 dark:text-dark-muted">
                      {item.filename || item.source_ref || item.artifact_id}
                      {item.byte_size ? ` · ${formatBytes(item.byte_size)}` : ''}
                      {typeof item.progress_percent === 'number'
                        ? ` · ${item.progress_percent}%`
                        : ''}
                    </p>
                    {item.lane === 'report' && item.source_ref ? (
                      <button
                        type="button"
                        onClick={() => selectView('informes')}
                        className="mt-1 text-xs font-semibold text-gov-blue-700 dark:text-dark-cyan"
                      >
                        Abrir en Editor Word
                      </button>
                    ) : null}
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    {item.lane === 'storage' ? (
                      <button
                        type="button"
                        title="Copiar al vault OUTPUT"
                        aria-label={`Promover ${item.title} al vault`}
                        disabled={promotingId === item.artifact_id}
                        onClick={() => void promoteToVault(item)}
                        className="rounded-lg p-2 text-gov-gray-400 hover:bg-emerald-50 hover:text-emerald-700 disabled:opacity-40 dark:hover:bg-emerald-950/40"
                      >
                        <Upload size={16} />
                      </button>
                    ) : null}
                    <button
                      type="button"
                      title="Eliminar"
                      aria-label={`Eliminar ${item.title}`}
                      onClick={() => setPending(item)}
                      className="rounded-lg p-2 text-gov-gray-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950/40"
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </>
      )}

      <ConfirmDangerModal
        isOpen={Boolean(pending)}
        title="Eliminar artefacto"
        description={
          pending?.lane === 'storage'
            ? 'Se borrará del índice y del storage local del repo.'
            : pending?.lane === 'report'
              ? 'Se archivará el documento Word (soft-delete).'
              : 'Se archivará el registro (el archivo del vault no se borra del disco).'
        }
        confirmLabel="Sí, eliminar"
        isLoading={deleting}
        details={
          pending
            ? [
                { label: 'Título', value: pending.title },
                { label: 'Tipo', value: laneBadge(pending.lane) },
                { label: 'ID', value: pending.artifact_id },
              ]
            : []
        }
        onConfirm={() => void confirmDelete()}
        onCancel={() => {
          if (!deleting) setPending(null);
        }}
      />
    </div>
  );
}
