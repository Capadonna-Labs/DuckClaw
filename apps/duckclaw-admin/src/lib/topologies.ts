/** Valores de `topology` en manifest.yaml (ver duckclaw.workers.orchestrator). */
export const WORKER_TOPOLOGIES = [
  {
    id: 'general',
    label: 'General',
    hint: 'Agente único; sin delegación a sub-workers.',
  },
  {
    id: 'orchestrator',
    label: 'Orquestador',
    hint: 'Delega en sub-workers listados en orchestrator.orchestrates del manifest.',
  },
] as const;

export type WorkerTopologyId = (typeof WORKER_TOPOLOGIES)[number]['id'];
