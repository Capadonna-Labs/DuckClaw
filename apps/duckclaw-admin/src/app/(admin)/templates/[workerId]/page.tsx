'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useParams, useSearchParams } from 'next/navigation';
import { adminService } from '@/services/adminService';
import type { TemplateDetail } from '@/types/admin';
import { useAuthStore } from '@/store/authStore';
import { ChevronRight, Save, CheckCircle } from 'lucide-react';
import { TemplateVaultPanel } from '@/components/templates/TemplateVaultPanel';

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
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { promptFiles, otherFiles } = useMemo(() => {
    if (!detail?.files) return { promptFiles: [] as string[], otherFiles: [] as string[] };
    const all = detail.files.map((f) => f.path).filter((p) => EDITABLE.test(p));
    const prompts = PROMPT_FILES.filter((p) => all.includes(p));
    const rest = all.filter((p) => !PROMPT_FILES.includes(p)).sort();
    return { promptFiles: prompts, otherFiles: rest };
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
  }, [tab, detail]);

  const save = async () => {
    if (!workerId || !canWrite) return;
    setMsg(null);
    try {
      await adminService.saveTemplateFile(workerId, tab, content);
      setMsg('Guardado en disco (canónico)');
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error al guardar');
    }
  };

  const validate = async () => {
    if (!workerId) return;
    const r = await adminService.validateTemplate(workerId);
    setMsg(r.ok ? 'Validación OK' : r.errors.join('; '));
  };

  if (!workerId) return null;

  return (
    <div className="space-y-4">
      <nav className="flex items-center gap-2 text-sm text-gov-gray-500">
        <Link href="/templates" className="hover:text-gov-blue-700">
          Plantillas
        </Link>
        <ChevronRight size={14} />
        <span className="font-mono text-gov-gray-900 dark:text-dark-text">{workerId}</span>
        <span className="text-[10px] uppercase px-2 py-0.5 rounded bg-gov-cyan-100 text-gov-blue-800 dark:bg-dark-bg">
          canónico (archivo)
        </span>
      </nav>

      <header className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-2xl font-black dark:text-dark-text">{workerId}</h1>
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
          {canWrite && (
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
          <FileGroup
            title="Comportamiento"
            files={promptFiles}
            tab={tab}
            onSelect={setTab}
            emptyHint="Sin system_prompt.md — vuelve a crear el agente o añade el archivo aquí."
          />
          <FileGroup title="Config y datos" files={otherFiles} tab={tab} onSelect={setTab} />
          <TemplateVaultPanel workerId={workerId} canWrite={canWrite} />
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
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            readOnly={!canWrite}
            className="w-full min-h-[420px] font-mono text-sm p-4 rounded-2xl border dark:border-dark-border dark:bg-dark-surface leading-relaxed"
            spellCheck={false}
          />
        </div>
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
