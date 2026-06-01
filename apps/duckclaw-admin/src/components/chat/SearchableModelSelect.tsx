'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { ChevronDown, Search } from 'lucide-react';

export type SearchableModelOption = { value: string; label: string };

type Props = {
  id?: string;
  value: string;
  options: SearchableModelOption[];
  onChange: (value: string) => void;
  disabled?: boolean;
  compact?: boolean;
  allowCustom?: boolean;
  placeholder?: string;
  searchPlaceholder?: string;
  className?: string;
  'aria-label'?: string;
};

type MenuCoords = { top: number; left: number; width: number };

export function SearchableModelSelect({
  id,
  value,
  options,
  onChange,
  disabled,
  compact,
  allowCustom,
  placeholder = 'Elegir modelo',
  searchPlaceholder = 'Buscar…',
  className,
  'aria-label': ariaLabel,
}: Props) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [coords, setCoords] = useState<MenuCoords | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  const selected = options.find((o) => o.value === value);
  const displayLabel = selected?.label ?? (value.trim() || placeholder);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return options;
    return options.filter(
      (o) =>
        o.value.toLowerCase().includes(q) ||
        o.label.toLowerCase().includes(q)
    );
  }, [options, query]);

  const customCandidate = useMemo(() => {
    if (!allowCustom) return null;
    const q = query.trim();
    if (!q) return null;
    if (options.some((o) => o.value === q)) return null;
    return q;
  }, [allowCustom, query, options]);

  const openMenu = () => {
    if (disabled) return;
    const el = triggerRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const width = Math.max(r.width, compact ? 220 : 260);
    const left = Math.min(r.left, window.innerWidth - width - 8);
    setCoords({ top: r.bottom + 4, left: Math.max(8, left), width });
    setOpen(true);
  };

  const closeMenu = () => {
    setOpen(false);
    setQuery('');
    setCoords(null);
  };

  const pick = (next: string) => {
    if (next && next !== value) onChange(next);
    closeMenu();
  };

  useEffect(() => {
    if (!open) return;
    const t = window.setTimeout(() => searchRef.current?.focus(), 0);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeMenu();
    };
    const onPointer = (e: MouseEvent | TouchEvent) => {
      const target = e.target as Node;
      if (rootRef.current?.contains(target) || panelRef.current?.contains(target)) return;
      closeMenu();
    };
    window.addEventListener('keydown', onKey);
    document.addEventListener('mousedown', onPointer);
    document.addEventListener('touchstart', onPointer);
    return () => {
      window.clearTimeout(t);
      window.removeEventListener('keydown', onKey);
      document.removeEventListener('mousedown', onPointer);
      document.removeEventListener('touchstart', onPointer);
    };
  }, [open]);

  const triggerCls = [
    'flex items-center justify-between gap-1 border rounded-lg dark:border-dark-border dark:bg-dark-bg disabled:opacity-50 text-left',
    compact ? 'text-[10px] px-1.5 py-1 max-w-[120px]' : 'text-xs px-2 py-1.5 max-w-[160px]',
    className ?? '',
  ].join(' ');

  return (
    <div ref={rootRef} className="relative">
      <button
        ref={triggerRef}
        type="button"
        id={id}
        disabled={disabled}
        onClick={() => (open ? closeMenu() : openMenu())}
        className={triggerCls}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={ariaLabel}
        title={value.trim() || undefined}
      >
        <span className="truncate">{displayLabel}</span>
        <ChevronDown size={compact ? 10 : 12} className="shrink-0 opacity-60" aria-hidden />
      </button>

      {open && coords && (
        <div
          ref={panelRef}
          role="listbox"
          aria-label={ariaLabel}
          className="fixed z-[9999] rounded-lg border shadow-lg dark:border-dark-border dark:bg-dark-bg bg-white"
          style={{ top: coords.top, left: coords.left, width: coords.width }}
        >
          <div className="flex items-center gap-1.5 border-b px-2 py-1.5 dark:border-dark-border">
            <Search size={compact ? 12 : 14} className="shrink-0 opacity-50" aria-hidden />
            <input
              ref={searchRef}
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  const first = filtered[0];
                  if (first) pick(first.value);
                  else if (customCandidate) pick(customCandidate);
                }
              }}
              placeholder={searchPlaceholder}
              className={`w-full bg-transparent outline-none placeholder:text-gov-gray-400 dark:placeholder:text-dark-muted ${
                compact ? 'text-[10px]' : 'text-xs'
              }`}
              aria-label="Buscar modelo"
            />
          </div>
          <ul className={`max-h-52 overflow-y-auto py-1 ${compact ? 'text-[10px]' : 'text-xs'}`}>
            {filtered.map((o) => {
              const active = o.value === value;
              return (
                <li key={o.value}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={active}
                    onClick={() => pick(o.value)}
                    className={`w-full px-2 py-1.5 text-left hover:bg-gov-gray-100 dark:hover:bg-dark-border/40 ${
                      active ? 'bg-gov-blue-50 dark:bg-dark-border/30 font-medium' : ''
                    }`}
                  >
                    <span className="block truncate">{o.label}</span>
                    <span className="block truncate font-mono text-[9px] text-gov-gray-500 dark:text-dark-muted">
                      {o.value}
                    </span>
                  </button>
                </li>
              );
            })}
            {customCandidate && (
              <li>
                <button
                  type="button"
                  role="option"
                  onClick={() => pick(customCandidate)}
                  className="w-full px-2 py-1.5 text-left hover:bg-gov-gray-100 dark:hover:bg-dark-border/40 border-t dark:border-dark-border"
                >
                  <span className="block text-gov-blue-700 dark:text-dark-cyan">Usar slug personalizado</span>
                  <span className="block truncate font-mono text-[9px] text-gov-gray-500 dark:text-dark-muted">
                    {customCandidate}
                  </span>
                </button>
              </li>
            )}
            {filtered.length === 0 && !customCandidate && (
              <li className="px-2 py-2 text-gov-gray-500 dark:text-dark-muted">Sin resultados</li>
            )}
          </ul>
        </div>
      )}
    </div>
  );
}
