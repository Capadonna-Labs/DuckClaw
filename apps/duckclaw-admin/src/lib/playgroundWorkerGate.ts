import { workerOptionId, type WorkerOption } from '@/lib/workerOptions';

/** Destino cuando Chat detecta que no hay agentes reales. */
export const WORKER_REQUIRED_PROJECTS_HREF = '/projects?onboarding=worker-required';

export const WORKER_REQUIRED_ALERT_MESSAGE =
  'No tienes agentes creados. Ve a Proyectos para crear el primero.';

const PHANTOM_WORKER_IDS = new Set(['default', 'internal_scaffold']);

/**
 * True si el catálogo del playground tiene al menos un worker real.
 * Vacío o solo `default` / scaffolds internos cuentan como “sin workers”.
 */
export function hasVisiblePlaygroundWorkers(
  workers: WorkerOption[] | undefined | null
): boolean {
  for (const worker of workers ?? []) {
    const id = workerOptionId(worker).trim();
    if (!id) continue;
    if (PHANTOM_WORKER_IDS.has(id)) continue;
    return true;
  }
  return false;
}

/**
 * Decide si Chat debe redirigir a Proyectos.
 * No redirige mientras carga, ni si falló la config, ni si hay workers reales.
 */
export function shouldRedirectToProjectsForMissingWorkers(input: {
  configLoading: boolean;
  configError: string | null | undefined;
  configLoaded: boolean;
  workers: WorkerOption[] | undefined | null;
  alreadyRedirected?: boolean;
}): boolean {
  if (input.alreadyRedirected) return false;
  if (input.configLoading) return false;
  if (input.configError) return false;
  if (!input.configLoaded) return false;
  return !hasVisiblePlaygroundWorkers(input.workers);
}
