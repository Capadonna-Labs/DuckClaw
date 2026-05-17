/** Valores reales de `topology` en manifest.yaml (ver duckclaw.workers.orchestrator). */
export const WORKER_TOPOLOGIES = [
  {
    id: 'general',
    label: 'General',
    hint: 'Agente único; sin delegación a sub-workers.',
  },
  {
    id: 'axis_orchestrator',
    label: 'AXIS orquestador',
    hint: 'Delega en sub-templates AXIS (requiere orchestrates en manifest).',
  },
] as const;

export type WorkerTopologyId = (typeof WORKER_TOPOLOGIES)[number]['id'];
