import type { KnowledgeSource } from '@/services/adminService';

function splitDocumentPaths(source: KnowledgeSource): string[] {
  return (source.document_paths || '')
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean);
}

function basename(path: string): string {
  const parts = path.split('/').filter(Boolean);
  return parts[parts.length - 1] || path;
}

export function knowledgeSourcePrimaryLabel(source: KnowledgeSource): string {
  const paths = splitDocumentPaths(source);
  if (paths.length === 1) {
    return basename(paths[0]);
  }
  const display = (source.display_name || '').trim();
  if (display && !display.startsWith('upload://')) {
    return display;
  }
  if (paths.length > 1) {
    return `${basename(paths[0])} (+${paths.length - 1} más)`;
  }
  const fileNames = source.metadata?.file_names;
  if (Array.isArray(fileNames) && fileNames.length > 0) {
    const first = String(fileNames[0] ?? '').trim();
    if (fileNames.length === 1 && first) return first;
    if (first) return `${first} (+${fileNames.length - 1} más)`;
  }
  return display || source.source_id;
}

export function knowledgeSourceSecondaryLine(source: KnowledgeSource): string | null {
  const paths = splitDocumentPaths(source);
  if (paths.length > 1) {
    return paths.map(basename).join(', ');
  }
  if (source.source_uri.startsWith('upload://')) {
    return paths.length === 1 ? paths[0] : null;
  }
  const uri = (source.source_uri || '').trim();
  return uri || null;
}
