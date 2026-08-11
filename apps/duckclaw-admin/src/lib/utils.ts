import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

/** Coerce gateway/API values before `.trim()` (JSON may send numbers). */
export function trimStr(value: unknown): string {
  if (value == null) return '';
  if (typeof value === 'string') return value.trim();
  return String(value).trim();
}

/**
 * Combina clases de Tailwind de forma segura usando clsx y tailwind-merge.
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
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
export function obtenerIniciales(nombreCompleto: unknown): string {
  const name = trimStr(nombreCompleto);
  if (!name) return '--';

  const partes = name.split(/\s+/);
  if (partes.length === 1) return partes[0].substring(0, 2).toUpperCase();

  const iniciales = (partes[0][0] + partes[1][0]).toUpperCase();
  return iniciales;
}

/**
 * Extrae el email real de una cadena que puede venir como "Nombre <email@dominio.com>"
 */
export function extraerEmail(input: unknown): string {
  const raw = trimStr(input);
  if (!raw) return '';
  const match = raw.match(/<([^>]+)>/);
  if (match && match[1]) {
    return trimStr(match[1]);
  }
  return raw;
}
