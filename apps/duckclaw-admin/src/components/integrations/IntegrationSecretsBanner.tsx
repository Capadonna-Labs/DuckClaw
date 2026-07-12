'use client';

import Link from 'next/link';
import { AlertTriangle } from 'lucide-react';
import { integrationSettingsHref } from '@/lib/integrationApiKeys';
import type { IntegrationGapPayload, IntegrationGapView } from '@/lib/integrationGaps';

type IntegrationSecretsBannerProps = {
  gaps: IntegrationGapView[] | IntegrationGapPayload[];
  compact?: boolean;
  className?: string;
};

function gapLabel(gap: IntegrationGapView | IntegrationGapPayload): string {
  if ('integration' in gap) {
    return gap.integration.label;
  }
  return gap.label;
}

function gapHref(gap: IntegrationGapView | IntegrationGapPayload): string {
  if ('integration' in gap) {
    return integrationSettingsHref();
  }
  return gap.admin_href || integrationSettingsHref();
}

function gapMessage(gap: IntegrationGapView | IntegrationGapPayload): string {
  if ('integration' in gap) {
    return `La skill «${gap.skill}» requiere API key de ${gap.integration.label}.`;
  }
  return gap.message;
}

export function IntegrationSecretsBanner({
  gaps,
  compact,
  className = '',
}: IntegrationSecretsBannerProps) {
  if (gaps.length === 0) return null;

  return (
    <ul
      className={`space-y-1.5 rounded-lg border border-amber-200/80 bg-amber-50/70 px-2 py-1.5 dark:border-amber-900/40 dark:bg-amber-950/20 ${className}`}
    >
      {gaps.map((gap) => {
        const key = 'integration' in gap ? `${gap.skill}:${gap.integration.id}` : `${gap.skill}:${gap.integration_id}`;
        return (
          <li key={key} className="flex flex-col gap-1 text-[10px] leading-snug text-amber-950 dark:text-amber-100">
            <span className="flex items-start gap-1.5">
              <AlertTriangle size={11} className="mt-0.5 shrink-0" aria-hidden />
              {gapMessage(gap)}
            </span>
            <Link
              href={gapHref(gap)}
              className={`font-semibold text-gov-blue-700 hover:underline dark:text-dark-cyan ${compact ? 'pl-4' : 'pl-5'}`}
            >
              Configurar {gapLabel(gap)} →
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
