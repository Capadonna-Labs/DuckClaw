# Proyectos Forge (local)

Las carpetas `forge/projects/<slug>/` **no se versionan** (`.gitignore`).

## Equipo por defecto (`.env`)

Define tu equipo en el **`.env` local** (no en el repo):

```bash
# Miembros: ids de carpeta bajo forge/templates/ (coma-separados)
DUCKCLAW_TEAM_MEMBERS=Worker-A,Worker-B

# Opcional
DUCKCLAW_TEAM_COORDINATOR=Worker-A
DUCKCLAW_TEAM_DISPLAY_NAME=Mi equipo
DUCKCLAW_TEAM_ID=mi-equipo
DUCKCLAW_TEAM_VAULT_ID=mi_vault
DUCKCLAW_TEAM_SHARED_CONTEXT_FILE=./config/team_context.md
# DUCKCLAW_TEAM_SHARED_CONTEXT="texto inline…"
```

La consola admin importa este bloque como preset; Playground y `/workers` resuelven los mismos ids.

## Disco

Al crear un proyecto en la UI se escribe `project.yaml` + opcional `_shared/context.md` solo en tu máquina.
