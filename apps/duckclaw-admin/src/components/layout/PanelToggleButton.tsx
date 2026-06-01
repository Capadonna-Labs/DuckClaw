'use client';

import type { LucideIcon } from 'lucide-react';
import { cn } from '@/lib/utils';

type PanelToggleButtonProps = {
  open: boolean;
  onToggle: () => void;
  openLabel: string;
  closedLabel: string;
  openIcon: LucideIcon;
  closedIcon: LucideIcon;
  title?: string;
  iconOnly?: boolean;
  className?: string;
};

/** Botón unificado para colapsar paneles (nav izquierdo, panel derecho Playground). */
export function PanelToggleButton({
  open,
  onToggle,
  openLabel,
  closedLabel,
  openIcon: OpenIcon,
  closedIcon: ClosedIcon,
  title,
  iconOnly,
  className,
}: PanelToggleButtonProps) {
  const Icon = open ? OpenIcon : ClosedIcon;
  const label = open ? openLabel : closedLabel;

  return (
    <button
      type="button"
      onClick={onToggle}
      aria-label={label}
      title={title ?? label}
      className={cn(
        'inline-flex items-center rounded-lg text-xs font-semibold',
        iconOnly ? 'justify-center p-2' : 'gap-1.5 px-3 py-2 rounded-xl border',
        !iconOnly && 'border-gov-gray-200 dark:border-dark-border',
        'text-gov-gray-600 dark:text-dark-muted',
        'hover:bg-gov-gray-50 dark:hover:bg-dark-bg transition-colors',
        className
      )}
    >
      <Icon size={16} aria-hidden />
      {!iconOnly && label}
    </button>
  );
}
