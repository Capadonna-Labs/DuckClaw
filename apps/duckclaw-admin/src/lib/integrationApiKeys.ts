/** Helpers for Integraciones → API keys (catalog from gateway). */

export type IntegrationCatalogScope = 'tenant' | 'global' | 'actor';

export function integrationSettingsHref(): string {
  return '/integraciones?tab=keys';
}

export function integrationScopeLabel(scope: IntegrationCatalogScope): string {
  switch (scope) {
    case 'tenant':
      return 'Workspace (tenant)';
    case 'global':
      return 'Global plataforma';
    case 'actor':
      return 'Personal (actor)';
    default: {
      const exhaustive: never = scope;
      return exhaustive;
    }
  }
}
