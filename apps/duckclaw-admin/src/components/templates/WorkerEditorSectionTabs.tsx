'use client';

export type WorkerEditorSection = 'comportamiento' | 'herramientas' | 'contextos' | 'avanzado';

const SECTIONS: { id: WorkerEditorSection; label: string }[] = [
  { id: 'comportamiento', label: 'Comportamiento' },
  { id: 'herramientas', label: 'Herramientas' },
  { id: 'contextos', label: 'Contextos' },
  { id: 'avanzado', label: 'Avanzado' },
];

type WorkerEditorSectionTabsProps = {
  active: WorkerEditorSection;
  showContextos: boolean;
  onChange: (section: WorkerEditorSection) => void;
};

export function WorkerEditorSectionTabs({
  active,
  showContextos,
  onChange,
}: WorkerEditorSectionTabsProps) {
  const tabs = showContextos
    ? SECTIONS
    : SECTIONS.filter((section) => section.id !== 'contextos');

  return (
    <div
      className="flex flex-wrap gap-1 border-b border-gov-gray-200 dark:border-dark-border"
      role="tablist"
      aria-label="Secciones del worker"
    >
      {tabs.map(({ id, label }) => {
        const selected = active === id;
        return (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={selected}
            onClick={() => onChange(id)}
            className={`border-b-2 px-4 py-2.5 text-sm font-semibold transition-colors -mb-px ${
              selected
                ? 'border-gov-blue-600 text-gov-blue-800 dark:border-dark-cyan dark:text-dark-cyan'
                : 'border-transparent text-gov-gray-500 hover:text-gov-gray-800 dark:hover:text-dark-text'
            }`}
          >
            {label}
          </button>
        );
      })}
    </div>
  );
}

export function sectionForFile(
  file: string,
  promptFiles: string[],
  contextFiles: string[]
): WorkerEditorSection {
  if (file === 'manifest.yaml') return 'herramientas';
  if (promptFiles.includes(file)) return 'comportamiento';
  if (contextFiles.includes(file)) return 'contextos';
  return 'avanzado';
}

export function defaultFileForSection(
  section: WorkerEditorSection,
  promptFiles: string[],
  contextFiles: string[],
  otherFiles: string[]
): string {
  switch (section) {
    case 'comportamiento':
      return promptFiles.includes('system_prompt.md')
        ? 'system_prompt.md'
        : promptFiles[0] ?? 'system_prompt.md';
    case 'herramientas':
      return 'manifest.yaml';
    case 'contextos':
      return contextFiles[0] ?? 'system_prompt.md';
    case 'avanzado':
      return otherFiles[0] ?? 'manifest.yaml';
    default: {
      const _exhaustive: never = section;
      return _exhaustive;
    }
  }
}
