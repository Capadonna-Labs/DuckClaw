export const HTML_REPORT_MAX_BYTES = 512 * 1024;
export const HTML_REPORT_PLACEHOLDER_MARKER = 'Ningún reporte generado aún';

export function isHtmlReportPlaceholder(html: string): boolean {
  return html.includes(HTML_REPORT_PLACEHOLDER_MARKER);
}

export function titleFromHtmlFilename(filename: string): string {
  const base = filename.split(/[/\\]/).pop() || 'Reporte';
  return base.replace(/\.html?$/i, '').trim() || 'Reporte';
}

export function validateHtmlUploadFile(file: File): string | null {
  const name = (file.name || '').toLowerCase();
  if (!name.endsWith('.html') && !name.endsWith('.htm')) {
    return 'Solo archivos .html o .htm';
  }
  if (file.size > HTML_REPORT_MAX_BYTES) {
    return 'El archivo excede 512 KB';
  }
  return null;
}

export function validateHtmlUploadText(text: string): string | null {
  const raw = text || '';
  if (!raw.trim()) return 'Archivo vacío';
  if (new TextEncoder().encode(raw).length > HTML_REPORT_MAX_BYTES) {
    return 'El HTML excede 512 KB';
  }
  const low = raw.toLowerCase();
  if (!low.includes('</html>') && !low.includes('<!doctype')) {
    return 'HTML inválido: falta </html> o <!DOCTYPE>';
  }
  return null;
}
