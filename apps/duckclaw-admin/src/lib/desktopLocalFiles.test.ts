import { describe, expect, it } from 'vitest';
import { desktopLocalFileToFile } from './desktopLocalFiles';

describe('desktopLocalFiles', () => {
  it('reconstructs File from base64 payload', async () => {
    const payload = {
      name: 'movimientos.xlsx',
      mime_type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      data_base64: Buffer.from('PK\x03\x04excel').toString('base64'),
      size: 10,
    };
    const file = desktopLocalFileToFile(payload);
    expect(file.name).toBe('movimientos.xlsx');
    expect(file.type).toBe(payload.mime_type);
    expect(file.size).toBeGreaterThan(0);
    const text = await file.text();
    expect(text.startsWith('PK')).toBe(true);
  });
});
