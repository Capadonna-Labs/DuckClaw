/** Extensiones admitidas en adjunto de chat (MarkItDown + texto nativo). */
export const CHAT_DOCUMENT_EXTENSIONS = new Set([
  '.pdf',
  '.docx',
  '.doc',
  '.xlsx',
  '.xls',
  '.csv',
  '.txt',
  '.md',
  '.markdown',
  '.pptx',
  '.ppt',
  '.html',
  '.htm',
  '.json',
]);

export const CHAT_DOCUMENT_ACCEPT =
  '.pdf,.docx,.doc,.xlsx,.xls,.csv,.txt,.md,.markdown,.pptx,.ppt,.html,.htm,.json,' +
  'application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,' +
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,' +
  'application/vnd.ms-excel,text/csv,text/plain,text/markdown,application/json';

export function chatDocumentExtension(name: string): string {
  const base = (name || '').replace(/\\/g, '/').split('/').pop() || '';
  const dot = base.lastIndexOf('.');
  if (dot < 0) return '';
  return base.slice(dot).toLowerCase();
}

export function isAllowedChatDocumentName(name: string): boolean {
  return CHAT_DOCUMENT_EXTENSIONS.has(chatDocumentExtension(name));
}

export function isAllowedChatDocument(file: { name: string }): boolean {
  return isAllowedChatDocumentName(file.name);
}

export function guessChatDocumentMime(file: { name: string; type?: string }): string {
  const mime = (file.type || '').trim().toLowerCase();
  if (mime) return mime;
  const ext = chatDocumentExtension(file.name);
  const map: Record<string, string> = {
    '.pdf': 'application/pdf',
    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    '.doc': 'application/msword',
    '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    '.xls': 'application/vnd.ms-excel',
    '.csv': 'text/csv',
    '.txt': 'text/plain',
    '.md': 'text/markdown',
    '.markdown': 'text/markdown',
    '.json': 'application/json',
    '.html': 'text/html',
    '.htm': 'text/html',
    '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    '.ppt': 'application/vnd.ms-powerpoint',
  };
  return map[ext] || 'application/octet-stream';
}
