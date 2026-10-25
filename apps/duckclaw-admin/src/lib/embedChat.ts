/** Message the page framing the embedded chat (e.g. an HTML dashboard's chat box) listens for to hide it; the chat stays loaded. */
export const EMBED_CHAT_CLOSE = 'duckclaw:embed-chat-close';

/** Ask the framing page to hide this chat. Same-origin only: a parent on another origin never gets it. */
export function requestEmbedChatClose(win: Window = window): void {
  if (win.parent === win) return;
  try {
    win.parent.postMessage({ type: EMBED_CHAT_CLOSE }, win.location.origin);
  } catch {
    /* parent gone or unreachable */
  }
}

/**
 * Esc in the embedded chat closes the box only when nothing inside it handles Esc itself:
 * not after another handler took it, not while typing in a field (title edit, search), not while a popup is open.
 */
export function shouldEscCloseEmbedChat(
  e: Pick<KeyboardEvent, 'key' | 'defaultPrevented' | 'target'>,
  doc: Pick<Document, 'querySelector'>,
): boolean {
  if (e.key !== 'Escape' || e.defaultPrevented) return false;
  const tag = (e.target as { tagName?: string } | null)?.tagName;
  if (tag === 'INPUT' || tag === 'SELECT') return false;
  return !doc.querySelector('[role="dialog"], [role="listbox"]');
}
