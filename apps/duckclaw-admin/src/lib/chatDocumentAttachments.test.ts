import { describe, expect, it } from 'vitest';
import {
  isAllowedChatDocument,
  isAllowedChatDocumentName,
} from '@/lib/chatDocumentAttachments';

describe('chatDocumentAttachments', () => {
  it('accepts office and text extensions', () => {
    expect(isAllowedChatDocumentName('a.pdf')).toBe(true);
    expect(isAllowedChatDocument({ name: 'b.docx' })).toBe(true);
    expect(isAllowedChatDocument({ name: 'c.xlsx' })).toBe(true);
    expect(isAllowedChatDocument({ name: 'd.csv' })).toBe(true);
    expect(isAllowedChatDocumentName('e.TXT')).toBe(true);
  });

  it('rejects unsupported extensions', () => {
    expect(isAllowedChatDocumentName('x.exe')).toBe(false);
    expect(isAllowedChatDocument({ name: 'photo.png' })).toBe(false);
  });
});
