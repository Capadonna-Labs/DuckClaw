'use client';

import { Sparkles } from 'lucide-react';
import {
  applyManifestQuick,
  parseManifestQuick,
  type ManifestQuickState,
  type ToolProfile,
} from '@/lib/manifestQuickEdit';

type ManifestGuidedPanelProps = {
  yaml: string;
  onChange: (nextYaml: string) => void;
  disabled?: boolean;
};

export function ManifestGuidedPanel({ yaml, onChange, disabled }: ManifestGuidedPanelProps) {
  const state = parseManifestQuick(yaml);

  const patch = (partial: Partial<ManifestQuickState>) => {
    const next = { ...state, ...partial };
    onChange(applyManifestQuick(yaml, next));
  };

  return (
    <section className="rounded-2xl border border-gov-blue-100 bg-gov-blue-50/40 p-4 dark:border-dark-border dark:bg-dark-bg/60">
      <p className="flex items-center gap-2 text-sm font-black text-gov-gray-900 dark:text-dark-text">
        <Sparkles size={16} className="text-gov-blue-700 dark:text-dark-cyan" />
        Configuración rápida
      </p>
      <p className="mt-1 text-[11px] text-gov-gray-600 dark:text-dark-muted">
        SQL, RAG, vault y sandbox base vienen incluidos por la plataforma. Aquí solo ajustas extras.
      </p>

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <label className="block space-y-1.5">
          <span className="text-[10px] font-black uppercase tracking-wide text-gov-gray-500">
            Perfil de herramientas
          </span>
          <select
            disabled={disabled}
            value={state.toolProfile}
            onChange={(e) => patch({ toolProfile: e.target.value as ToolProfile })}
            className="w-full rounded-xl border border-gov-gray-200 bg-white px-3 py-2 text-sm dark:border-dark-border dark:bg-dark-surface"
          >
            <option value="general">General (recomendado)</option>
            <option value="rag_only">Solo RAG + vault</option>
            <option value="minimal">Mínimo (hora + SQL)</option>
          </select>
        </label>

        <div className="space-y-2">
          <ToggleRow
            label="Búsqueda web (Tavily)"
            hint="Requiere TAVILY_API_KEY en el gateway"
            checked={state.webSearch}
            disabled={disabled}
            onChange={(webSearch) => patch({ webSearch })}
          />
          <ToggleRow
            label="Navegador sandbox (VNC)"
            hint="Para sitios web interactivos"
            checked={state.browserSandbox}
            disabled={disabled}
            onChange={(browserSandbox) => patch({ browserSandbox })}
          />
          <ToggleRow
            label="Desactivar baseline de plataforma"
            hint="Solo casos avanzados"
            checked={state.baselineOff}
            disabled={disabled}
            onChange={(baselineOff) => patch({ baselineOff })}
          />
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
