import {
  desktopAdminApiKey,
  isDesktopLiteMode,
  readDesktopEnvFile,
  updateDesktopAdminCredentials,
} from '@/lib/desktopEnvFile';
import { describe, expect, it } from 'vitest';

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

  it('updates only the desktop bootstrap credentials', () => {
    const prev = process.env.LOCALAPPDATA;
    const tmp = require('fs').mkdtempSync(require('path').join(require('os').tmpdir(), 'dc-register-'));
    process.env.LOCALAPPDATA = tmp;
    require('fs').mkdirSync(`${tmp}\\DuckClaw`, { recursive: true });
    require('fs').writeFileSync(
      `${tmp}\\DuckClaw\\desktop.env`,
      'DUCKCLAW_ADMIN_API_KEY=keep-this\nDUCKCLAW_ADMIN_EMAIL=old@example.com\n',
      'utf8'
    );

    expect(updateDesktopAdminCredentials('new@example.com', 'new-password')).toBe(true);
    expect(readDesktopEnvFile()).toMatchObject({
      DUCKCLAW_ADMIN_API_KEY: 'keep-this',
      DUCKCLAW_ADMIN_EMAIL: 'new@example.com',
      DUCKCLAW_ADMIN_PASSWORD: 'new-password',
    });
    process.env.LOCALAPPDATA = prev;
  });
});
