/** "11:45 p. m." today, "18 oct, 11:45 p. m." otherwise. */
export function formatMessageTime(iso: string | undefined, now = new Date()): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const time = d.toLocaleTimeString('es-CO', { hour: 'numeric', minute: '2-digit' });
  return d.toDateString() === now.toDateString()
    ? time
    : `${d.toLocaleDateString('es-CO', { day: 'numeric', month: 'short' })}, ${time}`;
}
