import { desktopAdminApiKey, isDesktopLiteMode, readDesktopEnvFile } from '@/lib/desktopEnvFile';

describe('desktopEnvFile', () => {
  it('prefers desktop.env over process env', () => {
    const prev = process.env.LOCALAPPDATA;
    const prevKey = process.env.DUCKCLAW_ADMIN_API_KEY;
    const tmp = require('fs').mkdtempSync(require('path').join(require('os').tmpdir(), 'dc-env-'));
    process.env.LOCALAPPDATA = tmp;
    process.env.DUCKCLAW_ADMIN_API_KEY = 'process-key';
    require('fs').mkdirSync(`${tmp}\\DuckClaw`, { recursive: true });
    require('fs').writeFileSync(
      `${tmp}\\DuckClaw\\desktop.env`,
      'DUCKCLAW_ADMIN_API_KEY=file-key\n',
      'utf8'
    );
    expect(readDesktopEnvFile().DUCKCLAW_ADMIN_API_KEY).toBe('file-key');
    expect(desktopAdminApiKey()).toBe('file-key');
    process.env.LOCALAPPDATA = prev;
    process.env.DUCKCLAW_ADMIN_API_KEY = prevKey;
  });

  it('detects desktop lite on win32 with desktop.env + loopback gateway', () => {
    const prevPlatform = process.platform;
    const prevLocal = process.env.LOCALAPPDATA;
    const prevGw = process.env.DUCKCLAW_GATEWAY_URL;
    const tmp = require('fs').mkdtempSync(require('path').join(require('os').tmpdir(), 'dc-lite-'));
    process.env.LOCALAPPDATA = tmp;
    process.env.DUCKCLAW_GATEWAY_URL = 'http://127.0.0.1:8000';
    Object.defineProperty(process, 'platform', { value: 'win32' });
    require('fs').mkdirSync(`${tmp}\\DuckClaw`, { recursive: true });
    require('fs').writeFileSync(
      `${tmp}\\DuckClaw\\desktop.env`,
      'DUCKCLAW_ADMIN_API_KEY=file-key\n',
      'utf8'
    );
    expect(isDesktopLiteMode()).toBe(true);
    Object.defineProperty(process, 'platform', { value: prevPlatform });
    process.env.LOCALAPPDATA = prevLocal;
    process.env.DUCKCLAW_GATEWAY_URL = prevGw;
  });
});
