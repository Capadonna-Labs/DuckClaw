import { describe, expect, it } from 'vitest';
import {
  MAX_INLINE_MESSAGE_CHARS,
  splitOverlongMessageIntoTxtAttachment,
} from './adminChatPure';

describe('splitOverlongMessageIntoTxtAttachment', () => {
  it('passes short messages through untouched', () => {
    const { message, extraDocument } = splitOverlongMessageIntoTxtAttachment('hola mundo');
    expect(message).toBe('hola mundo');
    expect(extraDocument).toBeNull();
  });

  it('converts an over-limit message into a mensaje.txt attachment', () => {
    // Regression: PlaygroundChatBody.message caps at 16000 chars server-side
    // (Pydantic max_length) — pasting more used to raise a 422 with no
    // recovery path in the compose UI.
    const longText = 'A'.repeat(MAX_INLINE_MESSAGE_CHARS + 1);
    const { message, extraDocument } = splitOverlongMessageIntoTxtAttachment(longText);

    expect(message).toBe('(mensaje largo adjuntado como mensaje.txt)');
    expect(extraDocument).not.toBeNull();
    expect(extraDocument?.filename).toBe('mensaje.txt');
    expect(extraDocument?.mime_type).toBe('text/plain');

    const decoded = Buffer.from(extraDocument?.data_base64 ?? '', 'base64').toString('utf-8');
    expect(decoded).toBe(longText);
  });

  it('round-trips non-ASCII text correctly through the base64 encoding', () => {
    const longText = 'á é í ó ú ñ € — '.repeat(2000);
    expect(longText.length).toBeGreaterThan(MAX_INLINE_MESSAGE_CHARS);
    const { extraDocument } = splitOverlongMessageIntoTxtAttachment(longText);
    const decoded = Buffer.from(extraDocument?.data_base64 ?? '', 'base64').toString('utf-8');
    expect(decoded).toBe(longText);
  });

  it('stays exactly at the limit without converting', () => {
    const exactText = 'B'.repeat(MAX_INLINE_MESSAGE_CHARS);
    const { message, extraDocument } = splitOverlongMessageIntoTxtAttachment(exactText);
    expect(message).toBe(exactText);
    expect(extraDocument).toBeNull();
  });
});
