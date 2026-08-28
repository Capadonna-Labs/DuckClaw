import { describe, expect, it } from 'vitest';
import {
  isHtmlReportPlaceholder,
  titleFromHtmlFilename,
  validateHtmlUploadFile,
  validateHtmlUploadText,
} from './htmlDashboardUpload';

describe('htmlDashboardUpload', () => {
  it('detects placeholder marker', () => {
    expect(isHtmlReportPlaceholder('<h3>Ningún reporte generado aún</h3>')).toBe(true);
    expect(isHtmlReportPlaceholder('<!DOCTYPE html><html><body>OK</body></html>')).toBe(false);
  });

  it('derives title from filename', () => {
    expect(titleFromHtmlFilename('mi-dashboard.html')).toBe('mi-dashboard');
    expect(titleFromHtmlFilename('C:\\tmp\\foo.htm')).toBe('foo');
  });

  it('validates upload file extension and size', () => {
    const ok = new File(['x'], 'dash.html', { type: 'text/html' });
    expect(validateHtmlUploadFile(ok)).toBeNull();
    const bad = new File(['x'], 'dash.txt', { type: 'text/plain' });
    expect(validateHtmlUploadFile(bad)).toMatch(/html/i);
  });

  it('validates html text shape', () => {
    expect(validateHtmlUploadText('<div>nope</div>')).toMatch(/DOCTYPE|html/i);
    expect(
      validateHtmlUploadText('<!DOCTYPE html><html><body></body></html>')
    ).toBeNull();
  });
});

console.log('htmlDashboardUpload.test.ts OK');
