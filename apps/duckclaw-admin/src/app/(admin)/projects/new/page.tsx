'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { adminService } from '@/services/adminService';
import SettingsSection from '@/components/settings/SettingsSection';
import { clampInput, LIMITS, validateWorkerId } from '@/lib/validation';
import { useAuthStore } from '@/store/authStore';
import { slugFromAgentName, presetForTemplateId } from '@/lib/templatePresets';
import { useTemplatePresets } from '@/lib/useTemplatePresets';
import { FolderPlus, Check, Sparkles, Layers } from 'lucide-react';
import type { TemplateSummary } from '@/types/admin';

const STEPS_AGENT = [
  'Tu agente',
  'Comportamiento',
  'Tipo de asistente',
  'Capacidades',
  'Herramientas',
  'Listo para crear',
] as const;

const STEPS_PROJECT = ['Proyecto', 'Miembros', 'Contexto compartido', 'Listo'] as const;

const DEFAULT_PROMPT_HINT = `Eres un asistente de IA útil y claro.

- Ayudas al usuario con las tareas que defina su creador.
- No inventes datos; si no sabes algo, dilo con honestidad.
- Responde en español salvo que el usuario pida otro idioma.`;

export default function NewProjectPage() {
  const router = useRouter();
  const { usuario } = useAuthStore();
  const canWrite = usuario?.rol === 'admin';

  const [step, setStep] = useState(0);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [id, setId] = useState('');
  const [source, setSource] = useState('default');
  const [systemPrompt, setSystemPrompt] = useState('');
  const [soul, setSoul] = useState('');
  const [selectedSkills, setSelectedSkills] = useState<string[]>([]);
  const [useDefaultSkills, setUseDefaultSkills] = useState(true);
  const [advancedMode, setAdvancedMode] = useState(false);
  const [createMode, setCreateMode] = useState<'agent' | 'project'>('agent');
  const [allTemplates, setAllTemplates] = useState<TemplateSummary[]>([]);
  const [projectMembers, setProjectMembers] = useState<string[]>([]);
  const [projectCoordinator, setProjectCoordinator] = useState<string | undefined>();
  const [projectVault, setProjectVault] = useState<string | undefined>();
  const [sharedContext, setSharedContext] = useState('');
  const [applyTenantTeam, setApplyTenantTeam] = useState(true);
  const [envPresets, setEnvPresets] = useState<
    Awaited<ReturnType<typeof adminService.listEnvForgeProjectPresets>>
  >([]);
  const [mcpSummary, setMcpSummary] = useState('');
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const { presets, loading: presetsLoading, error: presetsError } = useTemplatePresets(advancedMode);
  const STEPS = createMode === 'project' ? STEPS_PROJECT : STEPS_AGENT;

  useEffect(() => {
    adminService.getSourcePreview('default').then((p) => {
      if (!systemPrompt && p.system_prompt) setSystemPrompt(p.system_prompt);
      if (!soul && p.soul) setSoul(p.soul);
      setSelectedSkills(p.skills ?? []);
    });
    adminService.listTemplates().then(setAllTemplates).catch(() => undefined);
    adminService.listEnvForgeProjectPresets().then(setEnvPresets).catch(() => setEnvPresets([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- solo al montar
  }, []);

  useEffect(() => {
    adminService.getSourcePreview(source).then((p) => {
      setSelectedSkills(p.skills ?? []);
    });
    adminService.getMcpCatalog().then((r) => {
      setMcpSummary(
        `Tu agente podrá usar ${r.duckclaw_mcp.tools.length} herramientas del sistema cuando las actives más adelante.`
      );
    });
  }, [source]);

  useEffect(() => {
    if (!advancedMode && name.trim()) {
      const slug = slugFromAgentName(name);
      if (slug) setId(slug);
    }
  }, [name, advancedMode]);

  const validateStep = (): boolean => {
    if (step === 0) {
      if (!name.trim()) {
        setFieldError(
          createMode === 'project'
            ? 'Escribe un nombre para el proyecto.'
            : 'Escribe un nombre para tu agente (ej. Asistente de ventas).'
        );
        return false;
      }
      const wid = id.trim() || slugFromAgentName(name);
      const idErr = validateWorkerId(wid);
      if (idErr) {
        setFieldError(idErr);
        return false;
      }
      if (!id.trim()) setId(wid);
    }
    if (createMode === 'project' && step === 1 && projectMembers.length === 0) {
      setFieldError('Elige al menos un worker o importa un preset desde .env.');
      return false;
    }
    if (createMode === 'agent' && step === 1) {
      if (systemPrompt.trim().length < 20) {
        setFieldError(
          'Escribe al menos unas líneas de comportamiento (mín. 20 caracteres). Indica cómo debe actuar tu agente.'
        );
        return false;
      }
    }
    setFieldError(null);
    return true;
  };

  const next = () => {
    if (!validateStep()) return;
    setStep((s) => Math.min(s + 1, STEPS.length - 1));
  };

  const back = () => setStep((s) => Math.max(s - 1, 0));

  const importEnvPreset = (presetId: string) => {
    const preset = envPresets.find((p) => p.id === presetId);
    if (!preset) return;
    setProjectMembers(preset.members);
    setName(preset.display_name);
    setId(preset.id);
    setProjectCoordinator(preset.coordinator ?? undefined);
    setProjectVault(preset.shared_vault_id ?? undefined);
    if (preset.shared_context) setSharedContext(preset.shared_context);
  };

  const toggleMember = (workerId: string) => {
    setProjectMembers((prev) =>
      prev.includes(workerId) ? prev.filter((x) => x !== workerId) : [...prev, workerId]
    );
  };

  const finish = async () => {
    if (!canWrite) return;
    setLoading(true);
    setError(null);
    const workerId = id.trim() || slugFromAgentName(name);
    try {
      if (createMode === 'project') {
        await adminService.createForgeProject({
          id: workerId,
          display_name: name.trim(),
          members: projectMembers,
          coordinator: projectCoordinator,
          shared_vault_id: projectVault,
          shared_context: sharedContext.trim(),
          apply_tenant_team: applyTenantTeam,
        });
        router.push('/projects');
        return;
      }
      await adminService.createProject({
        id: workerId,
        source_template: source,
        name: name.trim(),
        description: description.trim(),
        skills: selectedSkills,
        topology: 'general',
        system_prompt: systemPrompt.trim(),
        soul: soul.trim(),
      });
      try {
        await adminService.createKanbanCard({
          title: name.trim(),
          description: description.trim() || 'Agente creado desde el asistente',
          status: 'completo',
          worker_id: workerId,
        });
      } catch {
        /* tablero opcional */
      }
      router.push(`/templates/${workerId}?focus=system_prompt.md`);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error');
    } finally {
      setLoading(false);
    }
  };

  const preset = presetForTemplateId(source, presets);

  return (
    <div className="space-y-6 max-w-3xl">
      <header>
        <h1 className="text-3xl font-black dark:text-dark-text">
          {createMode === 'project' ? 'Crear proyecto' : 'Crear un agente de IA'}
        </h1>
        <p className="text-sm text-gov-gray-500 mt-1">
          {createMode === 'project'
            ? 'Agrupa workers existentes y opcionalmente aplica el equipo al tenant.'
            : 'Sin código. Responde unas preguntas y DuckClaw prepara la configuración por ti.'}
        </p>
        <div className="flex flex-wrap gap-2 mt-3">
          <button
            type="button"
            onClick={() => {
              setCreateMode('agent');
              setStep(0);
            }}
            className={`text-xs px-3 py-1.5 rounded-full font-bold ${
              createMode === 'agent' ? 'bg-gov-blue-700 text-white' : 'border dark:border-dark-border'
            }`}
          >
            Un agente
          </button>
          <button
            type="button"
            onClick={() => {
              setCreateMode('project');
              setStep(0);
            }}
            className={`text-xs px-3 py-1.5 rounded-full font-bold inline-flex items-center gap-1 ${
              createMode === 'project' ? 'bg-gov-blue-700 text-white' : 'border dark:border-dark-border'
            }`}
          >
            <Layers size={12} /> Proyecto (varios workers)
          </button>
        </div>
        <Link href="/projects" className="text-sm text-gov-blue-700 font-semibold mt-2 inline-block">
          Ver proyectos →
        </Link>
      </header>

      <WizardStepper current={step} labels={STEPS} />

      <SettingsSection
        titulo={STEPS[step]}
        descripcion={`Paso ${step + 1} de ${STEPS.length}`}
        icono={<FolderPlus size={22} />}
      >
        {step === 0 && (
          <div className="space-y-4 max-w-lg">
            <Field label={createMode === 'project' ? '¿Cómo se llama tu proyecto?' : '¿Cómo se llama tu agente?'}>
              <input
                value={name}
                onChange={(e) => setName(clampInput(e.target.value, 64))}
                maxLength={64}
                className={inputCls}
                placeholder={createMode === 'project' ? 'Ej. Ventas corporativas' : 'Ej. Asistente de ventas'}
              />
            </Field>
            {createMode === 'agent' && (
            <Field label="¿Qué debe hacer? (opcional)">
              <textarea
                value={description}
                onChange={(e) => setDescription(clampInput(e.target.value, 500))}
                maxLength={500}
                rows={3}
                className={inputCls}
                placeholder="Ej. Responder preguntas de clientes y resumir pedidos del día."
              />
            </Field>
            )}
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={advancedMode}
                onChange={(e) => setAdvancedMode(e.target.checked)}
              />
              Modo avanzado (ID técnico y plantillas expertas)
            </label>
            {advancedMode && (
              <Field label="ID interno (carpeta)">
                <input
                  value={id}
                  onChange={(e) => setId(clampInput(e.target.value, LIMITS.workerId))}
                  maxLength={LIMITS.workerId}
                  className={inputCls}
                  placeholder="mi-agente"
                />
              </Field>
            )}
          </div>
        )}

        {createMode === 'project' && step === 1 && (
          <div className="space-y-4 max-w-2xl">
            {envPresets.length > 0 && (
              <div className="flex flex-wrap gap-2">
                <span className="text-xs text-gov-gray-500 w-full">Presets en .env:</span>
                {envPresets.map((p) => (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => importEnvPreset(p.id)}
                    className="px-3 py-2 text-xs font-bold rounded-xl border-2 border-gov-blue-600"
                  >
                    {p.display_name}
                  </button>
                ))}
              </div>
            )}
            <div className="flex flex-wrap gap-2 max-h-48 overflow-y-auto">
              {allTemplates.map((t) => {
                const on = projectMembers.includes(t.id);
                return (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => toggleMember(t.id)}
                    className={`px-3 py-2 rounded-xl text-xs font-mono border ${
                      on ? 'bg-gov-blue-700 text-white' : 'dark:border-dark-border'
                    }`}
                  >
                    {on ? '✓ ' : ''}
                    {t.id}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {createMode === 'project' && step === 2 && (
          <div className="space-y-4 max-w-2xl">
            <Field label="Contexto compartido (opcional)">
              <textarea
                value={sharedContext}
                onChange={(e) => setSharedContext(clampInput(e.target.value, 8000))}
                rows={6}
                className={inputCls}
              />
            </Field>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={applyTenantTeam}
                onChange={(e) => setApplyTenantTeam(e.target.checked)}
              />
              Aplicar equipo al tenant
            </label>
          </div>
        )}

        {createMode === 'project' && step === 3 && (
          <div className="space-y-4">
            <dl className="text-sm space-y-3 rounded-xl border dark:border-dark-border p-4">
              <Row k="Proyecto" v={name} />
              <Row k="Miembros" v={projectMembers.join(', ') || '—'} />
            </dl>
            {error && <p className="text-red-600 text-sm">{error}</p>}
          </div>
        )}

        {createMode === 'agent' && step === 1 && (
          <div className="space-y-4 max-w-2xl">
            <p className="text-sm text-gov-gray-500">
              Instrucciones de comportamiento (system_prompt). Base: plantilla{' '}
              <strong>default</strong>.
            </p>
            <Field label="¿Cómo debe actuar tu agente? (obligatorio)">
              <textarea
                value={systemPrompt}
                onChange={(e) => setSystemPrompt(clampInput(e.target.value, 12000))}
                maxLength={12000}
                rows={12}
                className={`${inputCls} font-mono text-xs`}
                placeholder={DEFAULT_PROMPT_HINT}
              />
            </Field>
            <Field label="Tono (opcional, soul.md)">
              <textarea
                value={soul}
                onChange={(e) => setSoul(clampInput(e.target.value, 4000))}
                maxLength={4000}
                rows={3}
                className={inputCls}
              />
            </Field>
            <button
              type="button"
              className="text-xs text-gov-blue-700 font-semibold"
              onClick={() => setSystemPrompt(DEFAULT_PROMPT_HINT)}
            >
              Restaurar texto sugerido
            </button>
          </div>
        )}

        {createMode === 'agent' && step === 2 && (
          <div className="space-y-4">
            <p className="text-sm text-gov-gray-500">
              Perfil de habilidades extra (catálogo en vivo desde el gateway).
            </p>
            {presetsError && <p className="text-amber-700 text-sm">{presetsError}</p>}
            {presetsLoading && <p className="text-sm text-gov-gray-400">Cargando plantillas…</p>}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {presets.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => setSource(p.id)}
                  className={`text-left p-4 rounded-2xl border-2 transition-colors ${
                    source === p.id
                      ? 'border-gov-blue-700 bg-gov-blue-50 dark:bg-dark-bg'
                      : 'border-gov-gray-100 dark:border-dark-border hover:border-gov-blue-300'
                  }`}
                >
                  <span className="text-2xl">{p.emoji}</span>
                  <p className="font-bold text-sm mt-2 flex items-center gap-2">
                    {p.title}
                    {p.recommended && (
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-gov-cyan-100 text-gov-blue-800">
                        Recomendado
                      </span>
                    )}
                  </p>
                  <p className="text-xs text-gov-gray-500 mt-1">{p.subtitle}</p>
                </button>
              ))}
            </div>
          </div>
        )}

        {createMode === 'agent' && step === 3 && (
          <div className="space-y-4">
            <p className="text-sm text-gov-gray-500">
              Las <strong>capacidades</strong> son acciones que tu agente puede realizar (buscar datos,
              hora, etc.). Lo habitual es dejar las de la plantilla.
            </p>
            <label className="flex items-center gap-2 text-sm font-medium">
              <input
                type="checkbox"
                checked={useDefaultSkills}
                onChange={(e) => setUseDefaultSkills(e.target.checked)}
              />
              Usar capacidades recomendadas para «{preset?.title ?? 'esta plantilla'}»
            </label>
            {!useDefaultSkills && advancedMode && (
              <p className="text-xs text-gov-gray-500">
                {selectedSkills.length} capacidades en la plantilla. Edítalas después en Workers si
                necesitas afinar.
              </p>
            )}
            {!advancedMode && (
              <p className="text-xs text-gov-gray-400 flex items-center gap-1">
                <Sparkles size={14} /> Activa modo avanzado si quieres elegir capacidades una a una.
              </p>
            )}
          </div>
        )}

        {createMode === 'agent' && step === 4 && (
          <div className="space-y-4 max-w-2xl">
            <p className="text-sm text-gov-gray-500">
              Conexiones opcionales con otras herramientas (clima, comandos del bot, etc.). Puedes
              configurarlas después en el menú <strong>MCP</strong>.
            </p>
            <p className="text-sm">{mcpSummary}</p>
          </div>
        )}

        {createMode === 'agent' && step === 5 && (
          <div className="space-y-4">
            <dl className="text-sm space-y-3 rounded-xl border dark:border-dark-border p-4">
              <Row k="Nombre" v={name} />
              <Row k="Descripción" v={description || '—'} />
              <Row k="Perfil" v={preset?.title ?? source} />
              <Row k="Comportamiento" v={`${systemPrompt.length} caracteres`} />
              <Row k="Capacidades" v={useDefaultSkills ? 'Recomendadas' : 'Personalizadas'} />
            </dl>
            {error && <p className="text-red-600 text-sm">{error}</p>}
            {!canWrite && (
              <p className="text-amber-700 text-sm">Tu rol no permite crear agentes. Pide acceso admin.</p>
            )}
          </div>
        )}

        {fieldError && <p className="text-red-600 text-sm">{fieldError}</p>}

        <div className="flex gap-2 pt-4">
          {step > 0 && (
            <button type="button" onClick={back} className="px-4 py-2 border rounded-xl text-sm">
              Atrás
            </button>
          )}
          {step < STEPS.length - 1 ? (
            <button
              type="button"
              onClick={next}
              disabled={step === 0 && !name.trim()}
              className="px-4 py-2 bg-gov-blue-700 text-white rounded-xl text-sm font-bold disabled:opacity-50"
            >
              Siguiente
            </button>
          ) : (
            <button
              type="button"
              onClick={finish}
              disabled={loading || !canWrite}
              className="px-4 py-2 bg-gov-blue-700 text-white rounded-xl text-sm font-bold disabled:opacity-50 flex items-center gap-2"
            >
              {loading
                ? 'Creando…'
                : createMode === 'project'
                  ? 'Crear proyecto'
                  : 'Crear mi agente'}
            </button>
          )}
        </div>
      </SettingsSection>
    </div>
  );
}

const inputCls =
  'w-full px-3 py-2 border rounded-xl dark:border-dark-border dark:bg-dark-bg text-sm';

function WizardStepper({ current, labels }: { current: number; labels: readonly string[] }) {
  return (
    <ol className="flex flex-wrap gap-2 mb-6">
      {labels.map((label, i) => (
        <li
          key={label}
          className={`text-xs px-3 py-1.5 rounded-full font-bold ${
            i === current
              ? 'bg-gov-blue-700 text-white'
              : i < current
                ? 'bg-gov-cyan-100 text-gov-blue-800 dark:bg-dark-bg'
                : 'bg-gov-gray-100 text-gov-gray-500 dark:bg-dark-surface'
          }`}
        >
          {i + 1}. {label}
        </li>
      ))}
    </ol>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-1">
      <span className="text-sm font-bold">{label}</span>
      {children}
    </label>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex gap-3">
      <dt className="text-gov-gray-500 w-28 shrink-0">{k}</dt>
      <dd className="text-sm">{v}</dd>
    </div>
  );
}
