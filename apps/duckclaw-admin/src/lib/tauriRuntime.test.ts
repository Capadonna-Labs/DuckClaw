import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { isDesktopBuild, isTauriDesktop } from '@/lib/tauriRuntime';

describe('tauriRuntime', () => {
  const prevDesktop = process.env.NEXT_PUBLIC_DUCKCLAW_DESKTOP;

  beforeEach(() => {
    vi.stubGlobal('window', {} as Window);
  });

  afterEach(() => {
    process.env.NEXT_PUBLIC_DUCKCLAW_DESKTOP = prevDesktop;
    vi.unstubAllGlobals();
  });

  it('isDesktopBuild respects NEXT_PUBLIC_DUCKCLAW_DESKTOP', () => {
    process.env.NEXT_PUBLIC_DUCKCLAW_DESKTOP = '1';
    expect(isDesktopBuild()).toBe(true);
    process.env.NEXT_PUBLIC_DUCKCLAW_DESKTOP = '0';
    expect(isDesktopBuild()).toBe(false);
  });

  it('isTauriDesktop requires desktop flag and Tauri internals', () => {
    process.env.NEXT_PUBLIC_DUCKCLAW_DESKTOP = '1';
    expect(isTauriDesktop()).toBe(false);
    vi.stubGlobal('window', { __TAURI_INTERNALS__: {} } as Window);
    expect(isTauriDesktop()).toBe(true);
  });
});
