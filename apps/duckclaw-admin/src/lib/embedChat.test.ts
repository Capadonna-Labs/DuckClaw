import { describe, expect, it, vi } from 'vitest';
import { EMBED_CHAT_CLOSE, requestEmbedChatClose, shouldEscCloseEmbedChat } from './embedChat';

const noPopup = { querySelector: () => null };
const popup = { querySelector: () => ({}) as Element };
const key = (over: Record<string, unknown> = {}) =>
  ({ key: 'Escape', defaultPrevented: false, target: { tagName: 'TEXTAREA' }, ...over }) as unknown as KeyboardEvent;

describe('shouldEscCloseEmbedChat', () => {
  it('closes on a plain Esc', () => expect(shouldEscCloseEmbedChat(key(), noPopup)).toBe(true));
  it('ignores other keys', () => expect(shouldEscCloseEmbedChat(key({ key: 'Enter' }), noPopup)).toBe(false));
  it('leaves Esc to a handler that took it', () =>
    expect(shouldEscCloseEmbedChat(key({ defaultPrevented: true }), noPopup)).toBe(false));
  it('leaves Esc to inputs', () =>
    expect(shouldEscCloseEmbedChat(key({ target: { tagName: 'INPUT' } }), noPopup)).toBe(false));
  it('leaves Esc to open popups', () => expect(shouldEscCloseEmbedChat(key(), popup)).toBe(false));
});

describe('requestEmbedChatClose', () => {
  it('posts the close message to the parent, same origin only', () => {
    const postMessage = vi.fn();
    const win = { parent: { postMessage }, location: { origin: 'https://admin.example' } } as unknown as Window;
    requestEmbedChatClose(win);
    expect(postMessage).toHaveBeenCalledWith({ type: EMBED_CHAT_CLOSE }, 'https://admin.example');
  });
  it('does nothing at the top level', () => {
    const win = { location: { origin: 'https://admin.example' } } as { parent?: unknown; location: { origin: string } };
    win.parent = win;
    expect(() => requestEmbedChatClose(win as unknown as Window)).not.toThrow();
  });
});
