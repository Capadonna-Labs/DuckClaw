'use client';

import { useCallback, useMemo, useState } from 'react';
import { ChevronsDownUp, ChevronsUpDown, Loader2, Search } from 'lucide-react';
import type { SkillCatalogItem } from '@/services/adminService';
import {
  applyReportsBundle,
  parseManifestSkills,
  reportsBundleFullySelected,
  toggleOptionalSkill,
} from '@/lib/manifestSkillsEdit';
import {
  buildSkillCategories,
  normalizeSkillId,
  REPORTS_HTML_SKILLS,
  type SkillCategory,
  type SkillCategoryEntry,
} from '@/lib/skillCategories';
import { useSkillCategoriesCatalog } from '@/components/skills/useSkillCategoriesCatalog';

type WorkerSkillPickerPanelProps = {
  manifestYaml: string;
  onManifestChange: (nextYaml: string) => void;
  disabled?: boolean;
  workerId?: string;
  globalSkills?: SkillCatalogItem[];
  localSkills?: SkillCatalogItem[];
  compact?: boolean;
};

function CollapsibleCategory({
  title,
  description,
  countLabel,
  open,
  onToggle,
  children,
}: {
  title: string;
  description?: string;
  countLabel?: string;
  open: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-xl border border-gov-gray-200 bg-white dark:border-dark-border dark:bg-dark-surface">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left"
        aria-expanded={open}
      >
        <span>
          <span className="block text-xs font-semibold text-gov-gray-800 dark:text-dark-text">{title}</span>
          {description ? (
            <span className="block text-[10px] text-gov-gray-500 dark:text-dark-muted">{description}</span>
          ) : null}
        </span>
        {countLabel ? (
          <span className="rounded-full bg-gov-gray-100 px-2 py-0.5 text-[10px] font-semibold text-gov-gray-600 dark:bg-dark-bg dark:text-dark-muted">
            {countLabel}
          </span>
        ) : null}
      </button>
      {open ? (
        <div className="max-h-52 space-y-0.5 overflow-y-auto border-t border-gov-gray-100 px-1 py-1 dark:border-dark-border">
          {children}
        </div>
      ) : null}
    </section>
  );
}

function SkillCheckboxRow({
  entry,
  checked,
  disabled,
  readOnly,
  onChange,
}: {
  entry: SkillCategoryEntry;
  checked: boolean;
  disabled?: boolean;
  readOnly?: boolean;
  onChange?: (enabled: boolean) => void;
}) {
  const locked = Boolean(readOnly);
  return (
    <label
      className={`flex items-start gap-2 rounded-lg px-2 py-1.5 ${
        locked
          ? 'cursor-default opacity-80'
          : 'cursor-pointer hover:bg-gov-gray-50 dark:hover:bg-dark-bg/80'
      }`}
    >
      <input
        type="checkbox"
        className="mt-1"
        checked={checked}
        disabled={disabled || locked}
        onChange={(e) => onChange?.(e.target.checked)}
      />
      <span>
        <span className="block font-mono text-[11px] font-semibold text-gov-gray-800 dark:text-dark-text">
          {entry.label}
        </span>
        {entry.hint ? (
          <span className="block text-[10px] text-gov-gray-500 dark:text-dark-muted">{entry.hint}</span>
        ) : null}
        {locked ? (
          <span className="block text-[10px] text-gov-gray-400 dark:text-dark-muted">
            Incluida por el perfil de herramientas
          </span>
        ) : null}
      </span>
    </label>
  );
}

function isBaselineCategory(category: SkillCategory): boolean {
  return category.id === 'baseline';
}

function filterCategory(
  category: SkillCategory,
  query: string,
  selected: Set<string>
): SkillCategory | null {
  const needle = query.trim().toLowerCase();
  const skills = category.skills.filter((entry) => {
    if (!needle) return true;
    return (
      entry.id.toLowerCase().includes(needle) ||
      entry.label.toLowerCase().includes(needle) ||
      (entry.hint ?? '').toLowerCase().includes(needle)
    );
  });
  if (skills.length === 0) return null;
  const baseline = isBaselineCategory(category);
  const activeCount = baseline
    ? skills.length
    : skills.filter((entry) => selected.has(normalizeSkillId(entry.id))).length;
  return {
    ...category,
    skills,
    title:
      activeCount > 0 && !baseline
        ? `${category.title} (${activeCount}/${skills.length})`
        : category.title,
  };
}

