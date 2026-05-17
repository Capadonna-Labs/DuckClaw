# Origen: retoPWRSomegahack

El código de esta carpeta proviene del repositorio del hackathon:

**https://github.com/ManePeqsiCoda/retoPWRSomegahack**

## Migración al monorepo

| Antes (hackathon) | Ahora (DuckClaw) |
|-------------------|------------------|
| Raíz del repo Next | `apps/duckclaw-admin/` |
| `npm` / `package-lock.json` | `pnpm` / `pnpm-lock.yaml` |
| CRM + panel mezclados | **Admin UI** activa; CRM = [módulo legacy](docs/legacy-crm-module.md) |
| `external/retoPWRSomegahack` (clone local) | Obsoleto; usar esta app |

Rama de integración: `samuel_dev-interfaz` → fusionada en `main`.

## Documentación actual

- Entrada: [README.md](README.md)
- Índice: [docs/README.md](docs/README.md)
- Spec SDD: [`specs/features/platform/DUCKCLAW_ADMIN_UI.md`](../../specs/features/platform/DUCKCLAW_ADMIN_UI.md)

## Clonar el repo original (referencia)

Solo si necesitas comparar historial o recuperar rutas CRM eliminadas en la migración:

```bash
git clone https://github.com/ManePeqsiCoda/retoPWRSomegahack.git /tmp/retoPWRSomegahack
```

No clones dentro de `duckclaw/external/` salvo comparación puntual; el producto soportado vive en `apps/duckclaw-admin`.
