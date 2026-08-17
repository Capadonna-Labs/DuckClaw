'use client';

import { Sparkles } from 'lucide-react';
import {
  applyManifestQuick,
  DEFAULT_MAX_TOOL_ROUNDS,
  MAX_TOOL_ROUNDS_CEILING,
  parseManifestQuick,
  type ManifestQuickState,
} from '@/lib/manifestQuickEdit';
import { DEFAULT_TOOL_PROFILE } from '@/lib/workerRoleTemplates';

type ManifestGuidedPanelProps = {
  yaml: string;
  onChange: (nextYaml: string) => void;
  disabled?: boolean;
};

export function ManifestGuidedPanel({ yaml, onChange, disabled }: ManifestGuidedPanelProps) {
  const state = parseManifestQuick(yaml);

  const patch = (partial: Partial<ManifestQuickState>) => {
    const next = { ...state, ...partial, toolProfile: DEFAULT_TOOL_PROFILE };
    onChange(applyManifestQuick(yaml, next));
  };

  return (
    <section className="rounded-xl border border-gov-gray-200 bg-white dark:border-dark-border dark:bg-dark-surface">
      <div className="border-b border-gov-gray-100 px-4 py-3 dark:border-dark-border">
        <p className="flex items-center gap-2 text-sm font-semibold text-gov-gray-900 dark:text-dark-text">
          <Sparkles size={16} className="text-gov-blue-700 dark:text-dark-cyan" />
          Qué puede hacer en el chat
        </p>
        <p className="mt-0.5 text-xs text-gov-gray-500 dark:text-dark-muted">
          Baseline completo (asistente general). Ajusta extras; el comportamiento lo defines en instrucciones.
        </p>
      </div>

      <div className="space-y-2 p-4">
        <p className="text-xs font-medium text-gov-gray-600 dark:text-dark-muted">Extras opcionales</p>
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
        <details className="rounded-lg border border-dashed border-gov-gray-200 px-2 py-1 dark:border-dark-border">
          <summary className="cursor-pointer px-1 py-1 text-[10px] font-semibold uppercase tracking-wide text-gov-gray-500">
            Avanzado
          </summary>
          <div className="mt-1 space-y-3 px-1 pb-1">
            <ToggleRow
              label="Sin capacidades base de plataforma"
              hint="Solo para perfiles técnicos; puede romper flujos habituales"
              checked={state.baselineOff}
              disabled={disabled}
              onChange={(baselineOff) => patch({ baselineOff })}
            />
            <div className="rounded-lg border border-gov-gray-200 px-3 py-2.5 dark:border-dark-border">
              <label className="block text-xs font-semibold text-gov-gray-900 dark:text-dark-text">
                Pasos con herramientas por turno
              </label>
              <p className="mt-0.5 text-[10px] leading-snug text-gov-gray-600 dark:text-dark-muted">
                Cuántas veces puede invocar tools el agente antes de cortar el turno (default{' '}
                {DEFAULT_MAX_TOOL_ROUNDS}).
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
                  className="w-16 rounded-lg border border-gov-gray-200 px-2 py-1 text-center text-xs font-semibold tabular-nums dark:border-dark-border dark:bg-dark-bg"
                  onChange={(e) => {
                    const raw = e.target.value.trim();
                    if (!raw) return;
                    const n = Number.parseInt(raw, 10);
                    if (!Number.isFinite(n)) return;
                    patch({
                      maxToolRounds: Math.max(1, Math.min(MAX_TOOL_ROUNDS_CEILING, n)),
                    });
                  }}
                />
              </div>
            </div>
          </div>
        </details>
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
    <label className="flex cursor-pointer items-start gap-2 rounded-lg border border-gov-gray-100 px-2 py-1.5 dark:border-dark-border">
      <input
        type="checkbox"
        className="mt-1"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span>
        <span className="block text-xs font-semibold text-gov-gray-800 dark:text-dark-text">{label}</span>
        <span className="block text-[10px] text-gov-gray-500 dark:text-dark-muted">{hint}</span>
      </span>
    </label>
  );
}
