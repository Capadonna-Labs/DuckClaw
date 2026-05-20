import assert from 'node:assert/strict';
import {
  countUnreadAssistantMessages,
  formatUnreadBadge,
  markReadMessageIndex,
} from './chatUnreadStorage';
import type { ChatMsg } from '../components/chat/types';

const messages: ChatMsg[] = [
  { role: 'user', text: 'hola' },
  { role: 'assistant', text: 'respuesta 1' },
  { role: 'assistant', text: 'respuesta 2' },
  { role: 'assistant', text: 'en curso', streaming: true },
];

assert.equal(markReadMessageIndex(messages), 3);
assert.equal(countUnreadAssistantMessages(messages, 0), 2);
assert.equal(countUnreadAssistantMessages(messages, 2), 0);
assert.equal(countUnreadAssistantMessages(messages, 3), 0);
assert.equal(formatUnreadBadge(5), '5');
assert.equal(formatUnreadBadge(100), '99+');

console.log('chatUnreadStorage.test.ts: ok');
