# Project N.O.M.A.D. (opcional)

[Project N.O.M.A.D.](https://github.com/Crosstalk-Solutions/project-nomad) (Crosstalk Solutions, Apache 2.0) es un servidor de conocimiento offline: Wikipedia, libros, cursos, mapas y un asistente de IA local, con su propio panel en el puerto 8080. **No forma parte del stack por defecto de DuckClaw**: no se instala ni arranca nada hasta que lo pides, igual que ComfyUI o los conectores MCP del Admin.

## Levantarlo

```bash
uv run duckops nomad up        # primera vez: genera secretos aleatorios y descarga imágenes
uv run duckops nomad status
uv run duckops nomad logs
uv run duckops nomad down      # conserva datos y secretos
uv run duckops nomad url
```

`--dry-run` en cualquiera muestra los comandos sin ejecutarlos. Requisitos: Docker con `docker compose`. Sin la IA ocupa menos de 1 GB de RAM y unos 5 GB de disco; el contenido offline y los modelos suben mucho el disco.

Dónde queda todo: `~/.duckclaw/project-nomad/` (`.env` con los secretos, modo 0600, y `data/`). Se cambia con `DUCKCLAW_NOMAD_HOME`. El compose es `deploy/optional/project-nomad/docker-compose.yml`, adaptado de la plantilla oficial.

## Qué cambia respecto a la plantilla oficial

- Imagen **fijada** (`NOMAD_VERSION`, hoy `v1.35.1`) en vez de `latest` con descarga permanente. Para actualizar, cambia `NOMAD_VERSION` en el `.env` y repite `duckops nomad up`.
- **Secretos obligatorios y aleatorios** (la plantilla trae `replaceme`). No cambies las contraseñas de la base de datos cuando ya existe.
- El panel publica solo en **127.0.0.1**. `--bind` con otra dirección exige `--expose`.
- Se omiten Dozzle (visor de logs) y el actualizador interno, que montan otra vez el socket de Docker; el enlace «Service Logs & Metrics» del panel no funcionará, usa `duckops nomad logs`.

## Seguridad: lee esto antes de usarlo

El contenedor `admin` monta `/var/run/docker.sock`: lo necesita para iniciar y detener las aplicaciones que gestiona (Kiwix, Ollama, etc.). Quien controle el panel de NOMAD controla el Docker del equipo, lo que equivale a ser administrador (root). Por eso:

- Mantenlo en loopback o en una red privada de confianza, y nunca expongas el 8080 a internet.
- Úsalo en un equipo que puedas dedicarle, no en el servidor donde corre tu producción.
- Los modelos, libros y mapas son contenido de terceros con licencias propias.

## Integración con DuckClaw

Hoy es una aplicación aparte: DuckClaw no la consulta ni la configura. No hay un conector MCP verificado de NOMAD; si más adelante quieres que los agentes usen su IA local o su biblioteca, hará falta un diseño propio (por ejemplo, apuntar un proveedor local de modelos a su Ollama).
