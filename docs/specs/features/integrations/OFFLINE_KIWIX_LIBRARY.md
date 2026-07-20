# Offline Kiwix + espejo local del vault

**Estado:** implemented  
**Relacionado:** research `web_search`, `DUCKCLAW_KNOWLEDGE_ALLOWED_ROOTS`, DOCUMENT_TOOLBOX.md

## Objetivo

Dos capas de conocimiento **sin red** (sin Project NOMAD):

| Capa | Ubicación | Tool / mecanismo |
|------|-----------|------------------|
| Enciclopedia (ZIM) | Storage **local** `DUCKCLAW_KIWIX_ZIM_DIR` (nunca GDrive) | `kiwix_search` |
| Bóveda propia | Espejo local de GDrive → `DUCKCLAW_VAULT_MIRROR_DIR` | `project_knowledge` + roots FS |
| Web (si hay red) | — | `web_search` / Tavily opcional |

## Contrato `.env`

```bash
# Enciclopedia ZIM (solo disco local)
DUCKCLAW_KIWIX_ZIM_DIR=~/DuckClawOffline/zim

# Espejo de la bóveda GDrive → local (rsync)
DUCKCLAW_VAULT_SOURCE_DIR=/path/to/MacMiniVault   # origen (GDrive)
DUCKCLAW_VAULT_MIRROR_DIR=~/DuckClawOffline/vault # destino local
```

- `knowledge_allowed_roots()` **antepone** `DUCKCLAW_VAULT_MIRROR_DIR` si existe, para preferir lectura local cuando Drive no está.
- Sync: `uv run duckops knowledge mirror` (rsync `-a`). Flag `--delete` opcional para espejo exacto.

## Tool `kiwix_search`

- Skill: `research` (mismo pack) o config `kiwix_enabled`.
- Requiere `kiwix-search` en PATH (`brew install kiwix-tools`) y al menos un `.zim` en el dir.
- Sin ZIMs / sin CLI: tool no registrada o mensaje accionable (no crash).

## Política agente

1. Con red: `web_search` para actualidad.
2. Sin red / fallo web: `kiwix_search` + `search_project_knowledge` (hub + FS bajo mirror).
3. No inventar hechos de enciclopedia.

## Operación humana

```bash
mkdir -p ~/DuckClawOffline/zim ~/DuckClawOffline/vault
brew install kiwix-tools
# Descargar ZIM compacto desde https://library.kiwix.org → ZIM_DIR
uv run duckops knowledge mirror
```

## Fuera de alcance

- NOMAD, mapas ProtoMaps, ZIMs en Google Drive.
