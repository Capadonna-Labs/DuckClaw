'use client';

import { Sparkles } from 'lucide-react';
import {
  applyManifestQuick,
  DEFAULT_MAX_TOOL_ROUNDS,
  MAX_TOOL_ROUNDS_CEILING,
  parseManifestQuick,
  type ManifestQuickState,
  type ToolProfile,
} from '@/lib/manifestQuickEdit';

type ManifestGuidedPanelProps = {
  yaml: string;
  onChange: (nextYaml: string) => void;
  disabled?: boolean;
};

const CAPABILITY_PRESETS: ReadonlyArray<{
  id: ToolProfile;
  title: string;
  description: string;
}> = [
  {
    id: 'general',
    title: 'Asistente completo',
    description: 'Datos, documentación e informes. El equilibrio habitual.',
  },
  {
    id: 'rag_only',
    title: 'Enfocado en documentación',
    description: 'Busca y lee en tu conocimiento. Sin consultas SQL ni extras.',
  },
  {
    id: 'minimal',
    title: 'Consultas ligeras',
    description: 'Hora y SQL básico. Menos capacidades, más rápido.',
  },
];

export function ManifestGuidedPanel({ yaml, onChange, disabled }: ManifestGuidedPanelProps) {
  const state = parseManifestQuick(yaml);

  const patch = (partial: Partial<ManifestQuickState>) => {
    const next = { ...state, ...partial };
    onChange(applyManifestQuick(yaml, next));
  };

  const activePreset =
    CAPABILITY_PRESETS.find((preset) => preset.id === state.toolProfile) ?? CAPABILITY_PRESETS[0];

  return (
    <section className="rounded-2xl border border-gov-blue-100 bg-gov-blue-50/40 p-4 dark:border-dark-border dark:bg-dark-bg/60">
      <p className="flex items-center gap-2 text-sm font-black text-gov-gray-900 dark:text-dark-text">
        <Sparkles size={16} className="text-gov-blue-700 dark:text-dark-cyan" />
        Qué puede hacer en el chat
      </p>
      <p className="mt-1 text-[11px] text-gov-gray-600 dark:text-dark-muted">
        Elige el estilo de ayuda. Las instrucciones de comportamiento las escribes en las pestañas de
        arriba; aquí solo defines capacidades extra.
      </p>

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <fieldset className="space-y-2" disabled={disabled}>
          <legend className="text-[10px] font-black uppercase tracking-wide text-gov-gray-500">
            Nivel de capacidades
          </legend>
          <div className="space-y-2">
            {CAPABILITY_PRESETS.map((preset) => {
              const selected = state.toolProfile === preset.id;
              return (
                <label
                  key={preset.id}
                  className={`flex cursor-pointer gap-3 rounded-xl border px-3 py-2.5 transition-colors ${
                    selected
                      ? 'border-gov-blue-400 bg-white shadow-sm dark:border-dark-cyan/50 dark:bg-dark-surface'
                      : 'border-gov-gray-200 bg-white/60 hover:border-gov-gray-300 dark:border-dark-border dark:bg-dark-surface/40'
                  }`}
                >
                  <input
                    type="radio"
                    name="tool-capability-preset"
                    className="mt-1"
                    checked={selected}
                    disabled={disabled}
                    onChange={() => patch({ toolProfile: preset.id })}
                  />
                  <span>
                    <span className="block text-xs font-bold text-gov-gray-900 dark:text-dark-text">
                      {preset.title}
                      {preset.id === 'general' ? (
                        <span className="ml-1 font-normal text-gov-gray-500">· recomendado</span>
                      ) : null}
                    </span>
                    <span className="mt-0.5 block text-[10px] leading-snug text-gov-gray-600 dark:text-dark-muted">
                      {preset.description}
                    </span>
                  </span>
                </label>
              );
            })}
          </div>
          <p className="text-[10px] text-gov-gray-500 dark:text-dark-muted">
            Seleccionado: <span className="font-semibold text-gov-gray-700 dark:text-dark-text">{activePreset.title}</span>
          </p>
        </fieldset>

        <div className="space-y-2">
          <p className="text-[10px] font-black uppercase tracking-wide text-gov-gray-500">
            Extras opcionales
          </p>
          <ToggleRow
            label="Buscar en internet"
            hint="Cuando necesite información actual fuera de tus documentos"
            checked={state.webSearch}
            disabled={disabled}
            onChange={(webSearch) => patch({ webSearch })}
          />
          <ToggleRow
            label="Abrir sitios web"
            hint="Para páginas que requieren interacción en navegador"
            checked={state.browserSandbox}
            disabled={disabled}
            onChange={(browserSandbox) => patch({ browserSandbox })}
          />
          <details className="rounded-xl border border-dashed border-gov-gray-200 px-2 py-1 dark:border-dark-border">
            <summary className="cursor-pointer px-1 py-1 text-[10px] font-bold uppercase tracking-wide text-gov-gray-500">
              Avanzado
            </summary>
            <div className="mt-1 px-1 pb-1 space-y-3">
              <ToggleRow
                label="Sin capacidades base de plataforma"
                hint="Solo para perfiles técnicos; puede romper flujos habituales"
                checked={state.baselineOff}
                disabled={disabled}
                onChange={(baselineOff) => patch({ baselineOff })}
              />
              <div className="rounded-xl border border-gov-gray-200 bg-white/70 px-3 py-2.5 dark:border-dark-border dark:bg-dark-surface/50">
                <label className="block text-xs font-bold text-gov-gray-900 dark:text-dark-text">
                  Pasos con herramientas por turno
                </label>
                <p className="mt-0.5 text-[10px] leading-snug text-gov-gray-600 dark:text-dark-muted">
                  Cuántas veces puede invocar tools el agente antes de cortar el turno (default{' '}
                  {DEFAULT_MAX_TOOL_ROUNDS}). Sube el valor si ves &quot;Alcancé el límite de pasos
                  con herramientas&quot;.
                </p>
                <div className="mt-2 flex items-center gap-3">
                  <input
                    type="range"
                    min={1}
                    max={MAX_TOOL_ROUNDS_CEILING}
                    step={1}
                    value={state.maxToolRounds}
                    disabled={disabled}
                    className="flex-1 accent-gov-blue-700 dark:accent-dark-cyan"
                    onChange={(e) =>
                      patch({
                        maxToolRounds: Math.max(
                          1,
                          Math.min(MAX_TOOL_ROUNDS_CEILING, Number(e.target.value) || DEFAULT_MAX_TOOL_ROUNDS)
                        ),
                      })
                    }
                  />
                  <input
                    type="number"
                    min={1}
                    max={MAX_TOOL_ROUNDS_CEILING}
                    step={1}
                    value={state.maxToolRounds}
                    disabled={disabled}
                    className="w-16 rounded-lg border border-gov-gray-200 px-2 py-1 text-center text-xs font-bold tabular-nums dark:border-dark-border dark:bg-dark-bg"
                    onChange={(e) => {
                      const n = Number.parseInt(e.target.value, 10);
                      patch({
                        maxToolRounds: Number.isFinite(n)
                          ? Math.max(1, Math.min(MAX_TOOL_ROUNDS_CEILING, n))
                          : DEFAULT_MAX_TOOL_ROUNDS,
                      });
                    }}
                  />
                </div>
              </div>
            </div>
          </details>
        </div>
      </div>
    </section>
  );
}

function ToggleRow({
  label,
  hint,
  checked,
  disabled,
  onChange,
}: {
  label: string;
  hint: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <label className="flex cursor-pointer items-start gap-2 rounded-xl border border-transparent px-1 py-0.5 hover:border-gov-gray-200 dark:hover:border-dark-border">
      <input
        type="checkbox"
        className="mt-1"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span>
        <span className="block text-xs font-bold text-gov-gray-800 dark:text-dark-text">{label}</span>
        <span className="block text-[10px] text-gov-gray-500 dark:text-dark-muted">{hint}</span>
      </span>
    </label>
  );
}
