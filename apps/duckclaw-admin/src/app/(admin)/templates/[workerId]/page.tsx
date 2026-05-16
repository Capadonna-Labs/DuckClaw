'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { adminService } from '@/services/adminService';
import type { TemplateDetail } from '@/types/admin';
import { useAuthStore } from '@/store/authStore';
import { ChevronRight, Save, CheckCircle } from 'lucide-react';

const TABS = ['manifest.yaml', 'system_prompt.md', 'soul.md', 'domain_closure.md'] as const;

export default function TemplateEditorPage() {
  const { workerId } = useParams<{ workerId: string }>();
  const { usuario } = useAuthStore();
  const canWrite = usuario?.rol === 'admin';

  const [detail, setDetail] = useState<TemplateDetail | null>(null);
  const [tab, setTab] = useState<string>('system_prompt.md');
  const [content, setContent] = useState('');
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!workerId) return;
    adminService
      .getTemplate(workerId)
      .then((d) => {
        setDetail(d);
        const initial = d.contents['system_prompt.md'] ?? d.contents['manifest.yaml'] ?? '';
        setTab(d.contents['system_prompt.md'] ? 'system_prompt.md' : 'manifest.yaml');
        setContent(initial);
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
      setMsg('Guardado');
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

      <div className="flex flex-wrap gap-2 border-b dark:border-dark-border pb-2">
        {TABS.map((f) => (
          <button
            key={f}
            type="button"
            onClick={() => setTab(f)}
            className={`px-3 py-1.5 text-xs font-bold rounded-lg ${
              tab === f
                ? 'bg-gov-blue-700 text-white'
                : 'bg-gov-gray-100 dark:bg-dark-bg text-gov-gray-600'
            }`}
          >
            {f}
          </button>
        ))}
      </div>

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
  );
}
