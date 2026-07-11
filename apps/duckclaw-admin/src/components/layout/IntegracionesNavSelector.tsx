'use client';

import Link from 'next/link';
import { usePathname, useSearchParams } from 'next/navigation';
import { useEffect, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import {
  INTEGRACIONES_TABS,
  isIntegracionesPath,
  parseIntegracionesTab,
  integracionesTabHref,
} from '@/config/integracionesNav';
import { cn } from '@/lib/utils';
import type { LucideIcon } from 'lucide-react';

type Props = {
  icon: LucideIcon;
  label: string;
  onNavigate?: () => void;
};

export function IntegracionesNavSelector({ icon: Icon, label, onNavigate }: Props) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const activeTab = parseIntegracionesTab(searchParams.get('tab'));
  const hubActive = isIntegracionesPath(pathname);
  const [open, setOpen] = useState(hubActive);

  useEffect(() => {
    if (hubActive) setOpen(true);
  }, [hubActive]);

  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className={cn(
          'w-full flex items-center gap-3 px-3 py-2 text-sm font-medium rounded-xl transition-colors',
          hubActive
            ? 'bg-white text-gov-blue-900 shadow-sm dark:bg-dark-surface dark:text-dark-text'
            : 'text-gov-gray-300 hover:bg-gov-blue-700/40 hover:text-white'
        )}
      >
        <Icon size={18} />
        <span className="flex-1 text-left">{label}</span>
        <ChevronDown size={14} className={cn('shrink-0 transition-transform', open && 'rotate-180')} />
      </button>
      {open && (
        <div className="ml-7 mt-1 space-y-0.5 border-l border-white/10 pl-3">
          {INTEGRACIONES_TABS.map((tab) => {
            const childActive = hubActive && activeTab === tab.id;
            return (
              <Link
                key={tab.id}
                href={integracionesTabHref(tab.id)}
                onClick={() => onNavigate?.()}
                className={cn(
                  'block rounded-lg px-2 py-1.5 text-xs font-semibold transition-colors',
                  childActive
                    ? 'bg-gov-blue-700/80 text-white'
                    : 'text-gov-gray-300 hover:bg-gov-blue-700/40 hover:text-white'
                )}
              >
                {tab.label}
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
