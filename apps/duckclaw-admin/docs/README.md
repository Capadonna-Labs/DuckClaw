# Documentación — DuckClaw Admin

Guías operativas de esta app. La **normativa** del producto está en el monorepo: [`specs/features/platform/DUCKCLAW_ADMIN_UI.md`](../../../specs/features/platform/DUCKCLAW_ADMIN_UI.md).

## Guías

| Archivo | Para quién | Tema |
|---------|------------|------|
| [architecture.md](architecture.md) | Arquitectos / backend | BFF, contrato admin API, seguridad |
| [environment.md](environment.md) | DevOps / local | Variables `.env` raíz vs `.env.local` |
| [development.md](development.md) | Frontend | Extender pantallas, lint, build, tests |
| [legacy-crm-module.md](legacy-crm-module.md) | Integración PQRSD | Código CRM heredado e IA vía gateway |

## Referencia histórica (hackathon)

Estos archivos describen el **CRM ciudadano** original; no sustituyen el README de la consola admin:

| Archivo | Nota |
|---------|------|
| [../PROJECT_DOCUMENTATION.md](../PROJECT_DOCUMENTATION.md) | Producto PQRSD Medellín (piloto) |
| [../BACKEND_IMPLEMENTATION_GUIDE.md](../BACKEND_IMPLEMENTATION_GUIDE.md) | APIs mock / MotherDuck del hack |
| [../TECHNICAL_SPECIFICATIONS.md](../TECHNICAL_SPECIFICATIONS.md) | Especificaciones técnicas legacy |
| [GATEWAY_IA_INTEGRATION.md](GATEWAY_IA_INTEGRATION.md) | Redirección → `legacy-crm-module.md` |

## Enlaces del monorepo

- Runbook PM2: [`docs/COMANDOS.md`](../../../docs/COMANDOS.md) (sección Admin UI)
- Gateway admin router: [`services/api-gateway/routers/admin.py`](../../../services/api-gateway/routers/admin.py)
- Plantillas workers: [`packages/agents/src/duckclaw/forge/templates/`](../../../packages/agents/src/duckclaw/forge/templates/)
