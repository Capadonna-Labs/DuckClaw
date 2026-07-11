'use client';

import { useMemo } from 'react';
import { Sparkles } from 'lucide-react';
import type { SkillCatalogItem } from '@/services/adminService';
import { WorkerSkillPickerPanel } from '@/components/templates/WorkerSkillPickerPanel';
import {
  buildDraftManifestYaml,
  parseDraftCompositionFromManifest,
  type DraftComposition,
} from '@/lib/draftManifestYaml';
import { DEFAULT_TOOL_PROFILE } from '@/lib/workerRoleTemplates';

type WorkerCompositionPanelProps = {
  composition: DraftComposition;
  onCompositionChange: (next: DraftComposition) => void;
  disabled?: boolean;
  workerId?: string;
  globalSkills?: SkillCatalogItem[];
  localSkills?: SkillCatalogItem[];
  showSkillPicker?: boolean;
};

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
    <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-gov-gray-200 px-3 py-2 dark:border-dark-border">
      <input
        type="checkbox"
        className="mt-0.5"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span>
        <span className="block text-xs font-semibold text-gov-gray-900 dark:text-dark-text">{label}</span>
        <span className="block text-[10px] text-gov-gray-500 dark:text-dark-muted">{hint}</span>
      </span>
    </label>
  );
}

export function WorkerCompositionPanel({
  composition,
  onCompositionChange,
  disabled,
  workerId,
  globalSkills = [],
  localSkills = [],
  showSkillPicker = true,
}: WorkerCompositionPanelProps) {
  const normalizedComposition = useMemo(
    () => ({ ...composition, tool_profile: DEFAULT_TOOL_PROFILE }),
    [composition]
  );

  const manifestYaml = useMemo(
    () => buildDraftManifestYaml(normalizedComposition),
    [normalizedComposition]
  );

  const patchComposition = (partial: Partial<DraftComposition>) => {
    onCompositionChange({ ...normalizedComposition, ...partial, tool_profile: DEFAULT_TOOL_PROFILE });
  };

  const onManifestChange = (nextYaml: string) => {
    const parsed = parseDraftCompositionFromManifest(nextYaml, normalizedComposition);
    onCompositionChange({ ...parsed, tool_profile: DEFAULT_TOOL_PROFILE });
  };

  return (
    <section className="space-y-4 rounded-xl border border-gov-gray-200 bg-white p-4 dark:border-dark-border dark:bg-dark-surface">
      <div>
        <p className="flex items-center gap-2 text-sm font-semibold text-gov-gray-900 dark:text-dark-text">
          <Sparkles size={16} className="text-gov-blue-700 dark:text-dark-cyan" />
          Herramientas y extras
        </p>
        <p className="mt-1 text-xs text-gov-gray-500 dark:text-dark-muted">
          Baseline completo (SQL, RAG, documentos). El agente usa solo lo que el turno requiere; aquí activas
          extras opcionales y skills.
        </p>
      </div>

      <div className="grid gap-2 sm:grid-cols-2">
        <ToggleRow
          label="Buscar en internet"
          hint="Activa skill research (Tavily) si hay API key"
          checked={normalizedComposition.web_search}
          disabled={disabled}
          onChange={(web_search) => patchComposition({ web_search })}
        />
        <ToggleRow
          label="Navegador sandbox"
          hint="Permite abrir URLs en sandbox del worker"
          checked={normalizedComposition.browser_sandbox}
          disabled={disabled}
          onChange={(browser_sandbox) => patchComposition({ browser_sandbox })}
        />
      </div>

      {showSkillPicker ? (
        <WorkerSkillPickerPanel
          manifestYaml={manifestYaml}
          onManifestChange={onManifestChange}
          disabled={disabled}
          workerId={workerId}
          globalSkills={globalSkills}
          localSkills={localSkills}
          compact
        />
      ) : null}
    </section>
  );
}
