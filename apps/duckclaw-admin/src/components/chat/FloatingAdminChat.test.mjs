import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const source = readFileSync(new URL('./FloatingAdminChat.tsx', import.meta.url), 'utf8');

assert.ok(
  source.includes('Pm2LiveLogsProvider') &&
    source.includes('Pm2LiveLogsControls') &&
    source.includes('Pm2LiveLogsViewport'),
  'FloatingAdminChat should reuse playground PM2 logs components'
);

assert.ok(
  source.includes('logsSplitOpen') && source.includes('autoStart={logsSplitOpen}'),
  'Logs stream should auto-start only when split is open'
);

assert.ok(
  source.includes("{'</>'}") && source.includes('aria-pressed={logsSplitOpen}'),
  'Footer toggle should render </> with aria-pressed'
);

assert.ok(
  source.includes('data-testid="floating-chat-logs-toggle"'),
  'Toggle should expose test id for manual/automated checks'
);

console.log('FloatingAdminChat.test.mjs: ok');
