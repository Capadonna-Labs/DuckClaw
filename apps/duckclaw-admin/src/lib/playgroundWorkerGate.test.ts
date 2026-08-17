import { describe, expect, it } from 'vitest';
import {
  hasVisiblePlaygroundWorkers,
  shouldRedirectToProjectsForMissingWorkers,
  WORKER_REQUIRED_PROJECTS_HREF,
} from './playgroundWorkerGate';

describe('hasVisiblePlaygroundWorkers', () => {
  it('returns false for empty or missing lists', () => {
    expect(hasVisiblePlaygroundWorkers(undefined)).toBe(false);
    expect(hasVisiblePlaygroundWorkers(null)).toBe(false);
    expect(hasVisiblePlaygroundWorkers([])).toBe(false);
  });

  it('returns false when only phantom default/scaffold workers exist', () => {
    expect(hasVisiblePlaygroundWorkers(['default'])).toBe(false);
    expect(hasVisiblePlaygroundWorkers([{ id: 'default', label: 'Default' }])).toBe(false);
    expect(
      hasVisiblePlaygroundWorkers([
        { id: 'default', label: 'Default' },
        { id: 'internal_scaffold', label: 'Scaffold' },
      ])
    ).toBe(false);
  });

  it('returns true when at least one real worker exists', () => {
    expect(hasVisiblePlaygroundWorkers(['research'])).toBe(true);
    expect(
      hasVisiblePlaygroundWorkers([
        { id: 'default', label: 'Default' },
        { id: 'ops', label: 'Ops' },
      ])
    ).toBe(true);
  });
});

describe('shouldRedirectToProjectsForMissingWorkers', () => {
  it('does not redirect while loading or before config is loaded', () => {
    expect(
      shouldRedirectToProjectsForMissingWorkers({
        configLoading: true,
        configError: null,
        configLoaded: false,
        workers: [],
      })
    ).toBe(false);
    expect(
      shouldRedirectToProjectsForMissingWorkers({
        configLoading: false,
        configError: null,
        configLoaded: false,
        workers: [],
      })
    ).toBe(false);
  });

  it('does not redirect on API error', () => {
    expect(
      shouldRedirectToProjectsForMissingWorkers({
        configLoading: false,
        configError: 'gateway down',
        configLoaded: false,
        workers: [],
      })
    ).toBe(false);
  });

  it('redirects once when config loaded with no real workers', () => {
    expect(
      shouldRedirectToProjectsForMissingWorkers({
        configLoading: false,
        configError: null,
        configLoaded: true,
        workers: ['default'],
      })
    ).toBe(true);
    expect(
      shouldRedirectToProjectsForMissingWorkers({
        configLoading: false,
        configError: null,
        configLoaded: true,
        workers: [],
        alreadyRedirected: true,
      })
    ).toBe(false);
  });

  it('does not redirect when a real worker exists', () => {
    expect(
      shouldRedirectToProjectsForMissingWorkers({
        configLoading: false,
        configError: null,
        configLoaded: true,
        workers: [{ id: 'ops', label: 'Ops' }],
      })
    ).toBe(false);
  });
});

describe('WORKER_REQUIRED_PROJECTS_HREF', () => {
  it('points to projects onboarding query', () => {
    expect(WORKER_REQUIRED_PROJECTS_HREF).toBe('/projects?onboarding=worker-required');
  });
});
