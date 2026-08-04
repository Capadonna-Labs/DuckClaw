import assert from 'node:assert/strict';
import {
  artifactIdFromMessageText,
  artifactPreviewFromMessage,
  historyToChatMessages,
  payloadImagesFromPreviews,
  preserveImagePreviewsFromPrevious,
  stripContextBlocksForDisplay,
  userPreviewsFromPayload,
} from './chatMessageImages';
import type { ChatMsg } from '../components/chat/types';

assert.deepEqual(
  userPreviewsFromPayload([{ mime_type: 'image/png', data_base64: 'abc123' }], ['1000377294.png']),
  [{ url: 'data:image/png;base64,abc123', name: '1000377294.png' }]
);

assert.deepEqual(
  payloadImagesFromPreviews([
    { url: 'data:image/png;base64,abc123', name: '1000377294.png' },
    { url: '/api/admin/artifacts/default/x', name: 'artifact.png' },
  ]),
  [{ mime_type: 'image/png', data_base64: 'abc123' }]
);

const aid = '6a9e78d6-32ee-4d70-858e-5ccf80a27746';
assert.equal(
  artifactIdFromMessageText(`Guardado en db/private/default/artifacts/${aid}.png`),
  aid
);
assert.equal(
  artifactIdFromMessageText(`artifacts/fal_${aid}.jpg`),
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

const historyMulti = historyToChatMessages(
  [
    {
      role: 'assistant',
      content: `Report ready\nvisual_artifact_id: ${aid}\nvisual_artifact_id: 2ab40842-bc48-4497-a79a-60f54f92ddf0`,
    },
  ],
  'default'
);
assert.equal(historyMulti[0]?.imagePreviews?.length, 2);

const server: ChatMsg[] = [{ role: 'user', text: 'foto' }];
const prev: ChatMsg[] = [
  {
    role: 'user',
    text: 'foto',
    imagePreviews: [{ url: 'data:image/png;base64,xyz', name: '1000377294.png' }],
  },
];
assert.deepEqual(preserveImagePreviewsFromPrevious(server, prev), prev);

const polluted = `[PROJECT_CONTEXT]\nNombre: Demo\n[/PROJECT_CONTEXT]\n\n¿Qué puedes hacer?`;
assert.equal(stripContextBlocksForDisplay(polluted), '¿Qué puedes hacer?');
const historyStripped = historyToChatMessages(
  [{ role: 'user', content: polluted }, { role: 'assistant', content: 'Puedo ayudarte.' }],
  'default'
);
assert.equal(historyStripped[0]?.text, '¿Qué puedes hacer?');
assert.equal(historyStripped[1]?.text, 'Puedo ayudarte.');

console.log('chatMessageImages.test.ts: ok');
