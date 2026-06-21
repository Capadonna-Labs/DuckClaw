import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const source = readFileSync(new URL('./page.tsx', import.meta.url), 'utf8');
const runSettingsSource = readFileSync(
  new URL('../../../components/playground/PlaygroundRunSettingsPanel.tsx', import.meta.url),
  'utf8'
);
const chatPanelSource = readFileSync(
  new URL('../../../components/chat/AdminChatPanel.tsx', import.meta.url),
  'utf8'
);

assert.equal(
  source.includes('ConfigAccordionSection'),
  false,
  'Playground settings should use AI Studio style cards/modals, not stacked accordions'
);

assert.equal(
  source.includes('Proyecto activo:'),
  false,
  'Playground chat surface should not render project status banners above the chat'
);

assert.equal(
  source.includes('Respuestas en vivo (SSE) · pestaña Conversación para cambiar de hilo'),
  false,
  'Playground header should not consume chat space with explanatory copy'
);

assert.equal(
  chatPanelSource.includes('ChatViewTabBar'),
  false,
  'AdminChatPanel should keep the full chat surface clean without embedded chat/conversation tabs'
);

assert.equal(
  chatPanelSource.includes('config?.team_hint && viewTab ==='),
  false,
  'AdminChatPanel should not render team hints as a banner inside the chat surface'
);

assert.ok(
  source.includes('PlaygroundRunSettingsPanel') && source.includes('SettingsModal'),
  'Playground settings should expose compact run settings and modal details'
);

assert.ok(
  runSettingsSource.includes('label="Proyecto"') && runSettingsSource.includes('label="Agente"'),
  'Run settings should expose project and agent controls as separate visible entries'
);

assert.equal(
  runSettingsSource.includes('title="Proyecto y agente"'),
  false,
  'Project and agent should not be hidden behind one combined settings row'
);

console.log('playground/page.test.mjs: ok');
