'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { adminService } from '@/services/adminService';
import type { TemplateDetail } from '@/types/admin';
import { useAuthStore } from '@/store/authStore';
import { ChevronRight, Save, CheckCircle } from 'lucide-react';

const EDITABLE = /\.(ya?ml|md|sql|txt|json|py)$/i;

export default function TemplateEditorPage() {
  const { workerId } = useParams<{ workerId: string }>();
  const { usuario } = useAuthStore();
  const canWrite = usuario?.rol === 'admin';

  const [detail, setDetail] = useState<TemplateDetail | null>(null);
  const [tab, setTab] = useState<string>('system_prompt.md');
  const [content, setContent] = useState('');
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const editableFiles = useMemo(() => {
    if (!detail?.files) return [];
    return detail.files
      .map((f) => f.path)
      .filter((p) => EDITABLE.test(p))
      .sort();
  }, [detail]);

  const load = useCallback(() => {
    if (!workerId) return;
    adminService
      .getTemplate(workerId)
      .then((d) => {
        setDetail(d);
        const preferred =
          (d.contents['system_prompt.md'] !== undefined && 'system_prompt.md') ||
          (d.contents['manifest.yaml'] !== undefined && 'manifest.yaml') ||
          Object.keys(d.contents)[0] ||
          'manifest.yaml';
        setTab(preferred);
        setContent(d.contents[preferred] ?? '');
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Error'));
  }, [workerId]);

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
        <div className="flex gap-2">
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
          <p className="text-[10px] font-bold uppercase text-gov-gray-500 px-2 py-1">Archivos</p>
          {editableFiles.map((f) => (
            <button
              key={f}
              type="button"
              onClick={() => setTab(f)}
              className={`block w-full text-left text-xs font-mono px-2 py-1.5 rounded-lg truncate ${
                tab === f
                  ? 'bg-gov-blue-700 text-white'
                  : 'hover:bg-white dark:hover:bg-dark-surface'
              }`}
            >
              {f}
            </button>
          ))}
        </aside>

        <div className="flex-1 min-w-0 space-y-2">
          <p className="text-xs font-mono text-gov-gray-500">{tab}</p>
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
            className="w-full min-h-[420px] font-mono text-sm p-4 rounded-2xl border dark:border-dark-border dark:bg-dark-surface"
            spellCheck={false}
          />
        </div>
      </div>
    </div>
  );
}
