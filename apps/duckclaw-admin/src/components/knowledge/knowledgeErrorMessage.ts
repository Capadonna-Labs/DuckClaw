/** Traduce errores técnicos del gateway RAG a copy legible. */
export function formatKnowledgeError(raw: string): string {
  const msg = (raw || '').trim();
  if (!msg) return 'No se pudo completar la operación RAG.';

  const rules: Array<[RegExp, string]> = [
    [
      /source_not_found|waiting_for_source/i,
      'La fuente aún se estaba registrando. Reintenta «Actualizar» o «Añadir al chat» en unos segundos.',
    ],
    [
      /hidden knowledge files are not allowed/i,
      'La carpeta incluye archivos ocultos (.obsidian, .git…). Reinicia el Gateway con el último código: ahora se omiten automáticamente.',
    ],
    [
      /fuera de ra[ií]ces permitidas|outside allowed root/i,
      'Ruta fuera de las carpetas permitidas en el servidor. Revisa DUCKCLAW_KNOWLEDGE_ALLOWED_ROOTS en .env.',
    ],
    [
      /no configurado para ingesta/i,
      'El servidor no tiene DUCKCLAW_KNOWLEDGE_ALLOWED_ROOTS. Añádelo en .env y reinicia DuckClaw-Gateway.',
    ],
    [
      /Ruta truncada|truncada/i,
      'La ruta se cortó al pegar (común en Google Drive). Usa el explorador de carpetas o pega la ruta absoluta completa.',
    ],
    [
      /no existe|not found/i,
      'Esa ruta no existe en el Mac del Gateway. Usa el explorador de carpetas o pega la ruta absoluta.',
    ],
    [
      /No hay archivos indexables/i,
      msg,
    ],
    [
      /DB-Writer desactualizado/i,
      msg,
    ],
    [
      /500|timeout|timed out|ECONNRESET/i,
      'La indexación tardó demasiado. Reinicia el Gateway con el último código o importa eligiendo un agente concreto.',
    ],
  ];

  for (const [pattern, text] of rules) {
    if (pattern.test(msg)) return text;
  }
  return msg;
}

export interface KnowledgeFolderPreview {
  ok: boolean;
  source_uri: string;
  file_count: number;
  skipped_hidden: number;
  skipped_secret: number;
  skipped_unsupported: number;
  sample_paths: string[];
}

export function formatFolderPreviewLine(preview: KnowledgeFolderPreview): string {
  const parts = [`${preview.file_count} candidato(s) · aún no están en el chat`];
  if (preview.skipped_hidden > 0) {
    parts.push(`${preview.skipped_hidden} ocultos omitidos (.obsidian, etc.)`);
  }
  if (preview.skipped_unsupported > 0) {
    parts.push(`${preview.skipped_unsupported} con formato no soportado`);
  }
  return parts.join(' · ');
}
