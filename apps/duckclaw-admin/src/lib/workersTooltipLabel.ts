/** Label for the platform workers status control. */
export function workersTooltipLabel(workers: string[]): string {
  if (workers.length === 0) return 'Sin workers activos';
  return workers.join(', ');
}
