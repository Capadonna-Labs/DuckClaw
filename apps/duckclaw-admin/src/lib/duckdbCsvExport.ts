/** Export DuckDB explorer rows to CSV (RFC 4180-ish). */

function escapeCsvCell(value: unknown): string {
  if (value === null || value === undefined) return '';
  const raw = typeof value === 'object' ? JSON.stringify(value) : String(value);
  if (/[",\n\r]/.test(raw)) {
    return `"${raw.replace(/"/g, '""')}"`;
  }
  return raw;
}

export function buildDuckdbCsv(columns: string[], rows: unknown[][]): string {
  const header = columns.map(escapeCsvCell).join(',');
  const body = rows.map((row) => row.map(escapeCsvCell).join(',')).join('\n');
  return body ? `${header}\n${body}` : header;
}

export function downloadDuckdbCsv(filename: string, columns: string[], rows: unknown[][]): void {
  const csv = buildDuckdbCsv(columns, rows);
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
