'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { adminService, type ReportInstanceSummary } from '@/services/adminService';

function statusBadge(status: string) {
  const map: Record<string, string> = {
    draft: 'bg-amber-900/50 text-amber-200',
    ready: 'bg-emerald-900/50 text-emerald-200',
    archived: 'bg-slate-700 text-slate-300',
  };
  return map[status] || 'bg-slate-700 text-slate-300';
}

function sectionIcon(sectionStatus: string) {
  if (sectionStatus === 'complete') return '✓';
  if (sectionStatus === 'partial') return '◐';
  return '○';
}

export function DocumentReportsPanel() {
  const [instances, setInstances] = useState<ReportInstanceSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedId, setSelectedId] = useState('');

  const loadInstances = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await adminService.listReportInstances({ limit: 100 });
      setInstances(res.instances);
      setSelectedId((prev) => prev || res.instances[0]?.instance_id || '');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudieron cargar los informes');
      setInstances([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadInstances();
  }, [loadInstances]);

  const selected = useMemo(
    () => instances.find((i) => i.instance_id === selectedId) ?? null,
    [instances, selectedId]
  );

  const previewSrc = selected
    ? `/api/admin/report-instances/${encodeURIComponent(selected.instance_id)}/preview?_t=${Date.now()}`
    : '';

  const playgroundHref = selected?.project_id
    ? `/playground?project=${encodeURIComponent(selected.project_id)}`
    : '/playground';

  return (
    <div className="flex h-full w-full overflow-hidden">
      <aside className="flex w-72 shrink-0 flex-col border-r border-slate-800 bg-slate-950">
        <div className="border-b border-slate-800 p-4">
          <h2 className="text-sm font-semibold text-slate-100">Informes Word</h2>
          <p className="mt-1 text-xs text-slate-500">
            Instancias del Report Engine (plantilla .docx + secciones).
          </p>
          <button
            type="button"
            onClick={() => void loadInstances()}
            className="mt-3 text-xs text-sky-400 hover:text-sky-300"
          >
            Actualizar lista
          </button>
        </div>
        <div className="scrollbar-thin min-h-0 flex-1 overflow-y-auto p-2">
          {loading ? (
            <p className="p-3 text-xs text-slate-500">Cargando…</p>
          ) : error ? (
            <p className="p-3 text-xs text-amber-300">{error}</p>
          ) : instances.length === 0 ? (
            <div className="space-y-2 p-3 text-xs text-slate-400">
              <p>Aún no hay informes. En el Chat, con un agente del proyecto:</p>
              <ol className="list-decimal space-y-1 pl-4 text-slate-500">
                <li>
                  <code className="text-slate-300">register_report_template</code> con tu .docx
                </li>
                <li>
                  <code className="text-slate-300">create_report_instance</code>
                </li>
                <li>
                  <code className="text-slate-300">patch_report_section</code> por sección
                </li>
                <li>
                  <code className="text-slate-300">render_report_instance</code>
                </li>
              </ol>
              <Link href="/playground" className="inline-block text-sky-400 hover:underline">
                Ir al Chat →
              </Link>
            </div>
          ) : (
            <ul className="space-y-1">
              {instances.map((item) => (
                <li key={item.instance_id}>
                  <button
                    type="button"
                    onClick={() => setSelectedId(item.instance_id)}
                    className={`w-full rounded-lg px-3 py-2 text-left text-sm transition ${
                      item.instance_id === selectedId
                        ? 'bg-slate-800 text-white'
                        : 'text-slate-300 hover:bg-slate-900'
                    }`}
                  >
                    <div className="truncate font-medium">{item.title}</div>
                    <div className="mt-0.5 flex items-center gap-2 text-[10px] text-slate-500">
                      <span>{item.progress.completion_percent}%</span>
                      {item.period_key ? <span>· {item.period_key}</span> : null}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {selected ? (
          <>
            <header className="flex flex-wrap items-center gap-3 border-b border-slate-800 px-4 py-3">
              <div className="min-w-0 flex-1">
                <h3 className="truncate text-base font-semibold">{selected.title}</h3>
                <p className="text-xs text-slate-500">
                  {selected.template_name || selected.template_id}
                  {selected.period_key ? ` · ${selected.period_key}` : ''}
                </p>
              </div>
              <span
                className={`rounded-full px-2 py-0.5 text-[10px] uppercase tracking-wide ${statusBadge(selected.status)}`}
              >
                {selected.status}
              </span>
              <span className="text-xs text-slate-400">{selected.progress.completion_percent}%</span>
              <Link
                href={playgroundHref}
                className="rounded-md bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500"
              >
                Completar en Chat
              </Link>
            </header>
            <div className="flex min-h-0 flex-1">
              <div className="min-w-0 flex-[3] border-r border-slate-800 bg-white">
                <iframe
                  key={previewSrc}
                  src={previewSrc}
                  title="Vista previa del informe"
                  className="h-full w-full"
                  sandbox="allow-same-origin"
                />
              </div>
              <div className="scrollbar-thin flex w-64 shrink-0 flex-col overflow-y-auto bg-slate-900 p-4">
                <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Secciones
                </h4>
                <ul className="mt-3 space-y-2">
                  {[
                    ...selected.progress.missing_sections,
                    ...selected.progress.partial_sections,
                    ...selected.progress.complete_sections.map((id) => ({
                      id,
                      label: id,
                      status: 'complete',
                    })),
                  ].map((sec) => (
                    <li
                      key={sec.id}
                      className="flex items-start gap-2 text-xs text-slate-300"
                    >
                      <span className="mt-0.5 w-4 shrink-0 text-center text-slate-500">
                        {sectionIcon(sec.status)}
                      </span>
                      <span>{sec.label}</span>
                    </li>
                  ))}
                </ul>
                {selected.rendered_docx_uri ? (
                  <p className="mt-4 break-all text-[10px] text-slate-500">
                    DOCX: {selected.rendered_docx_uri}
                  </p>
                ) : null}
              </div>
            </div>
          </>
        ) : (
          <div className="flex flex-1 items-center justify-center text-sm text-slate-500">
            {loading ? 'Cargando informes…' : 'Selecciona un informe o créalo desde el Chat.'}
          </div>
        )}
      </div>
    </div>
  );
}
