'use client';

import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import { Check, ChevronDown, Search } from 'lucide-react';
import { trimStr } from '@/lib/utils';

export type SearchableGroupedOption = {
  value: string;
  label: string;
  meta?: string;
  disabled?: boolean;
};

export type SearchableGroupedSection = {
  id: string;
  label: string;
  options: SearchableGroupedOption[];
};

type MenuCoords = { top: number; left: number; width: number };

type FlatRow =
  | { kind: 'header'; key: string; label: string; count: number }
  | { kind: 'option'; key: string; option: SearchableGroupedOption; ordinal: number };

type Props = {
  id?: string;
  value: string;
  groups: SearchableGroupedSection[];
  onChange: (value: string) => void;
  disabled?: boolean;
  placeholder?: string;
  searchPlaceholder?: string;
  emptyLabel?: string;
  className?: string;
  'aria-label'?: string;
};

const HEADER_H = 28;
const OPTION_H = 48;
const VIEWPORT_H = 288; // max-h-72
const OVERSCAN = 4;

function rowHeight(row: FlatRow): number {
  return row.kind === 'header' ? HEADER_H : OPTION_H;
}

/**
 * Combobox con búsqueda, grupos y lista virtualizada.
 * Panel `fixed` anclado al trigger (se reposiciona con scroll del admin).
 */
