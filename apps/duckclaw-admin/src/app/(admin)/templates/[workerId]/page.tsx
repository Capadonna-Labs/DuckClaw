'use client';

import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import Link from 'next/link';
import { useParams, useSearchParams } from 'next/navigation';
import { adminService } from '@/services/adminService';
import type { TemplateDetail } from '@/types/admin';
import { useAuthStore } from '@/store/authStore';
import { ChevronRight, Save, CheckCircle, Eye, FileCode, Columns2, Plus, Trash2, ArrowUp, ArrowDown } from 'lucide-react';
import { ChatMarkdown } from '@/components/chat/ChatMarkdown';

type MarkdownViewMode = 'edit' | 'preview' | 'split';

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
};

export default function TemplateEditorPage() {
  const { workerId } = useParams<{ workerId: string }>();
  const searchParams = useSearchParams();
  const focusFile = searchParams.get('focus');
  const { usuario } = useAuthStore();
  const canWrite = usuario?.rol === 'admin';

  const [detail, setDetail] = useState<TemplateDetail | null>(null);
  const [tab, setTab] = useState<string>('system_prompt.md');
  const [content, setContent] = useState('');
  const [markdownView, setMarkdownView] = useState<MarkdownViewMode>('edit');
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [newContextTitle, setNewContextTitle] = useState('');

  const markdownFile = isMarkdownPath(tab);
  const isCatalogWorker = detail?.source === 'catalog' || detail?.read_only === true;
  const canEditFiles = canWrite;

  const { promptFiles, contextFiles, otherFiles } = useMemo(() => {
    if (!detail?.files) {
      return { promptFiles: [] as string[], contextFiles: [] as string[], otherFiles: [] as string[] };
    }
    const all = detail.files.map((f) => f.path).filter((p) => EDITABLE.test(p));
    const contexts = [...(detail.contexts ?? [])]
      .sort((a, b) => Number(a.sort_order) - Number(b.sort_order))
      .map((ctx) => ctx.title)
      .filter((path) => all.includes(path));
    const contextSet = new Set(contexts);
    const prompts = PROMPT_FILES.filter((p) => all.includes(p));
    const promptSet = new Set(prompts);
    const rest = all.filter((p) => !promptSet.has(p) && !contextSet.has(p)).sort();
    return { promptFiles: prompts, contextFiles: contexts, otherFiles: rest };
  }, [detail]);

  const load = useCallback(() => {
    if (!workerId) return;
    adminService
      .getTemplate(workerId)
      .then((d) => {
        setDetail(d);
        const preferred =
          (focusFile && d.contents[focusFile] !== undefined && focusFile) ||
          (d.contents['system_prompt.md'] !== undefined && 'system_prompt.md') ||
          (d.contents['manifest.yaml'] !== undefined && 'manifest.yaml') ||
          Object.keys(d.contents)[0] ||
          'manifest.yaml';
        setTab(preferred);
        setContent(d.contents[preferred] ?? '');
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Error'));
  }, [workerId, focusFile]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!detail) return;
    setContent(detail.contents[tab] ?? '');
    if (!isMarkdownPath(tab)) setMarkdownView('edit');
  }, [tab, detail]);

  const save = async () => {
    if (!workerId || !canEditFiles) return;
    setMsg(null);
    try {
      await adminService.saveTemplateFile(workerId, tab, content);
      setMsg(isCatalogWorker ? 'Guardado en DuckDB (catálogo)' : 'Guardado en disco (canónico)');
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error al guardar');
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
    if (!workerId || !isCatalogWorker || !newContextTitle.trim()) return;
    setMsg(null);
    setError(null);
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
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error creando contexto');
    }
  };

  const deleteCurrentContext = async () => {
    if (!workerId || !isCatalogWorker || !tab) return;
    const ctx = detail?.contexts?.find((item) => item.title === tab);
    if (!ctx) return;
    setMsg(null);
    setError(null);
    try {
      await adminService.deleteTemplateContext(workerId, ctx.context_id);
      setMsg('Contexto desactivado en DuckDB');
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error eliminando contexto');
    }
  };

  const moveCurrentContext = async (direction: -1 | 1) => {
    if (!workerId || !isCatalogWorker || !detail?.contexts?.length) return;
    const ordered = [...detail.contexts].sort((a, b) => Number(a.sort_order) - Number(b.sort_order));
    const idx = ordered.findIndex((item) => item.title === tab);
    const swapIdx = idx + direction;
    if (idx < 0 || swapIdx < 0 || swapIdx >= ordered.length) return;
    const current = ordered[idx];
    const other = ordered[swapIdx];
    try {
      await adminService.reorderTemplateContexts(workerId, [
        { context_id: current.context_id, sort_order: Number(other.sort_order) },
        { context_id: other.context_id, sort_order: Number(current.sort_order) },
      ]);
      setMsg('Orden actualizado en DuckDB');
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error reordenando contexto');
    }
  };

  if (!workerId) return null;

  return (
    <div className="space-y-4">
      <nav className="flex items-center gap-2 text-sm text-gov-gray-500">
        <Link href="/templates" className="hover:text-gov-blue-700">
          Workers
        </Link>
        <ChevronRight size={14} />
        <span className="font-mono text-gov-gray-900 dark:text-dark-text">{workerId}</span>
        <span className="text-[10px] uppercase px-2 py-0.5 rounded bg-gov-cyan-100 text-gov-blue-800 dark:bg-dark-bg">
          {isCatalogWorker ? 'catálogo DB' : 'canónico (archivo)'}
        </span>
      </nav>

      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-black dark:text-dark-text">
            {detail?.display_name || workerId}
          </h1>
          {isCatalogWorker && (
            <p className="mt-1 text-xs text-gov-gray-500 dark:text-dark-muted">
              Snapshot importado desde DuckDB. Los cambios se versionan en el catálogo y no modifican
              carpetas de templates.
            </p>
          )}
        </div>
        <div className="flex gap-2 flex-wrap">
          <Link
            href={`/playground?worker=${encodeURIComponent(workerId)}`}
            className="px-3 py-2 text-sm border rounded-xl dark:border-dark-border text-gov-blue-700 font-semibold"
          >
            Probar en Playground
          </Link>
          <button
            type="button"
            onClick={validate}
            className="px-3 py-2 text-sm border rounded-xl dark:border-dark-border"
          >
            Validar
          </button>
          {canEditFiles && (
            <button
              type="button"
              onClick={save}
              className="px-4 py-2 text-sm bg-gov-blue-700 text-white rounded-xl flex items-center gap-2"
            >
              <Save size={16} /> Guardar
            </button>
          )}
        </div>
      </header>

      <div className="flex flex-col lg:flex-row gap-4">
        <aside className="lg:w-56 shrink-0 max-h-48 lg:max-h-[520px] overflow-y-auto rounded-xl border dark:border-dark-border p-2 bg-gov-gray-50 dark:bg-dark-bg">
          {isCatalogWorker && canWrite && (
            <CatalogContextTools
              title={newContextTitle}
              onTitleChange={setNewContextTitle}
              onCreate={createContext}
              onMoveUp={() => moveCurrentContext(-1)}
              onMoveDown={() => moveCurrentContext(1)}
              onDelete={deleteCurrentContext}
              canDelete={!!detail?.contexts?.some((item) => item.title === tab)}
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
          <p className="text-[10px] text-gov-gray-500 px-2 py-2 border-t dark:border-dark-border mt-2">
            La bóveda DuckDB se elige por conversación en Playground o en el chat flotante, no por
            worker.
          </p>
        </aside>

        <div className="flex-1 min-w-0 space-y-2">
          <p className="text-sm font-bold text-gov-gray-700 dark:text-dark-text">
            {TAB_LABELS[tab] ?? tab}
          </p>
          <p className="text-[10px] font-mono text-gov-gray-400">{tab}</p>
          {msg && (
            <p className="text-sm text-green-700 flex items-center gap-1">
              <CheckCircle size={16} /> {msg}
            </p>
          )}
          {error && <p className="text-sm text-red-600">{error}</p>}
          {markdownFile && (
            <MarkdownViewToggle
              mode={markdownView}
              canSplit={canWrite}
              onChange={setMarkdownView}
            />
          )}
          <TemplateFileEditor
            content={content}
            onChange={setContent}
            readOnly={!canEditFiles}
            markdownFile={markdownFile}
            viewMode={markdownView}
          />
        </div>
      </div>
    </div>
  );
}

function CatalogContextTools({
  title,
  canDelete,
  onTitleChange,
  onCreate,
  onMoveUp,
  onMoveDown,
  onDelete,
}: {
  title: string;
  canDelete: boolean;
  onTitleChange: (v: string) => void;
  onCreate: () => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
  onDelete: () => void;
}) {
  return (
    <div className="mb-3 rounded-xl border border-gov-blue-100 bg-white p-2 dark:border-dark-border dark:bg-dark-surface">
      <p className="px-1 text-[10px] font-black uppercase text-gov-blue-700 dark:text-dark-cyan">
        Contextos DB
      </p>
      <input
        value={title}
        onChange={(e) => onTitleChange(e.target.value)}
        placeholder="nuevo_contexto.md"
        className="mt-2 w-full rounded-lg border px-2 py-1.5 text-[11px] dark:border-dark-border dark:bg-dark-bg"
      />
      <button
        type="button"
        onClick={onCreate}
        className="mt-2 flex w-full items-center justify-center gap-1 rounded-lg bg-gov-blue-700 px-2 py-1.5 text-[11px] font-black text-white"
      >
        <Plus size={12} /> Añadir contexto
      </button>
      <div className="mt-2 grid grid-cols-3 gap-1">
        <button type="button" onClick={onMoveUp} className="rounded-lg border px-2 py-1 text-[10px] dark:border-dark-border">
          <ArrowUp size={12} className="mx-auto" />
        </button>
        <button type="button" onClick={onMoveDown} className="rounded-lg border px-2 py-1 text-[10px] dark:border-dark-border">
          <ArrowDown size={12} className="mx-auto" />
        </button>
        <button
          type="button"
          onClick={onDelete}
          disabled={!canDelete}
          className="rounded-lg border px-2 py-1 text-[10px] text-red-600 disabled:opacity-40 dark:border-dark-border"
        >
          <Trash2 size={12} className="mx-auto" />
        </button>
      </div>
    </div>
  );
}

function MarkdownViewToggle({
  mode,
  canSplit,
  onChange,
}: {
  mode: MarkdownViewMode;
  canSplit: boolean;
  onChange: (m: MarkdownViewMode) => void;
}) {
  const btn = (id: MarkdownViewMode, label: string, icon: ReactNode) => (
    <button
      type="button"
      onClick={() => onChange(id)}
      className={`px-3 py-1.5 text-xs rounded-lg border flex items-center gap-1.5 ${
        mode === id
          ? 'bg-gov-blue-700 text-white border-gov-blue-700'
          : 'dark:border-dark-border hover:bg-gov-gray-50 dark:hover:bg-dark-surface'
      }`}
    >
      {icon}
      {label}
    </button>
  );
  return (
    <div className="flex flex-wrap gap-2" role="tablist" aria-label="Vista del archivo Markdown">
      {btn('edit', 'Markdown', <FileCode size={14} />)}
      {btn('preview', 'Vista previa', <Eye size={14} />)}
      {canSplit ? btn('split', 'Dividido', <Columns2 size={14} />) : null}
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
        className="w-full min-h-[420px] p-4 rounded-2xl border dark:border-dark-border bg-white dark:bg-dark-surface overflow-y-auto"
        aria-label="Vista previa Markdown"
      >
        {content.trim() ? (
          <ChatMarkdown content={content} className="text-sm" />
        ) : (
          <p className="text-sm text-gov-gray-400 italic">Sin contenido</p>
        )}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
      <textarea
        value={content}
        onChange={(e) => onChange(e.target.value)}
        readOnly={readOnly}
        className={editorTextareaClass}
        spellCheck={false}
        aria-label="Editor Markdown"
      />
      <div
        className="min-h-[420px] p-4 rounded-2xl border dark:border-dark-border bg-gov-gray-50/80 dark:bg-dark-bg overflow-y-auto"
        aria-label="Vista previa Markdown"
      >
        {content.trim() ? (
          <ChatMarkdown content={content} className="text-sm" />
        ) : (
          <p className="text-sm text-gov-gray-400 italic">La vista previa aparecerá aquí</p>
        )}
      </div>
    </div>
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
