'use client';

import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import Link from 'next/link';
import { useParams, useRouter, useSearchParams } from 'next/navigation';
import { adminService } from '@/services/adminService';
import type { TemplateDetail } from '@/types/admin';
import { useAuthStore } from '@/store/authStore';
import ConfirmDangerModal from '@/components/admin/ConfirmDangerModal';
import { ChevronRight, Save, CheckCircle, Eye, FileCode, Plus, Trash2, Loader2 } from 'lucide-react';
import { ChatMarkdown } from '@/components/chat/ChatMarkdown';
import { WorkerCapabilitiesCard } from '@/components/templates/WorkerCapabilitiesCard';
import { ManifestGuidedPanel } from '@/components/templates/ManifestGuidedPanel';
import { SecurityPolicyInfoPanel } from '@/components/templates/SecurityPolicyInfoPanel';
import { AgentOnboardingBanner } from '@/components/templates/AgentOnboardingBanner';
import { WorkerDisplayNameEditor } from '@/components/templates/WorkerDisplayNameEditor';
import { pollWriteTask } from '@/lib/pollWriteTask';

type MarkdownViewMode = 'edit' | 'preview';

function isMarkdownPath(path: string): boolean {
  return /\.md$/i.test(path);
}

const EDITABLE = /\.(ya?ml|md|sql|txt|json|py)$/i;

const PROMPT_FILES = ['system_prompt.md', 'soul.md', 'domain_closure.md', 'WORKER_OVERVIEW.md'];

const TAB_LABELS: Record<string, string> = {
  'system_prompt.md': 'Instrucciones de comportamiento',
  'soul.md': 'Tono y personalidad',
  'domain_closure.md': 'Límites del dominio',
  'manifest.yaml': 'Configuración (manifest)',
  'security_policy.yaml': 'Sandbox (política)',
};