export function SearchableGroupedSelect({
  id,
  value,
  groups,
  onChange,
  disabled,
  placeholder = 'Elegir…',
  searchPlaceholder = 'Buscar…',
  emptyLabel = 'Sin resultados',
  className,
  'aria-label': ariaLabel,
}: Props) {
  const listId = useId();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [coords, setCoords] = useState<MenuCoords | null>(null);
  const [activeIndex, setActiveIndex] = useState(0);
  const [scrollTop, setScrollTop] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const flatOptions = useMemo(
    () => groups.flatMap((group) => group.options),
    [groups]
  );

  const selected = flatOptions.find((option) => option.value === value);
  const displayLabel = selected?.label ?? (trimStr(value) || placeholder);

  const filteredGroups = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return groups;
    return groups
      .map((group) => ({
        ...group,
        options: group.options.filter((option) => {
          const hay = `${option.label} ${option.value} ${option.meta || ''}`.toLowerCase();
          return hay.includes(q);
        }),
      }))
      .filter((group) => group.options.length > 0);
  }, [groups, query]);

  const filteredFlat = useMemo(
    () => filteredGroups.flatMap((group) => group.options),
    [filteredGroups]
  );

  const rows = useMemo(() => {
    const out: FlatRow[] = [];
    let ordinal = 0;
    for (const group of filteredGroups) {
      out.push({
        kind: 'header',
        key: `h:${group.id}`,
        label: group.label,
        count: group.options.length,
      });
      for (const option of group.options) {
        out.push({
          kind: 'option',
          key: `o:${option.value}`,
          option,
          ordinal: ordinal++,
        });
      }
    }
    return out;
  }, [filteredGroups]);

  const rowOffsets = useMemo(() => {
    const offsets: number[] = [];
    let acc = 0;
    for (const row of rows) {
      offsets.push(acc);
      acc += rowHeight(row);
    }
    return { offsets, totalHeight: acc };
  }, [rows]);

  const virtualWindow = useMemo(() => {
    const { offsets, totalHeight } = rowOffsets;
    if (rows.length === 0) {
      return { start: 0, end: 0, topPad: 0, totalHeight: 0, slice: [] as FlatRow[] };
    }
    let start = 0;
    while (start < rows.length && offsets[start]! + rowHeight(rows[start]!) < scrollTop) {
      start += 1;
    }
    start = Math.max(0, start - OVERSCAN);
    let end = start;
    const limit = scrollTop + VIEWPORT_H;
    while (end < rows.length && offsets[end]! < limit) {
      end += 1;
    }
    end = Math.min(rows.length, end + OVERSCAN);
    return {
      start,
      end,
      topPad: offsets[start] ?? 0,
      totalHeight,
      slice: rows.slice(start, end),
    };
  }, [rows, rowOffsets, scrollTop]);

  const syncPosition = useCallback(() => {
    const el = triggerRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    setCoords({
      top: Math.round(rect.bottom) - 1,
      left: Math.round(rect.left),
      width: Math.round(rect.width),
    });
  }, []);

  const openMenu = () => {
    if (disabled) return;
    syncPosition();
    setOpen(true);
    setActiveIndex(0);
    setScrollTop(0);
  };

  const closeMenu = () => {
    setOpen(false);
    setQuery('');
    setCoords(null);
    setActiveIndex(0);
    setScrollTop(0);
  };

  const pick = (next: string, optionDisabled?: boolean) => {
    if (optionDisabled) return;
    if (next && next !== value) onChange(next);
    closeMenu();
  };

  const scrollActiveIntoView = useCallback(
    (index: number) => {
      const optionRow = rows.findIndex(
        (row) => row.kind === 'option' && row.ordinal === index
      );
      if (optionRow < 0 || !listRef.current) return;
      const top = rowOffsets.offsets[optionRow] ?? 0;
      const bottom = top + OPTION_H;
      const viewTop = listRef.current.scrollTop;
      const viewBottom = viewTop + VIEWPORT_H;
      if (top < viewTop) listRef.current.scrollTop = top;
      else if (bottom > viewBottom) listRef.current.scrollTop = bottom - VIEWPORT_H;
    },
    [rows, rowOffsets.offsets]
  );

  useEffect(() => {
    if (!open) return;
    syncPosition();
    const scrollRoot = document.getElementById('admin-main-scroll');
    const onScrollOrResize = () => syncPosition();
    scrollRoot?.addEventListener('scroll', onScrollOrResize, { passive: true });
    window.addEventListener('resize', onScrollOrResize);
    window.addEventListener('scroll', onScrollOrResize, true);
    return () => {
      scrollRoot?.removeEventListener('scroll', onScrollOrResize);
      window.removeEventListener('resize', onScrollOrResize);
      window.removeEventListener('scroll', onScrollOrResize, true);
    };
  }, [open, syncPosition]);

  useEffect(() => {
    if (!open) return;
    const focusTimer = window.setTimeout(() => searchRef.current?.focus(), 0);
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        closeMenu();
        return;
      }
      if (event.key === 'ArrowDown') {
        event.preventDefault();
        setActiveIndex((prev) => {
          const next = Math.min(prev + 1, Math.max(filteredFlat.length - 1, 0));
          queueMicrotask(() => scrollActiveIntoView(next));
          return next;
        });
        return;
      }
      if (event.key === 'ArrowUp') {
        event.preventDefault();
        setActiveIndex((prev) => {
          const next = Math.max(prev - 1, 0);
          queueMicrotask(() => scrollActiveIntoView(next));
          return next;
        });
        return;
      }
      if (event.key === 'Enter') {
        event.preventDefault();
        const option = filteredFlat[activeIndex];
        if (option) pick(option.value, option.disabled);
      }
    };
    const onPointer = (event: MouseEvent | TouchEvent) => {
      const target = event.target as Node;
      if (rootRef.current?.contains(target) || panelRef.current?.contains(target)) return;
      closeMenu();
    };
    window.addEventListener('keydown', onKey);
    document.addEventListener('mousedown', onPointer);
    document.addEventListener('touchstart', onPointer);
    return () => {
      window.clearTimeout(focusTimer);
      window.removeEventListener('keydown', onKey);
      document.removeEventListener('mousedown', onPointer);
      document.removeEventListener('touchstart', onPointer);
    };
  }, [open, filteredFlat, activeIndex, value, scrollActiveIntoView]);

  useEffect(() => {
    setActiveIndex(0);
    setScrollTop(0);
    if (listRef.current) listRef.current.scrollTop = 0;
  }, [query]);

  return (
    <div ref={rootRef} className={`relative ${className || ''}`.trim()}>
      <button
        ref={triggerRef}
        type="button"
        id={id}
        disabled={disabled}
        onClick={() => (open ? closeMenu() : openMenu())}
        className={`flex w-full min-h-[2.5rem] items-center justify-between gap-2 border border-gov-gray-200 bg-white px-3 py-2 text-left text-sm dark:border-dark-border dark:bg-dark-bg disabled:opacity-50 ${
          open ? 'rounded-t-xl rounded-b-none border-b-transparent relative z-[10000]' : 'rounded-xl'
        }`}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        aria-label={ariaLabel}
        title={selected?.label || undefined}
      >
        <span className="min-w-0 truncate">
          <span className="block truncate font-medium text-gov-gray-900 dark:text-dark-text">
            {displayLabel}
          </span>
          {selected?.meta ? (
            <span className="block truncate text-xs text-gov-gray-500 dark:text-dark-muted">
              {selected.meta}
            </span>
          ) : null}
        </span>
        <ChevronDown size={16} className="shrink-0 opacity-60" aria-hidden />
      </button>

      {open && coords ? (
        <div
          ref={panelRef}
          id={listId}
          role="listbox"
          aria-label={ariaLabel}
          className="fixed z-[9999] overflow-hidden rounded-b-xl rounded-t-none border border-t-0 border-gov-gray-200 bg-white shadow-lg dark:border-dark-border dark:bg-dark-bg"
          style={{ top: coords.top, left: coords.left, width: coords.width }}
        >
          <div className="flex items-center gap-2 border-b border-gov-gray-100 px-3 py-2 dark:border-dark-border">
            <Search size={14} className="shrink-0 opacity-50" aria-hidden />
            <input
              ref={searchRef}
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={searchPlaceholder}
              className="w-full bg-transparent text-sm outline-none placeholder:text-gov-gray-400 dark:placeholder:text-dark-muted"
              aria-label={searchPlaceholder}
              autoComplete="off"
            />
          </div>
          <div
            ref={listRef}
            className="scrollbar-thin overflow-y-auto"
            style={{ height: VIEWPORT_H }}
            onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)}
            data-virtualized="true"
          >
            {filteredFlat.length === 0 ? (
              <p className="px-3 py-3 text-sm text-gov-gray-500 dark:text-dark-muted">{emptyLabel}</p>
            ) : (
              <div style={{ height: virtualWindow.totalHeight, position: 'relative' }}>
                <div style={{ transform: `translateY(${virtualWindow.topPad}px)` }}>
                  {virtualWindow.slice.map((row) => {
                    if (row.kind === 'header') {
                      return (
                        <div
                          key={row.key}
                          role="presentation"
                          className="flex items-center bg-gov-gray-50 px-3 text-[10px] font-bold uppercase tracking-wide text-gov-gray-500 dark:bg-dark-bg dark:text-dark-muted"
                          style={{ height: HEADER_H }}
                        >
                          {row.label}
                          <span className="ml-1 font-normal normal-case opacity-70">
                            ({row.count})
                          </span>
                        </div>
                      );
                    }
                    const { option, ordinal } = row;
                    const active = option.value === value;
                    const highlighted = ordinal === activeIndex;
                    return (
                      <button
                        key={row.key}
                        type="button"
                        role="option"
                        aria-selected={active}
                        disabled={option.disabled}
                        onMouseEnter={() => setActiveIndex(ordinal)}
                        onClick={() => pick(option.value, option.disabled)}
                        className={`flex w-full items-start gap-2 px-3 text-left text-sm disabled:cursor-not-allowed disabled:opacity-50 ${
                          highlighted
                            ? 'bg-gov-blue-50 dark:bg-dark-border/40'
                            : 'hover:bg-gov-gray-50 dark:hover:bg-dark-border/30'
                        } ${active ? 'font-semibold' : ''}`}
                        style={{ height: OPTION_H }}
                      >
                        <span className="mt-0.5 w-4 shrink-0">
                          {active ? (
                            <Check size={14} className="text-gov-blue-700 dark:text-dark-cyan" />
                          ) : null}
                        </span>
                        <span className="min-w-0 flex-1 py-1">
                          <span className="block truncate text-gov-gray-900 dark:text-dark-text">
                            {option.label}
                          </span>
                          {option.meta ? (
                            <span className="block truncate text-xs text-gov-gray-500 dark:text-dark-muted">
                              {option.meta}
                            </span>
                          ) : null}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
          <div className="border-t border-gov-gray-100 px-3 py-1.5 text-[10px] text-gov-gray-400 dark:border-dark-border dark:text-dark-muted">
            {filteredFlat.length} de {flatOptions.length} · virtualizado · ↑↓ Enter · Esc
          </div>
        </div>
      ) : null}
    </div>
  );
}
