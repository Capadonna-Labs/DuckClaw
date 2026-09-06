export const HTML_REPORT_MAX_BYTES = 512 * 1024;
export const HTML_REPORT_PLACEHOLDER_MARKER = 'Ningún reporte generado aún';

export function isHtmlReportIncomplete(html: string): boolean {
  const low = (html || '').toLowerCase();
  return !low.includes('</html>') || !low.includes('<body');
}

export function isHtmlReportPlaceholder(html: string): boolean {
  return html.includes(HTML_REPORT_PLACEHOLDER_MARKER) || isHtmlReportIncomplete(html);
}

export function titleFromHtmlFilename(filename: string): string {
  const base = filename.split(/[/\\]/).pop() || 'Reporte';
  return base.replace(/\.html?$/i, '').trim() || 'Reporte';
}

export function titleFromHtmlContent(html: string): string {
  const m = (html || '').match(/<title[^>]*>([^<]*)<\/title>/i);
  return ((m?.[1] || 'Reporte').trim().slice(0, 200) || 'Reporte');
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
  if (!low.includes('</html>')) {
    return 'HTML inválido: falta </html>';
  }
  if (!low.includes('<body')) {
    return 'HTML inválido: falta <body>';
  }
  return null;
}
