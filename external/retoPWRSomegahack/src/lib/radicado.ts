export const CODIGOS_SECRETARIA: Record<string, string> = {
  'sec-salud':      'SAL',
  'sec-educacion':  'EDU',
  'sec-movilidad':  'MOV',
  'sec-cultura':    'CUL',
  'sec-desarrollo': 'DES',
};

/**
 * Genera un radicado único para un ticket PQRSD.
 * En producción el backend (FastAPI/DuckDB) lo genera al hacer el INSERT.
 * En el frontend lo usamos para mocks y el simulador de demo.
 */
export function generarNumeroRadicado(
  idSecretaria: string,
  fecha: Date = new Date()
): string {
  const yyyy = fecha.getFullYear();
  const mm   = String(fecha.getMonth() + 1).padStart(2, '0');
  const dd   = String(fecha.getDate()).padStart(2, '0');
  // Secuencia pseudoaleatoria de 6 dígitos (suficiente para demos)
  const seq  = String(Math.floor(Math.random() * 999999)).padStart(6, '0');
  const cod  = CODIGOS_SECRETARIA[idSecretaria] ?? 'GEN';
  return `MDE-${yyyy}${mm}${dd}-${seq}-${cod}`;
}

/**
 * Versión compacta para mostrar en tablas y espacios reducidos.
 * MDE-20260418-000142-SAL → #000142-SAL
 */
export function formatearRadicadoCorto(radicado: string): string {
  const partes = radicado.split('-');
  // Formato: MDE - YYYYMMDD - NNNNNN - COD → queremos #NNNNNN-COD
  if (partes.length === 4) return `#${partes[2]}-${partes[3]}`;
  return radicado; // fallback si el formato no es el esperado
}

/**
 * Valida que un string tenga el formato correcto.
 * Útil para sanear datos provenientes del backend.
 */
export function validarFormatoRadicado(radicado: string): boolean {
  return /^MDE-\d{8}-\d{6}-[A-Z]{2,3}$/.test(radicado);
}

/**
 * Extrae la fecha de radicación del número de radicado.
 * Útil para mostrar metadata sin hacer otro request al backend.
 */
export function parsearFechaDeRadicado(radicado: string): Date | null {
  const match = radicado.match(/^MDE-(\d{4})(\d{2})(\d{2})-/);
  if (!match) return null;
  return new Date(
    parseInt(match[1]),  // año
    parseInt(match[2]) - 1,  // mes (0-indexed)
    parseInt(match[3])   // día
  );
}
