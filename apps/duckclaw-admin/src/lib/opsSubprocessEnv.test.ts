import { describe, expect, it, vi } from 'vitest';
import { opsSubprocessEnv } from './opsSubprocessEnv';
import {
  isPm2NodeDevBlockedKey,
  PM2_NODE_DEV_ENV_FILTER,
} from './pm2NodeDevEnvFilter';

describe('opsSubprocessEnv', () => {
  it('permite DUCKCLAW_* y bloquea variables de next dev', () => {
    vi.stubEnv('DUCKCLAW_GATEWAY_URL', 'http://127.0.0.1:8000');
    vi.stubEnv('HOME', '/Users/test');
    vi.stubEnv('PATH', '/usr/bin');
    vi.stubEnv('NODE_OPTIONS', '--max-old-space-size=8192');
    vi.stubEnv('NEXT_RUNTIME', 'nodejs');
    vi.stubEnv('npm_lifecycle_script', 'next dev');

    const sample = opsSubprocessEnv();
    expect(sample.DUCKCLAW_GATEWAY_URL).toBe('http://127.0.0.1:8000');
    expect(sample.HOME).toBe('/Users/test');
    expect(sample.PATH?.split(':')).toContain('/opt/homebrew/bin');
    expect(sample.NODE_OPTIONS).toBeUndefined();
    expect(sample.NEXT_RUNTIME).toBeUndefined();
    expect(sample.npm_lifecycle_script).toBeUndefined();

    vi.unstubAllEnvs();
  });

  it('acepta extras explícitos', () => {
    const sample = opsSubprocessEnv({
      DUCKCLAW_GATEWAY_URL: 'http://127.0.0.1:8000',
      HOME: '/Users/test',
      PATH: '/usr/bin',
    });
    expect(sample.DUCKCLAW_GATEWAY_URL).toBe('http://127.0.0.1:8000');
    expect('NODE_OPTIONS' in sample).toBe(false);
    expect('NEXT_RUNTIME' in sample).toBe(false);
  });
});

describe('pm2_node_dev_env_filter spec parity', () => {
  it('bloquea prefijos y claves del seed compartido', () => {
    for (const prefix of PM2_NODE_DEV_ENV_FILTER.blocked_prefixes) {
      expect(isPm2NodeDevBlockedKey(`${prefix}example`)).toBe(true);
    }
    for (const key of PM2_NODE_DEV_ENV_FILTER.blocked_keys) {
      expect(isPm2NodeDevBlockedKey(key)).toBe(true);
    }
    expect(isPm2NodeDevBlockedKey('npm_package_name')).toBe(true);
    expect(isPm2NodeDevBlockedKey('DUCKCLAW_GATEWAY_URL')).toBe(false);
  });
});