export function WorkerSkillPickerPanel({
  manifestYaml,
  onManifestChange,
  disabled,
  workerId,
  globalSkills = [],
  localSkills = [],
  compact = false,
}: WorkerSkillPickerPanelProps) {
  const [query, setQuery] = useState('');
  const { platformCategories, baselineProfiles, loading: categoriesLoading, error: categoriesError } =
    useSkillCategoriesCatalog();

  const parsed = useMemo(() => parseManifestSkills(manifestYaml), [manifestYaml]);
  const selected = useMemo(
    () => new Set(parsed.optionalSkillNames.map(normalizeSkillId)),
    [parsed.optionalSkillNames]
  );

  const categories = useMemo(() => {
    const all = buildSkillCategories(
      manifestYaml,
      globalSkills,
      localSkills,
      workerId,
      platformCategories,
      baselineProfiles
    );
    return all
      .map((category) => filterCategory(category, query, selected))
      .filter((category): category is SkillCategory => category !== null);
  }, [manifestYaml, globalSkills, localSkills, workerId, platformCategories, baselineProfiles, query, selected]);

  const activeOptionalCount = parsed.optionalSkillNames.length;
  const reportsSelected = reportsBundleFullySelected(manifestYaml);
  const [openCategories, setOpenCategories] = useState<Record<string, boolean>>({ baseline: true });

  const toggleCategory = useCallback((id: string) => {
    setOpenCategories((prev) => ({ ...prev, [id]: !prev[id] }));
  }, []);

  const allExpanded = categories.length > 0 && categories.every((c) => openCategories[c.id]);

  const toggleAll = useCallback(() => {
    if (allExpanded) {
      setOpenCategories({});
    } else {
      const next: Record<string, boolean> = {};
      for (const c of categories) next[c.id] = true;
      setOpenCategories(next);
    }
  }, [allExpanded, categories]);

  const patchSkill = (skillId: string, enabled: boolean) => {
    onManifestChange(toggleOptionalSkill(manifestYaml, skillId, enabled));
  };

  return (
    <section className={`space-y-3 ${compact ? '' : 'rounded-xl border border-gov-gray-200 p-4 dark:border-dark-border dark:bg-dark-surface'}`}>
      {!compact && (
        <div>
          <h3 className="text-sm font-semibold text-gov-gray-900 dark:text-dark-text">Skills opcionales</h3>
          <p className="mt-0.5 text-xs text-gov-gray-500 dark:text-dark-muted">
            {activeOptionalCount} activa{activeOptionalCount === 1 ? '' : 's'} · baseline según perfil
          </p>
        </div>
      )}

      {categoriesError ? (
        <p className="rounded-lg bg-amber-50 px-2 py-1 text-[10px] text-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
          Catálogo no disponible; usando fallback. {categoriesError}
        </p>
      ) : null}

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={disabled}
          onClick={() => onManifestChange(applyReportsBundle(manifestYaml, !reportsSelected))}
          className="rounded-lg border border-gov-gray-200 px-2.5 py-1 text-[10px] font-semibold dark:border-dark-border disabled:opacity-50"
        >
          {reportsSelected ? 'Quitar reportes HTML' : 'Paquete reportes HTML'}
        </button>
        <span className="self-center text-[9px] text-gov-gray-400">{REPORTS_HTML_SKILLS.join(', ')}</span>
      </div>

      <label className="relative block">
        <Search
          size={14}
          className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-gov-gray-400"
        />
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Buscar skill…"
          className="w-full rounded-lg border border-gov-gray-200 bg-gov-gray-50 py-2 pl-9 pr-3 text-sm dark:border-dark-border dark:bg-dark-bg"
        />
      </label>

      {categoriesLoading ? (
        <p className="flex items-center gap-2 text-[11px] text-gov-gray-500">
          <Loader2 size={14} className="animate-spin" />
          Cargando categorías…
        </p>
      ) : (
        <>
          {categories.length > 0 ? (
            <button
              type="button"
              onClick={toggleAll}
              className="inline-flex items-center gap-1.5 text-[10px] font-semibold text-gov-gray-500 hover:text-gov-gray-700"
            >
              {allExpanded ? <ChevronsDownUp size={12} /> : <ChevronsUpDown size={12} />}
              {allExpanded ? 'Colapsar todo' : 'Expandir todo'}
            </button>
          ) : null}
          <div className="space-y-2">
            {categories.map((category) => {
              const baseline = isBaselineCategory(category);
              const activeCount = baseline
                ? category.skills.length
                : category.skills.filter((entry) => selected.has(normalizeSkillId(entry.id))).length;
              return (
                <CollapsibleCategory
                  key={category.id}
                  title={category.title}
                  description={category.description}
                  open={!!openCategories[category.id]}
                  onToggle={() => toggleCategory(category.id)}
                  countLabel={
                    baseline ? `${category.skills.length} incluidas` : `${activeCount}/${category.skills.length}`
                  }
                >
                  {category.skills.map((entry) => (
                    <SkillCheckboxRow
                      key={entry.id}
                      entry={entry}
                      checked={baseline ? true : selected.has(normalizeSkillId(entry.id))}
                      disabled={disabled}
                      readOnly={baseline}
                      onChange={(enabled) => patchSkill(entry.id, enabled)}
                    />
                  ))}
                </CollapsibleCategory>
              );
            })}
            {categories.length === 0 ? (
              <p className="text-[11px] text-gov-gray-500">Sin coincidencias.</p>
            ) : null}
          </div>
        </>
      )}
    </section>
  );
}
