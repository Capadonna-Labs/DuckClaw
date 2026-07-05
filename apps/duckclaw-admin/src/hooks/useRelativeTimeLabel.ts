'use client';

import { useEffect, useState } from 'react';
import { formatRelativeTimeMs } from '@/lib/formatRelativeTime';
import { useVisibilityAwareInterval } from '@/hooks/useVisibilityAwareInterval';

const TICK_MS = 10_000;

/** Re-calcula la etiqueta relativa mientras la pestaña está visible. */
export function useRelativeTimeLabel(timestampMs: number): string {
  const [label, setLabel] = useState(() => formatRelativeTimeMs(timestampMs));

  useEffect(() => {
    setLabel(formatRelativeTimeMs(timestampMs));
  }, [timestampMs]);

  useVisibilityAwareInterval(() => {
    setLabel(formatRelativeTimeMs(timestampMs));
  }, timestampMs > 0 ? TICK_MS : null);

  return label;
}
