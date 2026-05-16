/**
 * Heurística para rechazar abuso técnico en la instrucción del co-pilot CRM
 * antes de invocar al gateway (spec: CRM resumen ejecutivo Gateway.md).
 */

export type ValidateInstruccionResult =
  | { ok: true }
  | { ok: false; code: 'shell_or_system' | 'low_natural_text' };

/** Mensaje institucional único para respuesta HTTP 200 + invalid_request. */
export const INVALID_INSTRUCCION_FUNCIONARIO_TEXT = `Respetado/a funcionario/a:

No es una petición válida para el asistente de redacción institucional. Indique cómo desea ajustar la comunicación al ciudadano (tono, extensión, mención de normativa o similar). No se aceptan comandos de sistema ni instrucciones técnicas ajenas a la carta oficial.`;

const SHELL_OR_SYSTEM_PATTERNS: RegExp[] = [
  /\bsudo\b/i,
  /\brm\s+[-\w]/i,
  /--rm\b/i,
  /\bcurl\b/i,
  /\bwget\b/i,
  /\bchmod\b/i,
  /\bchown\b/i,
  /\beval\s*\(/i,
  /\bexec\s*\(/i,
  /\/\s*(?:bin|usr|etc|var|tmp|dev)\b/i,
  /\bcmd\.exe\b/i,
  /\bpowershell\b/i,
  /\b(?:&&|\|\|)\s*\S+/,
  /\|\s*(?:curl|wget|bash|sh|sudo)\b/i,
  /\b(?:bash|sh|zsh)\s+(?:-c|\()/i,
  /\bdocker\b/i,
  /\bkubectl\b/i,
  /\bssh\b/i,
  /\bscp\b/i,
  /\b(?:DROP|DELETE|TRUNCATE)\s+TABLE\b/i,
];

/**
 * Rechaza instrucciones que no parecen redacción PQRSD (comandos shell, etc.).
 */
export function validateInstruccionFuncionario(raw: string): ValidateInstruccionResult {
  const s = (raw ?? '').trim();
  if (!s) {
    return { ok: false, code: 'shell_or_system' };
  }

  for (const re of SHELL_OR_SYSTEM_PATTERNS) {
    if (re.test(s)) {
      return { ok: false, code: 'shell_or_system' };
    }
  }

  const letters = (s.match(/[a-záéíóúüñA-ZÁÉÍÓÚÜÑ]/g) ?? []).length;
  if (s.length >= 24 && letters / s.length < 0.35) {
    return { ok: false, code: 'low_natural_text' };
  }

  return { ok: true };
}
