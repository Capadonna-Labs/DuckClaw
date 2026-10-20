/**
 * Unread badge for the conversation list: how many messages each conversation had the last
 * time it was open on this device. Per-device by design (browser storage); a conversation never
 * seen on this device counts as read so the list does not light up on first visit.
 */
const KEY = 'duckclaw.conversationSeen.v1';

function read(): Record<string, number> {
  try {
    const raw = window.localStorage.getItem(KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

export function markConversationSeen(sessionId: string, messageCount: number): void {
  if (!sessionId || !Number.isFinite(messageCount)) return;
  try {
    const seen = read();
    if ((seen[sessionId] ?? -1) >= messageCount) return;
    seen[sessionId] = messageCount;
    window.localStorage.setItem(KEY, JSON.stringify(seen));
  } catch {
    // Private mode / storage blocked: the badge just stays off.
  }
}

/** New replies since the last visit. Each turn stores a user line and a reply, so count / 2. */
export function unreadReplies(sessionId: string, messageCount: number): number {
  const seen = read()[sessionId];
  if (seen === undefined) {
    markConversationSeen(sessionId, messageCount);
    return 0;
  }
  return Math.max(0, Math.ceil((messageCount - seen) / 2));
}
