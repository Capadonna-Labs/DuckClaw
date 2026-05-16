import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import { format, parseISO, formatDistanceToNow } from 'date-fns';
import { es } from 'date-fns/locale';

/**
 * Combina clases de Tailwind de forma segura usando clsx y tailwind-merge.
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/**
 * Retorna fecha en formato "dd/MM/yyyy".
 * Ejemplo: "2026-04-15T10:30:00Z" -> "15/04/2026"
 */
export function formatearFecha(isoString: string): string {
  try {
    return format(parseISO(isoString), 'dd/MM/yyyy', { locale: es });
  } catch {
    return 'Fecha inválida';
  }
}

/**
 * Retorna "Hace 2 días", "Hace 3 horas", etc.
 */
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

/**
 * Trunca y agrega "..." si supera maxLength.
 */
export function truncarTexto(texto: string, maxLength: number): string {
  if (texto.length <= maxLength) return texto;
  return texto.slice(0, maxLength).trim() + '...';
}

/**
 * Extrae las primeras dos iniciales del nombre: "Carlos Arturo López" -> "CA"
 */
export function obtenerIniciales(nombreCompleto: string): string {
  if (!nombreCompleto) return '--';
  
  const partes = nombreCompleto.trim().split(/\s+/);
  if (partes.length === 1) return partes[0].substring(0, 2).toUpperCase();
  
  const iniciales = (partes[0][0] + partes[1][0]).toUpperCase();
  return iniciales;
}

/**
 * Extrae el email real de una cadena que puede venir como "Nombre <email@dominio.com>"
 */
export function extraerEmail(input: string): string {
  if (!input) return '';
  const match = input.match(/<([^>]+)>/);
  if (match && match[1]) {
    return match[1].trim();
  }
  return input.trim();
}
