'use client';

import Link from 'next/link';
import { FilePlus2, FolderOpen, Trash2 } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import ConfirmDangerModal from '@/components/admin/ConfirmDangerModal';
import { VaultDocxPicker } from '@/components/reports/VaultDocxPicker';
import {
  adminService,
  type ReportInstanceSummary,
  type ReportTemplateSummary,
} from '@/services/adminService';
import { pollWriteTask } from '@/lib/pollWriteTask';

type TemplateMode = 'registered' | 'vault_path';
type WizardStep = 1 | 2;

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

function hasRenderablePreview(progress: ReportInstanceSummary['progress']): boolean {
  return progress.complete_count + progress.partial_count > 0;
}

type OrderedSection = { id: string; label: string; status: string };

function orderedSections(progress: ReportInstanceSummary['progress']): OrderedSection[] {
  const complete = progress.complete_sections.map((id) => ({
    id,
    label: id,
    status: 'complete',
  }));
  return [...progress.missing_sections, ...progress.partial_sections, ...complete];
}

function buildChatPrompt(instance: ReportInstanceSummary): string {
  return encodeURIComponent(
    `Continúa el documento Word «${instance.title}» (instance_id ${instance.instance_id}). ` +
      `Rellena las secciones pendientes con el contenido que te iré dictando y al final genera el documento Word.`
  );
}

function Field({
  id,
  label,
  hint,
  children,
}: {
  id: string;
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="block text-sm font-medium text-slate-200">
        {label}
      </label>
      {hint ? <p className="text-xs leading-relaxed text-slate-500">{hint}</p> : null}
      {children}
    </div>
  );
}

const inputClass =
  'w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5 text-sm text-slate-100 placeholder:text-slate-600 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500';

function sectionStatusClass(status: string): string {
  if (status === 'complete') return 'text-emerald-400';
  if (status === 'partial') return 'text-amber-400';
  return 'text-slate-500';
}

function SectionsSidebar({
  sections,
  renderedDocxUri,
}: {
  sections: OrderedSection[];
  renderedDocxUri: string;
}) {
  return (
    <div className="scrollbar-thin flex w-64 shrink-0 flex-col overflow-y-auto border-l border-slate-800 bg-slate-900 p-4">
      <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Secciones</h4>
      <ul className="mt-3 space-y-2">
        {sections.map((sec) => (
          <li key={sec.id} className="flex items-start gap-2 text-xs text-slate-300">
            <span
              className={`mt-0.5 w-4 shrink-0 text-center ${sectionStatusClass(sec.status)}`}
            >
              {sectionIcon(sec.status)}
            </span>
            <span>{sec.label}</span>
          </li>
        ))}
      </ul>
      {renderedDocxUri ? (
        <p className="mt-4 break-all text-[10px] text-slate-500">DOCX: {renderedDocxUri}</p>
      ) : null}
    </div>
  );
}

