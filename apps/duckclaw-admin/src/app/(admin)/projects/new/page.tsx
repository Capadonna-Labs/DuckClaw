'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { adminService } from '@/services/adminService';
import SettingsSection from '@/components/settings/SettingsSection';
import { clampInput, LIMITS, validateWorkerId } from '@/lib/validation';
import { useAuthStore } from '@/store/authStore';
import {
  BEGINNER_TEMPLATE_PRESETS,
  ADVANCED_TEMPLATE_PRESETS,
  slugFromAgentName,
  presetForTemplateId,
} from '@/lib/templatePresets';
import { FolderPlus, Check, Sparkles } from 'lucide-react';

const STEPS = [
  'Tu agente',
  'Comportamiento',
  'Tipo de asistente',
  'Capacidades',
  'Herramientas',
  'Listo para crear',
] as const;

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
  const [mcpSummary, setMcpSummary] = useState('');
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const presets = advancedMode ? ADVANCED_TEMPLATE_PRESETS : BEGINNER_TEMPLATE_PRESETS;

  useEffect(() => {
    adminService.getSourcePreview('default').then((p) => {
      if (!systemPrompt && p.system_prompt) setSystemPrompt(p.system_prompt);
      if (!soul && p.soul) setSoul(p.soul);
      setSelectedSkills(p.skills ?? []);
    });
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
        setFieldError('Escribe un nombre para tu agente (ej. Asistente de ventas).');
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
    if (step === 1) {
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

  const finish = async () => {
    if (!canWrite) return;
    setLoading(true);
    setError(null);
    const workerId = id.trim() || slugFromAgentName(name);
    try {
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

  const preset = presetForTemplateId(source);

  return (
    <div className="space-y-6 max-w-3xl">
      <header>
        <h1 className="text-3xl font-black dark:text-dark-text">Crear un agente de IA</h1>
        <p className="text-sm text-gov-gray-500 mt-1">
          Sin código. Responde unas preguntas y DuckClaw prepara la configuración por ti.
        </p>
        <Link href="/kanban" className="text-sm text-gov-blue-700 font-semibold mt-2 inline-block">
          Ver tablero de tareas →
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
            <Field label="¿Cómo se llama tu agente?">
              <input
                value={name}
                onChange={(e) => setName(clampInput(e.target.value, 64))}
                maxLength={64}
                className={inputCls}
                placeholder="Ej. Asistente de ventas"
              />
            </Field>
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

        {step === 1 && (
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

        {step === 2 && (
          <div className="space-y-4">
            <p className="text-sm text-gov-gray-500">
              Perfil de habilidades extra (todos parten de default en disco).
            </p>
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

        {step === 3 && (
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

        {step === 4 && (
          <div className="space-y-4 max-w-2xl">
            <p className="text-sm text-gov-gray-500">
              Conexiones opcionales con otras herramientas (clima, comandos del bot, etc.). Puedes
              configurarlas después en el menú <strong>MCP</strong>.
            </p>
            <p className="text-sm">{mcpSummary}</p>
          </div>
        )}

        {step === 5 && (
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
              {loading ? 'Creando…' : (
                <>
                  <Check size={16} /> Crear mi agente
                </>
              )}
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
