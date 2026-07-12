'use client';

import Link from 'next/link';
import { KeyRound } from 'lucide-react';

export type LlmGapPayload = {
  provider: string;
  integration_id?: string;
  label: string;
  message: string;
  admin_href: string;
};

type LlmSecretsBannerProps = {
  gap: LlmGapPayload | null | undefined;
  className?: string;
};

export function LlmSecretsBanner({ gap, className = '' }: LlmSecretsBannerProps) {
  if (!gap?.message) return null;

  return (
    <div
      className={`rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-950 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-100 ${className}`}
      role="status"
    >
      <p className="flex items-start gap-2">
        <KeyRound size={14} className="mt-0.5 shrink-0" aria-hidden />
        <span>{gap.message}</span>
      </p>
      <Link
        href={gap.admin_href || '/integraciones?tab=keys'}
        className="mt-2 inline-flex font-semibold text-gov-blue-800 underline-offset-2 hover:underline dark:text-dark-cyan"
      >
        Configurar {gap.label} →
      </Link>
    </div>
  );
}