function DraftWorkspace({
  instance,
  playgroundHref,
  sections,
}: {
  instance: ReportInstanceSummary;
  playgroundHref: string;
  sections: OrderedSection[];
}) {
  const pending = instance.progress.missing_count + instance.progress.partial_count;

  return (
    <div className="scrollbar-thin flex min-w-0 flex-1 flex-col overflow-y-auto bg-slate-900/40 p-6">
      <div className="mx-auto w-full max-w-2xl space-y-6">
        <div className="rounded-xl border border-slate-800 bg-slate-950/80 p-5">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Borrador · {instance.progress.completion_percent}%
          </p>
          <h4 className="mt-2 text-lg font-semibold text-slate-100">
            {pending > 0
              ? `${pending} sección${pending === 1 ? '' : 'es'} por rellenar`
              : 'Listo para generar Word'}
          </h4>
          <p className="mt-2 text-sm leading-relaxed text-slate-400">
            La plantilla «{instance.template_name || instance.template_id}» ya está cargada.
            Dicta el contenido en Chat; la vista previa HTML aparece cuando haya al menos una
            sección con texto.
          </p>
          <Link
            href={playgroundHref}
            className="mt-4 inline-flex rounded-md bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500"
          >
            Completar en Chat →
          </Link>
        </div>

        <div>
          <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Checklist ({sections.length})
          </h4>
          <ul className="mt-3 divide-y divide-slate-800 overflow-hidden rounded-xl border border-slate-800 bg-slate-950/60">
            {sections.map((sec) => (
              <li
                key={sec.id}
                className="flex items-center gap-3 px-4 py-2.5 text-sm text-slate-300"
              >
                <span className={`w-4 shrink-0 text-center ${sectionStatusClass(sec.status)}`}>
                  {sectionIcon(sec.status)}
                </span>
                <span className="min-w-0 flex-1 truncate">{sec.label}</span>
                <span className="shrink-0 text-[10px] uppercase tracking-wide text-slate-600">
                  {sec.status === 'complete'
                    ? 'Hecho'
                    : sec.status === 'partial'
                      ? 'Parcial'
                      : 'Pendiente'}
                </span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}

export function DocumentReportsPanel() {
  const [instances, setInstances] = useState<ReportInstanceSummary[]>([]);
  const [templates, setTemplates] = useState<ReportTemplateSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [selectedId, setSelectedId] = useState('');
  const [showWizard, setShowWizard] = useState(false);
  const [wizardStep, setWizardStep] = useState<WizardStep>(1);
  const [busy, setBusy] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<ReportInstanceSummary | null>(null);
  const [pendingDeleteTemplate, setPendingDeleteTemplate] = useState<ReportTemplateSummary | null>(
    null
  );
  const [vaultPickerOpen, setVaultPickerOpen] = useState(false);
  const [showManualPath, setShowManualPath] = useState(false);

  const [templateMode, setTemplateMode] = useState<TemplateMode>('registered');
  const [templatePath, setTemplatePath] = useState('');
  const [templateName, setTemplateName] = useState('');
  const [selectedTemplateId, setSelectedTemplateId] = useState('');
  const [reportTitle, setReportTitle] = useState('');

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [instRes, tplRes] = await Promise.all([
        adminService.listReportInstances({ limit: 100 }),
        adminService.listReportTemplates({ limit: 100 }),
      ]);
      setInstances(instRes.instances);
      setTemplates(tplRes.templates);
      setSelectedId((prev) => {
        if (prev && instRes.instances.some((i) => i.instance_id === prev)) return prev;
        return instRes.instances[0]?.instance_id || '';
      });
      if (tplRes.templates.length > 0) {
        setSelectedTemplateId((prev) => prev || tplRes.templates[0].template_id);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudieron cargar los informes');
      setInstances([]);
      setTemplates([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  useEffect(() => {
    if (templates.length === 0) {
      setTemplateMode('vault_path');
      setSelectedTemplateId('');
    }
  }, [templates.length]);

  const selected = useMemo(
    () => instances.find((i) => i.instance_id === selectedId) ?? null,
    [instances, selectedId]
  );

  const selectedTemplate = useMemo(
    () => templates.find((t) => t.template_id === selectedTemplateId) ?? null,
    [templates, selectedTemplateId]
  );

  const previewSrc = useMemo(() => {
    if (!selected) return '';
    const bust = selected.updated_at || selected.instance_id;
    return `/api/admin/report-instances/${encodeURIComponent(selected.instance_id)}/preview?v=${encodeURIComponent(bust)}`;
  }, [selected]);

  const playgroundHref = selected
    ? `/playground?project=${encodeURIComponent(selected.project_id || '')}&q=${buildChatPrompt(selected)}`
    : '/playground';

  function openWizard() {
    setShowWizard(true);
    setWizardStep(1);
    setError('');
    setNotice('');
    if (templates.length === 0) {
      setTemplateMode('vault_path');
      setSelectedTemplateId('');
    } else {
      setTemplateMode('registered');
      setSelectedTemplateId((prev) => prev || templates[0].template_id);
    }
  }

  function closeWizard() {
    setShowWizard(false);
    setWizardStep(1);
    setTemplatePath('');
    setTemplateName('');
    setReportTitle('');
  }

  async function assertWriteOk(taskId: string, failFallback: string): Promise<void> {
    const polled = await pollWriteTask(taskId, { intervalMs: 400, maxAttempts: 90 });
    if (polled.state === 'success') return;
    if (polled.state === 'failed') {
      throw new Error(polled.detail || failFallback);
    }
    setNotice(
      polled.state === 'timeout'
        ? 'Escritura encolada; confirma en la lista (db-writer puede ir con retardo).'
        : 'No se confirmó el write-task; refresca la lista.'
    );
  }

  function canAdvanceFromStep1(): boolean {
    if (templateMode === 'registered') return Boolean(selectedTemplateId.trim());
    return Boolean(templatePath.trim());
  }

  function canCreate(): boolean {
    return canAdvanceFromStep1() && Boolean(reportTitle.trim());
  }

  async function handleCreateReport() {
    if (!canCreate()) {
      setError('Completa plantilla y título antes de crear.');
      return;
    }
    setBusy(true);
    setError('');
    setNotice('');
    try {
      let templateId = '';
      if (templateMode === 'registered') {
        templateId = selectedTemplateId.trim();
        if (!templateId) {
          throw new Error('Elige una plantilla registrada.');
        }
      } else {
        const path = templatePath.trim();
        if (!path) {
          throw new Error('Indica la ruta del .docx en el vault.');
        }
        const reg = await adminService.registerReportTemplate({
          template_docx_path: path,
          name: templateName.trim() || undefined,
        });
        await assertWriteOk(reg.task_id, 'No se pudo registrar la plantilla');
        templateId = reg.template_id;
        setSelectedTemplateId(templateId);
      }

      const title = reportTitle.trim();
      const created = await adminService.createReportInstance({
        template_id: templateId,
        title,
      });
      await assertWriteOk(created.task_id, 'No se pudo crear el informe');

      setInstances((prev) => {
        if (prev.some((i) => i.instance_id === created.instance_id)) return prev;
        return [
          {
            instance_id: created.instance_id,
            template_id: templateId,
            template_name: selectedTemplate?.name || templateName.trim() || templateId,
            title,
            period_key: '',
            project_id: '',
            status: 'draft',
            preview_html: '',
            rendered_docx_uri: '',
            conversation_id: '',
            updated_at: new Date().toISOString(),
            progress: {
              section_count: 0,
              complete_count: 0,
              partial_count: 0,
              missing_count: 0,
              completion_percent: 0,
              missing_sections: [],
              partial_sections: [],
              complete_sections: [],
            },
          },
          ...prev,
        ];
      });
      closeWizard();
      setNotice(`Informe «${title}» creado. Continúa el contenido en el Chat.`);
      await loadAll();
      setSelectedId(created.instance_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo crear el informe');
    } finally {
      setBusy(false);
    }
  }

  async function confirmDelete() {
    if (!pendingDelete) return;
    setDeleting(true);
    setError('');
    setNotice('');
    const target = pendingDelete;
    try {
      const res = await adminService.deleteReportInstance(target.instance_id);
      await assertWriteOk(res.task_id, 'No se pudo eliminar el informe');
      setInstances((prev) => prev.filter((i) => i.instance_id !== target.instance_id));
      setSelectedId((prev) => (prev === target.instance_id ? '' : prev));
      setPendingDelete(null);
      setNotice(`Informe «${target.title}» eliminado.`);
      await loadAll();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo eliminar el informe');
    } finally {
      setDeleting(false);
    }
  }

  async function confirmDeleteTemplate() {
    if (!pendingDeleteTemplate) return;
    setDeleting(true);
    setError('');
    setNotice('');
    const target = pendingDeleteTemplate;
    try {
      const res = await adminService.deleteReportTemplate(target.template_id);
      await assertWriteOk(res.task_id, 'No se pudo eliminar la plantilla');
      setTemplates((prev) => prev.filter((t) => t.template_id !== target.template_id));
      setSelectedTemplateId((prev) => (prev === target.template_id ? '' : prev));
      setPendingDeleteTemplate(null);
      setNotice(
        `Plantilla «${target.name}» eliminada. Sus informes asociados de tu usuario también se archivaron.`
      );
      await loadAll();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo eliminar la plantilla');
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="flex h-full w-full overflow-hidden">
      <aside className="flex w-72 shrink-0 flex-col border-r border-slate-800 bg-slate-950">
        <div className="border-b border-slate-800 p-4">
          <h2 className="text-sm font-semibold text-slate-100">Informes Word</h2>
          <p className="mt-1 text-xs text-slate-500">
            Plantilla → nombre → secciones en Chat → Word final.
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={openWizard}
              className="rounded-md bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500"
            >
              Nuevo informe
            </button>
            <button
              type="button"
              onClick={() => void loadAll()}
              className="text-xs text-sky-400 hover:text-sky-300"
            >
              Actualizar
            </button>
          </div>
        </div>
        <div className="scrollbar-thin min-h-0 flex-1 overflow-y-auto p-2">
          {loading ? (
            <p className="p-3 text-xs text-slate-500">Cargando…</p>
          ) : error && instances.length === 0 ? (
            <p className="p-3 text-xs text-amber-300">{error}</p>
          ) : instances.length === 0 ? (
            <div className="space-y-3 p-3 text-xs text-slate-400">
              <p className="font-medium text-slate-200">Aún no hay informes</p>
              <p>
                Crea uno con <span className="font-semibold text-slate-300">Nuevo informe</span>: elige
                plantilla registrada o registra un .docx del vault.
              </p>
            </div>
          ) : (
            <ul className="space-y-1">
              {instances.map((item) => {
                const isActive = item.instance_id === selectedId;
                return (
                  <li key={item.instance_id} className="group relative">
                    <button
                      type="button"
                      onClick={() => {
                        setSelectedId(item.instance_id);
                        setShowWizard(false);
                      }}
                      className={`w-full rounded-lg px-3 py-2 pr-9 text-left text-sm transition ${
                        isActive
                          ? 'bg-slate-800 text-white'
                          : 'text-slate-300 hover:bg-slate-900'
                      }`}
                    >
                      <div className="truncate font-medium">{item.title}</div>
                      <div className="mt-0.5 text-[10px] text-slate-500">
                        {item.progress.completion_percent}% · {item.template_name || item.template_id}
                      </div>
                    </button>
                    <button
                      type="button"
                      title="Eliminar informe"
                      aria-label={`Eliminar ${item.title}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        setPendingDelete(item);
                      }}
                      className={`absolute right-1.5 top-1.5 rounded-md p-1.5 text-slate-500 transition hover:bg-red-950/60 hover:text-red-300 ${
                        isActive ? 'opacity-100' : 'opacity-0 group-hover:opacity-100 focus:opacity-100'
                      }`}
                    >
                      <Trash2 size={14} />
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
        {templates.length > 0 ? (
          <div className="border-t border-slate-800 p-3">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
              Plantillas ({templates.length})
            </p>
            <ul className="mt-2 max-h-36 space-y-1 overflow-y-auto">
              {templates.map((tpl) => (
                <li
                  key={tpl.template_id}
                  className="group flex items-start gap-1 rounded-md px-1 py-1 hover:bg-slate-900"
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[11px] text-slate-300">{tpl.name}</p>
                    <p className="truncate text-[10px] text-slate-600">
                      {tpl.section_schema?.length || 0} sec. · {tpl.template_id}
                    </p>
                  </div>
                  <button
                    type="button"
                    title="Eliminar plantilla"
                    aria-label={`Eliminar plantilla ${tpl.name}`}
                    onClick={() => setPendingDeleteTemplate(tpl)}
                    className="rounded p-1 text-slate-600 opacity-70 hover:bg-red-950/50 hover:text-red-300 group-hover:opacity-100"
                  >
                    <Trash2 size={12} />
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {showWizard ? (
          <div className="scrollbar-thin flex-1 overflow-y-auto p-6">
            <div className="max-w-xl space-y-6">
              <div>
                <h3 className="text-base font-semibold text-slate-100">Nuevo informe</h3>
                <p className="mt-1 text-sm text-slate-400">
                  Paso {wizardStep} de 2 —{' '}
                  {wizardStep === 1 ? 'elige la plantilla' : 'nombre del documento'}
                </p>
                <ol className="mt-4 flex gap-2 text-xs">
                  <li
                    className={`rounded-full px-3 py-1 ${
                      wizardStep === 1
                        ? 'bg-sky-600 text-white'
                        : 'bg-slate-800 text-slate-300'
                    }`}
                  >
                    1. Plantilla
                  </li>
                  <li
                    className={`rounded-full px-3 py-1 ${
                      wizardStep === 2
                        ? 'bg-sky-600 text-white'
                        : 'bg-slate-800 text-slate-500'
                    }`}
                  >
                    2. Nombre
                  </li>
                </ol>
              </div>

              {error ? (
                <p className="rounded-md border border-amber-800/60 bg-amber-950/40 px-3 py-2 text-sm text-amber-200">
                  {error}
                </p>
              ) : null}
              {notice ? <p className="text-sm text-emerald-300">{notice}</p> : null}

              {wizardStep === 1 ? (
                <div className="space-y-5">
                  <div className="grid gap-3 sm:grid-cols-2">
                    <button
                      type="button"
                      disabled={templates.length === 0}
                      onClick={() => {
                        setTemplateMode('registered');
                        setTemplatePath('');
                        if (!selectedTemplateId && templates[0]) {
                          setSelectedTemplateId(templates[0].template_id);
                        }
                      }}
                      className={`rounded-xl border p-4 text-left transition ${
                        templateMode === 'registered'
                          ? 'border-sky-500 bg-sky-950/40 ring-1 ring-sky-500/40'
                          : 'border-slate-700 bg-slate-900/50 hover:border-slate-600'
                      } disabled:cursor-not-allowed disabled:opacity-40`}
                    >
                      <FolderOpen className="mb-2 text-sky-400" size={18} />
                      <div className="text-sm font-semibold text-slate-100">Ya registrada</div>
                      <p className="mt-1 text-xs text-slate-500">
                        {templates.length > 0
                          ? `${templates.length} plantilla(s) disponibles`
                          : 'Todavía no hay ninguna — usa la otra opción'}
                      </p>
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setTemplateMode('vault_path');
                        setSelectedTemplateId('');
                      }}
                      className={`rounded-xl border p-4 text-left transition ${
                        templateMode === 'vault_path'
                          ? 'border-sky-500 bg-sky-950/40 ring-1 ring-sky-500/40'
                          : 'border-slate-700 bg-slate-900/50 hover:border-slate-600'
                      }`}
                    >
                      <FilePlus2 className="mb-2 text-sky-400" size={18} />
                      <div className="text-sm font-semibold text-slate-100">Desde el vault</div>
                      <p className="mt-1 text-xs text-slate-500">
                        Registra un .docx por ruta relativa y crea el informe
                      </p>
                    </button>
                  </div>

                  {templateMode === 'registered' ? (
                    <Field
                      id="report-template-select"
                      label="Plantilla"
                      hint="Solo plantillas que ya analizaste y guardaste en el sistema."
                    >
                      <select
                        id="report-template-select"
                        className={inputClass}
                        value={selectedTemplateId}
                        onChange={(e) => setSelectedTemplateId(e.target.value)}
                      >
                        {templates.map((tpl) => (
                          <option key={tpl.template_id} value={tpl.template_id}>
                            {tpl.name} ({tpl.section_schema?.length || 0} secciones)
                          </option>
                        ))}
                      </select>
                      {selectedTemplate?.template_uri ? (
                        <p className="mt-2 break-all font-mono text-[11px] text-slate-500">
                          {selectedTemplate.template_uri}
                        </p>
                      ) : null}
                    </Field>
                  ) : (
                    <div className="space-y-4">
                      <div className="rounded-xl border border-slate-700 bg-slate-900/60 p-4">
                        <p className="text-sm font-medium text-slate-200">Plantilla Word del vault</p>
                        <p className="mt-1 text-xs text-slate-500">
                          Navega las carpetas permitidas y elige un .docx. No hace falta memorizar la ruta.
                        </p>
                        {templatePath.trim() ? (
                          <p className="mt-3 break-all rounded-lg border border-emerald-900/50 bg-emerald-950/30 px-3 py-2 font-mono text-[11px] text-emerald-200">
                            {templatePath}
                          </p>
                        ) : (
                          <p className="mt-3 text-xs text-amber-300/90">Aún no has elegido ningún archivo.</p>
                        )}
                        <button
                          type="button"
                          onClick={() => setVaultPickerOpen(true)}
                          className="mt-3 rounded-md bg-sky-600 px-3 py-2 text-sm font-medium text-white hover:bg-sky-500"
                        >
                          {templatePath.trim() ? 'Cambiar .docx…' : 'Elegir .docx del vault…'}
                        </button>
                      </div>
                      <Field
                        id="report-template-name"
                        label="Nombre de la plantilla"
                        hint="Opcional. Si lo dejas vacío se usa el nombre del archivo."
                      >
                        <input
                          id="report-template-name"
                          className={inputClass}
                          value={templateName}
                          onChange={(e) => setTemplateName(e.target.value)}
                          autoComplete="off"
                        />
                      </Field>
                      <div>
                        <button
                          type="button"
                          onClick={() => setShowManualPath((v) => !v)}
                          className="text-xs text-slate-500 underline hover:text-slate-300"
                        >
                          {showManualPath ? 'Ocultar ruta manual' : 'Pegar ruta a mano (avanzado)'}
                        </button>
                        {showManualPath ? (
                          <div className="mt-2">
                            <Field
                              id="report-template-path"
                              label="Ruta del .docx"
                              hint="Absoluta bajo ALLOWED_ROOTS o relativa al vault."
                            >
                              <input
                                id="report-template-path"
                                className={inputClass}
                                placeholder="Alcaldia/.../INFORME.docx"
                                value={templatePath}
                                onChange={(e) => setTemplatePath(e.target.value)}
                                autoComplete="off"
                              />
                            </Field>
                          </div>
                        ) : null}
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2 text-xs text-slate-400">
                    Plantilla:{' '}
                    <span className="font-medium text-slate-200">
                      {templateMode === 'registered'
                        ? selectedTemplate?.name || selectedTemplateId
                        : templatePath.trim() || '—'}
                    </span>
                  </div>
                  <Field
                    id="report-title"
                    label="Nombre del documento"
                    hint="Obligatorio. Las secciones las define la plantilla; tú las rellenas después en Chat."
                  >
                    <input
                      id="report-title"
                      className={inputClass}
                      placeholder="Informe mensual — julio 2026"
                      value={reportTitle}
                      onChange={(e) => setReportTitle(e.target.value)}
                      autoComplete="off"
                    />
                  </Field>
                </div>
              )}

              <div className="flex flex-wrap items-center gap-3 border-t border-slate-800 pt-4">
                {wizardStep === 1 ? (
                  <>
                    <button
                      type="button"
                      disabled={!canAdvanceFromStep1()}
                      onClick={() => {
                        setError('');
                        setWizardStep(2);
                      }}
                      className="rounded-md bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-40"
                    >
                      Continuar
                    </button>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={closeWizard}
                      className="rounded-md px-4 py-2 text-sm text-slate-400 hover:text-slate-200"
                    >
                      Cancelar
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      type="button"
                      disabled={busy || !canCreate()}
                      onClick={() => void handleCreateReport()}
                      className="rounded-md bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
                    >
                      {busy ? 'Creando…' : 'Crear informe'}
                    </button>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => setWizardStep(1)}
                      className="rounded-md px-4 py-2 text-sm text-slate-400 hover:text-slate-200"
                    >
                      Atrás
                    </button>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={closeWizard}
                      className="rounded-md px-4 py-2 text-sm text-slate-500 hover:text-slate-300"
                    >
                      Cancelar
                    </button>
                  </>
                )}
              </div>
            </div>
          </div>
        ) : selected ? (
          <>
            <header className="flex flex-wrap items-center gap-3 border-b border-slate-800 px-4 py-3">
              <div className="min-w-0 flex-1">
                <h3 className="truncate text-base font-semibold">{selected.title}</h3>
                <p className="text-xs text-slate-500">
                  {selected.template_name || selected.template_id}
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
              <button
                type="button"
                onClick={() => setPendingDelete(selected)}
                className="rounded-md border border-red-900/60 px-3 py-1.5 text-xs font-medium text-red-300 hover:bg-red-950/40"
              >
                Eliminar
              </button>
            </header>
            {notice ? (
              <p className="border-b border-slate-800 px-4 py-2 text-xs text-emerald-300">{notice}</p>
            ) : null}
            {error ? (
              <p className="border-b border-amber-900/40 px-4 py-2 text-xs text-amber-200">{error}</p>
            ) : null}
            <div className="flex min-h-0 flex-1">
              {hasRenderablePreview(selected.progress) ? (
                <>
                  <div className="relative min-w-0 flex-1 bg-white">
                    <iframe
                      key={selected.instance_id}
                      src={previewSrc}
                      title="Vista previa del informe"
                      className="h-full w-full"
                      sandbox="allow-same-origin"
                    />
                  </div>
                  <SectionsSidebar
                    sections={orderedSections(selected.progress)}
                    renderedDocxUri={selected.rendered_docx_uri}
                  />
                </>
              ) : (
                <DraftWorkspace
                  instance={selected}
                  playgroundHref={playgroundHref}
                  sections={orderedSections(selected.progress)}
                />
              )}
            </div>
          </>
        ) : (
          <div className="flex flex-1 flex-col items-center justify-center gap-3 px-6 text-center text-sm text-slate-500">
            <p>{loading ? 'Cargando informes…' : 'Selecciona un informe o crea uno nuevo.'}</p>
            {!loading ? (
              <button
                type="button"
                onClick={openWizard}
                className="rounded-md bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500"
              >
                Nuevo informe
              </button>
            ) : null}
          </div>
        )}
      </div>

      <ConfirmDangerModal
        isOpen={Boolean(pendingDelete)}
        title="Eliminar informe"
        description="Se archivará y dejará de aparecer en la lista."
        confirmLabel="Sí, eliminar"
        isLoading={deleting && Boolean(pendingDelete)}
        details={
          pendingDelete
            ? [
                { label: 'Título', value: pendingDelete.title },
                { label: 'ID', value: pendingDelete.instance_id },
              ]
            : []
        }
        onConfirm={() => void confirmDelete()}
        onCancel={() => {
          if (!deleting) setPendingDelete(null);
        }}
      />

      <ConfirmDangerModal
        isOpen={Boolean(pendingDeleteTemplate)}
        title="Eliminar plantilla"
        description="Se archivará la plantilla y también los informes activos tuyos que la usen. El .docx del vault no se borra."
        confirmLabel="Sí, eliminar plantilla"
        isLoading={deleting && Boolean(pendingDeleteTemplate)}
        details={
          pendingDeleteTemplate
            ? [
                { label: 'Nombre', value: pendingDeleteTemplate.name },
                { label: 'ID', value: pendingDeleteTemplate.template_id },
                { label: 'URI', value: pendingDeleteTemplate.template_uri || '—' },
              ]
            : []
        }
        onConfirm={() => void confirmDeleteTemplate()}
        onCancel={() => {
          if (!deleting) setPendingDeleteTemplate(null);
        }}
      />

      <VaultDocxPicker
        open={vaultPickerOpen}
        onClose={() => setVaultPickerOpen(false)}
        onSelect={(path) => {
          setTemplatePath(path);
          setTemplateMode('vault_path');
          setSelectedTemplateId('');
          const base = path.replace(/\\/g, '/').split('/').filter(Boolean).pop() || '';
          if (!templateName.trim() && base) {
            setTemplateName(base.replace(/\.docx$/i, ''));
          }
        }}
      />
    </div>
  );
}
