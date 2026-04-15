# Multi-Vault System

Implementa bóvedas privadas por usuario con hot-switch:

- `db/system.duckdb` guarda el registry `main.user_vaults`.
- Cada usuario tiene su carpeta en `db/private/{user_id}/`.
- La bóveda activa se resuelve por `user_id`; si no existe, se crea `default.duckdb`.

## Comandos `/vault`

- `/vault`: muestra bóveda activa, ruta y tamaño.
- `/vault list`: lista bóvedas del usuario.
- `/vault new <name>`: crea una bóveda nueva.
- `/vault use <vault_id>`: cambia la bóveda activa.
- `/vault rm <vault_id>`: elimina una bóveda (si era activa, vuelve a `default`).

## Gateway y DB Writer (Path-Aware)

- `POST /api/v1/agent/chat` resuelve `vault_db_path` por `user_id` y lo propaga al grafo.
- `POST /api/v1/db/write` acepta/encola:
  - `user_id`
  - `db_path`
  - `query`
  - `params`
- El DB Writer ejecuta cada escritura contra el `db_path` del payload.

## Seguridad de rutas

- Solo se aceptan rutas dentro de `db/private/{user_id}/`.
- Se bloquean rutas externas (path traversal o archivos fuera del espacio del usuario).

## See also / Ver también

- [API Gateway (HTTP overview + Python reference)](api/api_gateway.md)
- [DB Writer](api/db_writer.md)
- [Singleton Writer](architecture/singleton_writer.md)
- [Operations hub](operations/index.md)