export default function TemplateEditorPage() {
  const { workerId } = useParams<{ workerId: string }>();
  const searchParams = useSearchParams();
  const router = useRouter();
  const focusFile = searchParams.get('focus');
  const showCreatedBanner = searchParams.get('created') === '1';
  const { usuario } = useAuthStore();
  const canWrite = usuario?.rol === 'admin';

  const [detail, setDetail] = useState<TemplateDetail | null>(null);
  const [tab, setTab] = useState<string>('system_prompt.md');
  const [content, setContent] = useState('');
  const [markdownView, setMarkdownView] = useState<MarkdownViewMode>('preview');
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [newContextTitle, setNewContextTitle] = useState('');
  const [contextError, setContextError] = useState<string | null>(null);
  const [manifestYaml, setManifestYaml] = useState('');
  const [saving, setSaving] = useState(false);
  const [pendingDeleteContext, setPendingDeleteContext] = useState<{ contextId: string; title: string } | null>(
    null
  );
  const [deletingContext, setDeletingContext] = useState(false);

  const markdownFile = isMarkdownPath(tab);
  const isCatalogWorker = detail?.source === 'catalog' || detail?.read_only === true;
  const canEditFiles = canWrite;

  const { promptFiles, contextFiles, otherFiles } = useMemo(() => {
    if (!detail?.files) {
      return { promptFiles: [] as string[], contextFiles: [] as string[], otherFiles: [] as string[] };
    }
    const all = detail.files.map((f) => f.path).filter((p) => EDITABLE.test(p));
    const prompts = PROMPT_FILES.filter((p) => all.includes(p));
    const promptSet = new Set(prompts);
    const contexts = [...(detail.contexts ?? [])]
      .sort((a, b) => Number(a.sort_order) - Number(b.sort_order))
      .map((ctx) => ctx.title)
      .filter((path) => all.includes(path) && !promptSet.has(path));
    const contextSet = new Set(contexts);
    const rest = all.filter((p) => !promptSet.has(p) && !contextSet.has(p)).sort();
    return { promptFiles: prompts, contextFiles: contexts, otherFiles: rest };
  }, [detail]);

  const load = useCallback((preferredPath?: string) => {
    if (!workerId) return Promise.resolve();
    return adminService
      .getTemplate(workerId)
      .then((d) => {
        setDetail(d);
        const preferred =
          (preferredPath && d.contents[preferredPath] !== undefined && preferredPath) ||
          (focusFile && d.contents[focusFile] !== undefined && focusFile) ||
          (d.contents['system_prompt.md'] !== undefined && 'system_prompt.md') ||
          (d.contents['manifest.yaml'] !== undefined && 'manifest.yaml') ||
          Object.keys(d.contents)[0] ||
          'manifest.yaml';
        setTab(preferred);
        setContent(d.contents[preferred] ?? '');
        setManifestYaml(d.contents['manifest.yaml'] ?? '');
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Error'));
  }, [workerId, focusFile]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!detail) return;
    if (tab === 'manifest.yaml') {
      setContent(manifestYaml);
    } else {
      setContent(detail.contents[tab] ?? '');
    }
    if (!isMarkdownPath(tab)) setMarkdownView('preview');
  }, [tab, detail, manifestYaml]);

  useEffect(() => {
    if (tab === 'manifest.yaml') {
      setManifestYaml(content);
    }
  }, [tab, content]);

  const savedManifestYaml = detail?.contents?.['manifest.yaml'] ?? '';
  const manifestDirty = manifestYaml !== savedManifestYaml;

  const onManifestChange = (nextYaml: string) => {
    setManifestYaml(nextYaml);
    if (tab === 'manifest.yaml') {
      setContent(nextYaml);
    }
  };

  const save = async () => {
    if (!workerId || !canEditFiles) return;
    setMsg(null);
    setError(null);
    setSaving(true);
    try {
      const taskIds: string[] = [];
      const primary = await adminService.saveTemplateFile(workerId, tab, content);
      if (primary.task_id) taskIds.push(primary.task_id);
      if (tab !== 'manifest.yaml' && manifestDirty) {
        const manifest = await adminService.saveTemplateFile(workerId, 'manifest.yaml', manifestYaml);
        if (manifest.task_id) taskIds.push(manifest.task_id);
      }
      for (const taskId of taskIds) {
        const polled = await pollWriteTask(taskId, { intervalMs: 400, maxAttempts: 60 });
        if (polled.state === 'failed') {
          throw new Error(polled.detail || 'Error al persistir en DuckDB');
        }
        if (polled.state === 'timeout' || polled.state === 'not_found') {
          setMsg('Guardado encolado; refresca si no ves los cambios.');
          await load();
          return;
        }
      }
      setMsg(isCatalogWorker ? 'Guardado en catálogo' : 'Guardado en disco (canónico)');
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error al guardar');
    } finally {
      setSaving(false);
    }
  };

  const validate = async () => {
    if (isCatalogWorker) {
      setMsg('Worker leído desde catálogo DB; la validación de manifest en disco no aplica todavía.');
      return;
    }
    if (!workerId) return;
    const r = await adminService.validateTemplate(workerId);
    setMsg(r.ok ? 'Validación OK' : r.errors.join('; '));
  };

  const createContext = async () => {
    if (!workerId || !isCatalogWorker) return;
    if (!newContextTitle.trim()) {
      setContextError('Escribe un nombre para el contexto.');
      return;
    }
    setMsg(null);
    setError(null);
    setContextError(null);
    try {
      const title = newContextTitle.trim().endsWith('.md')
        ? newContextTitle.trim()
        : `${newContextTitle.trim()}.md`;
      await adminService.createTemplateContext(workerId, {
        title,
        content_md: `# ${title.replace(/\\.md$/i, '')}\n\n`,
        sort_order: (detail?.contexts?.length ?? 0) * 10 + 100,
      });
      setNewContextTitle('');
      setTab(title);
      setMsg('Contexto creado en DuckDB');
      await load(title);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error creando contexto');
    }
  };

  const requestDeleteContext = () => {
    if (!isCatalogWorker || !tab) return;
    const ctx = detail?.contexts?.find((item) => item.title === tab);
    if (!ctx) return;
    setPendingDeleteContext({ contextId: ctx.context_id, title: ctx.title });
  };

  const confirmDeleteContext = async () => {
    if (!workerId || !pendingDeleteContext) return;
    setMsg(null);
    setError(null);
    setDeletingContext(true);
    try {
      await adminService.deleteTemplateContext(workerId, pendingDeleteContext.contextId);
      setPendingDeleteContext(null);
      setMsg('Contexto eliminado');
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error eliminando contexto');
    } finally {
      setDeletingContext(false);
    }
  };

  if (!workerId) return null;

  const isContextTab = Boolean(detail?.contexts?.some((item) => item.title === tab));

  return (
    <div className="space-y-6">
      <header className="space-y-3">
        <nav className="flex flex-wrap items-center gap-2 text-sm text-gov-gray-500 dark:text-dark-muted">
          <Link href="/templates" className="hover:text-gov-blue-700 dark:hover:text-dark-cyan">
            Workers
          </Link>
          <ChevronRight size={14} />
          <span className="font-mono text-gov-gray-900 dark:text-dark-text">{workerId}</span>
          <span className="rounded-full bg-gov-cyan-100 px-2 py-0.5 text-[10px] font-black uppercase text-gov-blue-800 dark:bg-dark-bg dark:text-dark-cyan">
            {isCatalogWorker ? 'catálogo DB' : 'canónico (archivo)'}
          </span>
        </nav>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <WorkerDisplayNameEditor
            workerId={workerId}
            displayName={detail?.display_name || workerId}
            canEdit={canEditFiles && isCatalogWorker}
            onSaved={(next) => {
              setDetail((prev) => (prev ? { ...prev, display_name: next } : prev));
              setMsg('Nombre actualizado.');
            }}
          />
          <div className="flex flex-wrap gap-2">
            {!isCatalogWorker && (
              <button
                type="button"
                onClick={validate}
                className="rounded-xl border px-3 py-2 text-sm dark:border-dark-border"
              >
                Validar manifest
              </button>
            )}
            {canEditFiles && (
              <button
                type="button"
                onClick={save}
                disabled={saving}
                className="inline-flex items-center gap-2 rounded-xl bg-gov-blue-700 px-4 py-2 text-sm font-bold text-white disabled:opacity-60"
              >
                {saving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
                {saving ? 'Guardando…' : 'Guardar'}
              </button>
            )}
          </div>
        </div>
      </header>

      {showCreatedBanner && workerId && (
        <AgentOnboardingBanner
          workerId={workerId}
          onDismiss={() => router.replace(`/templates/${encodeURIComponent(workerId)}`, { scroll: false })}
        />
      )}

      {msg && (
        <p className="flex items-center gap-1 text-sm text-green-700 dark:text-green-300">
          <CheckCircle size={16} /> {msg}
        </p>
      )}
      {error && <p className="text-sm text-red-600 dark:text-red-300">{error}</p>}

      <div className="grid gap-6 lg:grid-cols-12">
        <div className="lg:col-span-3">
          <aside className="space-y-3 rounded-2xl border border-gov-gray-100 bg-white p-3 dark:border-dark-border dark:bg-dark-surface lg:sticky lg:top-4 lg:max-h-[calc(100vh-8rem)] lg:overflow-y-auto">
            {isCatalogWorker && canWrite && (
              <CatalogContextTools
                title={newContextTitle}
                error={contextError}
                onTitleChange={(value) => {
                  setNewContextTitle(value);
                  setContextError(null);
                }}
                onCreate={createContext}
                onRequestDelete={requestDeleteContext}
                canDelete={isContextTab}
              />
            )}
            <FileGroup
              title="Comportamiento"
              files={promptFiles}
              tab={tab}
              onSelect={setTab}
              emptyHint="Sin system_prompt.md — vuelve a crear el agente o añade el archivo aquí."
            />
            {isCatalogWorker && (
              <FileGroup
                title="Contextos DB"
                files={contextFiles}
                tab={tab}
                onSelect={setTab}
                emptyHint="Sin contextos Markdown asociados todavía."
              />
            )}
            <FileGroup title="Config y datos" files={otherFiles} tab={tab} onSelect={setTab} />
          </aside>
        </div>

        <div className="min-w-0 space-y-4 lg:col-span-9">
          <WorkerCapabilitiesCard
            workerId={workerId}
            manifestYaml={manifestYaml}
            manifestDirty={manifestDirty}
            canEdit={canEditFiles}
            refreshKey={msg}
            onOpenManifest={() => setTab('manifest.yaml')}
          />

          <section className="space-y-3 rounded-2xl border border-gov-gray-100 bg-white p-4 dark:border-dark-border dark:bg-dark-surface">
            <div>
              <h2 className="text-sm font-black text-gov-gray-900 dark:text-dark-text">
                {TAB_LABELS[tab] ?? tab}
              </h2>
              <p className="mt-0.5 font-mono text-[11px] text-gov-gray-400 dark:text-dark-muted">{tab}</p>
            </div>

            {tab === 'manifest.yaml' && (
              <ManifestGuidedPanel yaml={content} onChange={setContent} disabled={!canEditFiles} />
            )}
            {tab === 'security_policy.yaml' && <SecurityPolicyInfoPanel />}
            {markdownFile && (
              <MarkdownViewToggle mode={markdownView} onChange={setMarkdownView} />
            )}
            {tab !== 'manifest.yaml' && tab !== 'security_policy.yaml' && (
              <TemplateFileEditor
                content={content}
                onChange={setContent}
                readOnly={!canEditFiles}
                markdownFile={markdownFile}
                viewMode={markdownView}
              />
            )}
          </section>
        </div>
      </div>

      <ConfirmDangerModal
        isOpen={Boolean(pendingDeleteContext)}
        title="Eliminar contexto"
        description="Se quitará este archivo de contexto del worker. No afecta system_prompt ni soul."
        confirmLabel="Sí, eliminar contexto"
        isLoading={deletingContext}
        details={
          pendingDeleteContext
            ? [
                { label: 'Archivo', value: pendingDeleteContext.title },
                { label: 'Worker', value: workerId },
              ]
            : []
        }
        onCancel={() => !deletingContext && setPendingDeleteContext(null)}
        onConfirm={() => void confirmDeleteContext()}
      />
    </div>
  );
}

function CatalogContextTools({
  title,
  error,
  canDelete,
  onTitleChange,
  onCreate,
  onRequestDelete,
}: {
  title: string;
  error: string | null;
  canDelete: boolean;
  onTitleChange: (v: string) => void;
  onCreate: () => void;
  onRequestDelete: () => void;
}) {
  return (
    <div className="mb-3 rounded-xl border border-gov-blue-100 bg-white p-2 dark:border-dark-border dark:bg-dark-surface">
      <p className="px-1 text-[10px] font-black uppercase text-gov-blue-700 dark:text-dark-cyan">
        Nuevo contexto
      </p>
      <input
        value={title}
        onChange={(e) => onTitleChange(e.target.value)}
        placeholder="nuevo_contexto.md"
        className="mt-2 w-full rounded-lg border px-2 py-1.5 text-[11px] dark:border-dark-border dark:bg-dark-bg"
      />
      {error && <p className="mt-1 px-1 text-[10px] font-semibold text-red-600">{error}</p>}
      <button
        type="button"
        onClick={onCreate}
        disabled={!title.trim()}
        className="mt-2 flex w-full items-center justify-center gap-1 rounded-lg bg-gov-blue-700 px-2 py-1.5 text-[11px] font-black text-white disabled:opacity-50"
      >
        <Plus size={12} /> Añadir contexto
      </button>
      {canDelete ? (
        <button
          type="button"
          onClick={onRequestDelete}
          className="mt-2 flex w-full items-center justify-center gap-1 rounded-lg border border-red-200 px-2 py-1.5 text-[11px] font-bold text-red-700 hover:bg-red-50 dark:border-red-900/50 dark:text-red-300 dark:hover:bg-red-950/30"
        >
          <Trash2 size={12} />
          Eliminar contexto seleccionado
        </button>
      ) : null}
    </div>
  );
}

function MarkdownViewToggle({
  mode,
  onChange,
}: {
  mode: MarkdownViewMode;
  onChange: (m: MarkdownViewMode) => void;
}) {
  const btn = (id: MarkdownViewMode, label: string, icon: ReactNode) => (
    <button
      type="button"
      onClick={() => onChange(id)}
      className={`flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs ${
        mode === id
          ? 'border-gov-blue-700 bg-gov-blue-700 text-white'
          : 'dark:border-dark-border hover:bg-gov-gray-50 dark:hover:bg-dark-surface'
      }`}
    >
      {icon}
      {label}
    </button>
  );
  return (
    <div className="flex flex-wrap gap-2" role="tablist" aria-label="Vista del archivo Markdown">
      {btn('preview', 'Vista previa', <Eye size={14} />)}
      {btn('edit', 'Markdown', <FileCode size={14} />)}
    </div>
  );
}

const editorTextareaClass =
  'w-full min-h-[420px] font-mono text-sm p-4 rounded-2xl border dark:border-dark-border dark:bg-dark-surface leading-relaxed';

function TemplateFileEditor({
  content,
  onChange,
  readOnly,
  markdownFile,
  viewMode,
}: {
  content: string;
  onChange: (v: string) => void;
  readOnly: boolean;
  markdownFile: boolean;
  viewMode: MarkdownViewMode;
}) {
  if (!markdownFile || viewMode === 'edit') {
    return (
      <textarea
        value={content}
        onChange={(e) => onChange(e.target.value)}
        readOnly={readOnly}
        className={editorTextareaClass}
        spellCheck={false}
      />
    );
  }

  if (viewMode === 'preview') {
    return (
      <div
        className="min-h-[420px] w-full overflow-y-auto rounded-2xl border bg-white p-4 dark:border-dark-border dark:bg-dark-bg"
        aria-label="Vista previa Markdown"
      >
        {content.trim() ? (
          <ChatMarkdown content={content} className="text-sm" />
        ) : (
          <p className="text-sm italic text-gov-gray-400 dark:text-dark-muted">Sin contenido</p>
        )}
      </div>
    );
  }

  return (
    <textarea
      value={content}
      onChange={(e) => onChange(e.target.value)}
      readOnly={readOnly}
      className={editorTextareaClass}
      spellCheck={false}
      aria-label="Editor Markdown"
    />
  );
}

function FileGroup({
  title,
  files,
  tab,
  onSelect,
  emptyHint,
}: {
  title: string;
  files: string[];
  tab: string;
  onSelect: (f: string) => void;
  emptyHint?: string;
}) {
  return (
    <div className="mb-3">
      <p className="text-[10px] font-bold uppercase text-gov-gray-500 px-2 py-1">{title}</p>
      {files.length === 0 && emptyHint ? (
        <p className="text-[10px] text-gov-gray-400 px-2 py-1">{emptyHint}</p>
      ) : null}
      {files.map((f) => (
        <button
          key={f}
          type="button"
          onClick={() => onSelect(f)}
          className={`block w-full text-left text-xs font-mono px-2 py-1.5 rounded-lg truncate ${
            tab === f
              ? 'bg-gov-blue-700 text-white'
              : 'hover:bg-white dark:hover:bg-dark-surface'
          }`}
        >
          {f}
        </button>
      ))}
    </div>
  );
}
