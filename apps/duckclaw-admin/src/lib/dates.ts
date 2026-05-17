import { format } from 'date-fns/format';
import { parseISO } from 'date-fns/parseISO';
import { formatDistanceToNow } from 'date-fns/formatDistanceToNow';
import { es } from 'date-fns/locale/es';

/** Retorna fecha en formato "dd/MM/yyyy". */
export function formatearFecha(isoString: string): string {
  try {
    return format(parseISO(isoString), 'dd/MM/yyyy', { locale: es });
  } catch {
    return 'Fecha inválida';
  }
}

/** Retorna "Hace 2 días", "Hace 3 horas", etc. */
export function formatearFechaRelativa(isoString: string): string {
  try {
    return formatDistanceToNow(parseISO(isoString), {
      addSuffix: true,
      locale: es,
    });
  } catch {
    return 'Fecha inválida';
  }
}
