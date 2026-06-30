'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { ChevronDown, Layers, Loader2, Search } from 'lucide-react';
import type { SkillCatalogItem } from '@/services/adminService';
import {
  applyReportsBundle,
  parseManifestSkills,
  reportsBundleFullySelected,
  toggleOptionalSkill,
} from '@/lib/manifestSkillsEdit';
import { parseManifestQuick } from '@/lib/manifestQuickEdit';
import {
  buildSkillCategories,
  normalizeSkillId,
  REPORTS_HTML_SKILLS,
  type SkillCategory,
  type SkillCategoryEntry,
} from '@/lib/skillCategories';
import { useSkillCategoriesCatalog } from '@/components/skills/useSkillCategoriesCatalog';

type WorkerToolsDropdownProps = {
  manifestYaml: string;
  onManifestChange: (nextYaml: string) => void;
  disabled?: boolean;
  workerId?: string;
  globalSkills?: SkillCatalogItem[];
  localSkills?: SkillCatalogItem[];
};

function CollapsibleCategory({
  title,
  description,
  countLabel,
  defaultOpen,
  children,
}: {
  title: string;
  description?: string;
  countLabel?: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen ?? false);
  return (
    <section className="rounded-xl border border-gov-gray-200/90 bg-white dark:border-dark-border dark:bg-[#1e1f20]">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left"
        aria-expanded={open}
      >
        <span>
          <span className="block text-xs font-bold text-gov-gray-800 dark:text-dark-text">{title}</span>
          {description ? (
            <span className="block text-[10px] text-gov-gray-500 dark:text-dark-muted">{description}</span>
          ) : null}
        </span>
        <span className="flex shrink-0 items-center gap-2">
          {countLabel ? (
            <span className="rounded-full bg-gov-gray-100 px-2 py-0.5 text-[10px] font-bold text-gov-gray-600 dark:bg-dark-bg dark:text-dark-muted">
              {countLabel}
            </span>
          ) : null}
          <ChevronDown
            size={14}
            className={`text-gov-gray-400 transition-transform dark:text-dark-muted ${
              open ? 'rotate-0' : '-rotate-90'
            }`}
            aria-hidden
          />
        </span>
      </button>
      {open ? (
        <div className="max-h-48 space-y-0.5 overflow-y-auto border-t border-gov-gray-100 px-1 py-1 dark:border-dark-border">
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
  if (readOnly) {
    return (
      <div className="flex items-start gap-2 rounded-lg px-2 py-1.5">
        <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-gov-gray-300 dark:bg-dark-muted" />
        <span>
          <span className="block font-mono text-[11px] font-bold text-gov-gray-600 dark:text-dark-muted">
            {entry.label}
          </span>
          {entry.hint ? (
            <span className="block text-[10px] text-gov-gray-400 dark:text-dark-muted">{entry.hint}</span>
          ) : null}
        </span>
      </div>
    );
  }
  return (
    <label className="flex cursor-pointer items-start gap-2 rounded-lg px-2 py-1.5 hover:bg-gov-gray-50 dark:hover:bg-dark-bg/80">
      <input
        type="checkbox"
        className="mt-1"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange?.(e.target.checked)}
      />
      <span>
        <span className="block font-mono text-[11px] font-bold text-gov-gray-800 dark:text-dark-text">
          {entry.label}
        </span>
        {entry.hint ? (
          <span className="block text-[10px] text-gov-gray-500 dark:text-dark-muted">{entry.hint}</span>
        ) : null}
      </span>
    </label>
  );
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
  if (!needle && category.readOnly) return { ...category, skills };
  if (skills.length === 0) return null;
  if (category.readOnly) {
    return { ...category, skills: skills.length ? skills : category.skills };
  }
  const activeCount = skills.filter((entry) => selected.has(normalizeSkillId(entry.id))).length;
  return {
    ...category,
    skills,
    title:
      activeCount > 0 && !category.readOnly
        ? `${category.title} (${activeCount}/${skills.length})`
        : category.title,
  };
}

export function WorkerToolsDropdown({
  manifestYaml,
  onManifestChange,
  disabled,
  workerId,
  globalSkills = [],
  localSkills = [],
}: WorkerToolsDropdownProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const panelRef = useRef<HTMLDivElement>(null);
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

  const patchSkill = (skillId: string, enabled: boolean) => {
    onManifestChange(toggleOptionalSkill(manifestYaml, skillId, enabled));
  };

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent) => {
      if (!panelRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onPointerDown);
    return () => document.removeEventListener('mousedown', onPointerDown);
  }, [open]);

  return (
    <div ref={panelRef} className="relative">
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen((value) => !value)}
        className="inline-flex items-center gap-2 rounded-xl border border-gov-gray-200 bg-white px-3 py-2 text-xs font-bold text-gov-gray-800 hover:bg-gov-gray-50 disabled:opacity-50 dark:border-dark-border dark:bg-dark-surface dark:text-dark-text dark:hover:bg-dark-bg"
        aria-expanded={open}
        aria-haspopup="dialog"
      >
        <Layers size={14} className="text-gov-blue-700 dark:text-dark-cyan" />
        Herramientas
        <span className="rounded-full bg-gov-blue-50 px-2 py-0.5 text-[10px] font-black text-gov-blue-800 dark:bg-gov-blue-950/40 dark:text-gov-blue-200">
          {activeOptionalCount} activa{activeOptionalCount === 1 ? '' : 's'}
        </span>
        <ChevronDown
          size={14}
          className={`text-gov-gray-400 transition-transform ${open ? 'rotate-180' : ''}`}
        />
      </button>

      {open ? (
        <div className="absolute right-0 z-30 mt-2 w-[min(100vw-2rem,28rem)] rounded-2xl border border-gov-gray-200 bg-white p-3 shadow-xl dark:border-dark-border dark:bg-dark-surface">
          <p className="text-[11px] text-gov-gray-500 dark:text-dark-muted">
            Cambios en memoria hasta pulsar Guardar.
          </p>

          {categoriesError ? (
            <p className="mt-2 rounded-lg bg-amber-50 px-2 py-1 text-[10px] text-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
              Catálogo DuckDB no disponible; usando categorías por defecto. {categoriesError}
            </p>
          ) : null}

          <div className="mt-2 flex flex-wrap gap-2">
            <button
              type="button"
              disabled={disabled}
              onClick={() => onManifestChange(applyReportsBundle(manifestYaml, !reportsSelected))}
              className="rounded-lg border border-gov-gray-200 px-2.5 py-1 text-[10px] font-bold text-gov-gray-700 hover:bg-gov-gray-50 disabled:opacity-50 dark:border-dark-border dark:text-dark-text dark:hover:bg-dark-bg"
            >
              {reportsSelected ? 'Quitar paquete Reportes' : 'Paquete Reportes HTML'}
            </button>
            <span className="self-center text-[9px] text-gov-gray-400 dark:text-dark-muted">
              {REPORTS_HTML_SKILLS.join(', ')}
            </span>
          </div>

          <label className="relative mt-2 block">
            <Search
              size={14}
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-gov-gray-400"
            />
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Buscar skill…"
              className="w-full rounded-xl border border-gov-gray-200 bg-gov-gray-50 py-2 pl-9 pr-3 text-sm dark:border-dark-border dark:bg-dark-bg"
            />
          </label>

          {categoriesLoading ? (
            <p className="mt-3 flex items-center gap-2 text-[11px] text-gov-gray-500 dark:text-dark-muted">
              <Loader2 size={14} className="animate-spin" />
              Cargando categorías…
            </p>
          ) : (
            <div className="mt-2 max-h-[min(60vh,24rem)] space-y-2 overflow-y-auto">
              {categories.map((category) => (
                <CollapsibleCategory
                  key={category.id}
                  title={category.title}
                  description={category.description}
                  defaultOpen={category.id === 'web' || category.id === 'reports_html'}
                  countLabel={
                    category.readOnly
                      ? `${category.skills.length} incluidas`
                      : `${category.skills.filter((entry) => selected.has(normalizeSkillId(entry.id))).length}/${category.skills.length}`
                  }
                >
                  {category.skills.map((entry) => (
                    <SkillCheckboxRow
                      key={entry.id}
                      entry={entry}
                      checked={
                        category.readOnly ? true : selected.has(normalizeSkillId(entry.id))
                      }
                      disabled={disabled}
                      readOnly={category.readOnly}
                      onChange={(enabled) => patchSkill(entry.id, enabled)}
                    />
                  ))}
                </CollapsibleCategory>
              ))}
              {categories.length === 0 ? (
                <p className="text-[11px] text-gov-gray-500 dark:text-dark-muted">Sin coincidencias.</p>
              ) : null}
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}
