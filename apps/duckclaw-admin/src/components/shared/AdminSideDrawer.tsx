'use client';

import { useEffect, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';

type Props = {
  open: boolean;
  title: string;
  subtitle?: string;
  onClose: () => void;
  children: ReactNode;
  /** Ancho del panel (default 28rem). */
  widthClassName?: string;
};

/**
 * Drawer lateral derecho (Progressive Disclosure).
 * ESC / overlay cierran. Portal a body para no heredar overflow del main.
 */
export function AdminSideDrawer({
  open,
  title,
  subtitle,
  onClose,
  children,
  widthClassName = 'w-full max-w-md',
}: Props) {
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  if (!open || typeof document === 'undefined') return null;

  return createPortal(
    <div className="fixed inset-0 z-[180]" data-admin-side-drawer="true">
      <button
        type="button"
        className="absolute inset-0 bg-slate-900/50 backdrop-blur-[1px]"
        aria-label="Cerrar panel"
        onClick={onClose}
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-labelledby="admin-side-drawer-title"
        className={`absolute inset-y-0 right-0 flex ${widthClassName} flex-col border-l border-gov-gray-200 bg-white shadow-2xl dark:border-dark-border dark:bg-dark-surface`}
      >
        <header className="flex shrink-0 items-start justify-between gap-3 border-b border-gov-gray-100 px-5 py-4 dark:border-dark-border">
          <div className="min-w-0">
            <h2
              id="admin-side-drawer-title"
              className="truncate text-lg font-black text-gov-gray-900 dark:text-dark-text"
            >
              {title}
            </h2>
            {subtitle ? (
              <p className="mt-1 truncate font-mono text-xs text-gov-gray-500 dark:text-dark-muted">
                {subtitle}
              </p>
            ) : null}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-gov-gray-500 hover:bg-gov-gray-100 dark:hover:bg-dark-bg"
            aria-label="Cerrar"
          >
            <X size={18} />
          </button>
        </header>
        <div className="scrollbar-thin flex-1 overflow-y-auto px-5 py-4">{children}</div>
      </aside>
    </div>,
    document.body
  );
}
