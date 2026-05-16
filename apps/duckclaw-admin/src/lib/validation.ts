/** Validaciones compartidas — consola admin */

export const LIMITS = {
  searchQuery: 50,
  workerId: 64,
  templatePath: 120,
  runtimeKey: 128,
  runtimeValue: 8000,
  tenantId: 64,
  telegramUserId: 20,
  username: 64,
  sessionId: 128,
  commandSearch: 50,
} as const;

const WORKER_ID_RE = /^[a-zA-Z0-9_-]+$/;

export function clampInput(value: string, max: number): string {
  return value.slice(0, max);
}

export function validateWorkerId(id: string): string | null {
  const v = id.trim();
  if (!v) return 'El ID del worker es obligatorio';
  if (v.length > LIMITS.workerId) return `Máximo ${LIMITS.workerId} caracteres`;
  if (!WORKER_ID_RE.test(v)) return 'Solo letras, números, guión y guión bajo';
  return null;
}

export function validateTemplatePath(path: string): string | null {
  const v = path.trim();
  if (!v) return 'La ruta de plantilla origen es obligatoria';
  if (v.length > LIMITS.templatePath) return `Máximo ${LIMITS.templatePath} caracteres`;
  if (v.includes('..')) return 'Ruta inválida';
  return null;
}

export function validateRuntimeKey(key: string): string | null {
  const v = key.trim();
  if (!v) return 'La key es obligatoria';
  if (v.length > LIMITS.runtimeKey) return `Máximo ${LIMITS.runtimeKey} caracteres`;
  return null;
}

export function validateRuntimeValue(value: string): string | null {
  if (value.length > LIMITS.runtimeValue) return `Máximo ${LIMITS.runtimeValue} caracteres`;
  return null;
}

export function validateTelegramUserId(id: string): string | null {
  const v = id.trim();
  if (!v) return 'user_id obligatorio';
  if (!/^\d{3,20}$/.test(v)) return 'user_id debe ser numérico (3–20 dígitos)';
  return null;
}
