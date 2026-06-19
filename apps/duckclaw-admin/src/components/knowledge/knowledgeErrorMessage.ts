/** Traduce errores técnicos del gateway RAG a copy legible. */
export function formatKnowledgeError(raw: string): string {
  const msg = (raw || '').trim();
  if (!msg) return 'No se pudo completar la operación RAG.';

  const rules: Array<[RegExp, string]> = [
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
      'La ruta se cortó al pegar (común en Google Drive). Pulsa «Usar vault del servidor».',
    ],
    [
      /no existe|not found/i,
      'Esa ruta no existe en el Mac del Gateway. Usa «Usar vault del servidor» o pega la ruta completa hasta MacMiniVault.',
    ],
    [
      /No hay archivos indexables/i,
      msg,
    ],
    [
      /DB-Writer desactualizado/i,
      msg,
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
  const parts = [`${preview.file_count} archivo(s) listos para indexar`];
  if (preview.skipped_hidden > 0) {
    parts.push(`${preview.skipped_hidden} ocultos omitidos (.obsidian, etc.)`);
  }
  if (preview.skipped_unsupported > 0) {
    parts.push(`${preview.skipped_unsupported} con formato no soportado`);
  }
  return parts.join(' · ');
}
