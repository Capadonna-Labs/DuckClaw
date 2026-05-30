import assert from 'node:assert/strict';
import {
  artifactIdFromMessageText,
  artifactPreviewFromMessage,
  historyToChatMessages,
  preserveImagePreviewsFromPrevious,
  userPreviewsFromPayload,
} from './chatMessageImages';
import type { ChatMsg } from '../components/chat/types';

assert.deepEqual(
  userPreviewsFromPayload([{ mime_type: 'image/png', data_base64: 'abc123' }], ['1000377294.png']),
  [{ url: 'data:image/png;base64,abc123', name: '1000377294.png' }]
);

const aid = '6a9e78d6-32ee-4d70-858e-5ccf80a27746';
assert.equal(
  artifactIdFromMessageText(`Guardado en db/private/default/artifacts/${aid}.png`),
  aid
);

const preview = artifactPreviewFromMessage(`artifact_id=${aid}`, 'default');
assert.equal(preview?.[0]?.artifactId, aid);
assert.match(preview?.[0]?.url ?? '', new RegExp(`/api/admin/artifacts/default/${aid}$`));

const history = historyToChatMessages(
  [{ role: 'assistant', content: `Ver artifacts/${aid}.png` }],
  'default'
);
assert.equal(history[0]?.imagePreviews?.[0]?.artifactId, aid);

const server: ChatMsg[] = [{ role: 'user', text: 'foto' }];
const prev: ChatMsg[] = [
  {
    role: 'user',
    text: 'foto',
    imagePreviews: [{ url: 'data:image/png;base64,xyz', name: '1000377294.png' }],
  },
];
assert.deepEqual(preserveImagePreviewsFromPrevious(server, prev), prev);

console.log('chatMessageImages.test.ts: ok');
