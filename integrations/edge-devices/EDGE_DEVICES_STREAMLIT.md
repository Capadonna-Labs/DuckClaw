# Edge devices (`libedgecore`)

El fichero `libedgecore.so` **no va en git** (suele ignorarse `*.so`). Tras un `git pull`, compila de nuevo o copia un `.so` ya generado a `native/`. El cliente Python también prueba rutas típicas del monorepo (`duckclaw/libedgecore.so`, `duckclaw/forge/skills/libedgecore.so`).

## Compilar la librería nativa (Linux / VPS)

Desde la raíz del monorepo:

```bash
cd integrations/edge-devices/native
g++ -O3 -shared -fPIC -std=c++14 edge_core.cpp -o libedgecore.so
```

En macOS el artefacto suele ser `libedgecore.dylib` (mismo comando sustituyendo el nombre de salida si lo deseas).

Opcional: exportar la ruta absoluta del `.so`:

```bash
export DUCKCLAW_EDGE_LIB_PATH="$PWD/libedgecore.so"
```

## Enlace entre dos edge devices (DEL)

Ver [SPEC.MD](SPEC.MD). Ejemplo entre dos portátiles:

```bash
# Portátil A
uv run python -m duckclaw_edge_devices.link --device-id LAPTOP-A --listen 0.0.0.0:9870 --stream

# Portátil B
uv run python -m duckclaw_edge_devices.link --device-id LAPTOP-B --connect 192.168.1.10:9870 --stream
```

## Dashboard Streamlit

Instalar dependencias del subproyecto y arrancar la UI:

```bash
cd integrations/edge-devices
uv sync
uv run streamlit run src/duckclaw_edge_devices/app.py
```

Desde la raíz del monorepo (sin `cd`):

```bash
uv run --project integrations/edge-devices streamlit run integrations/edge-devices/src/duckclaw_edge_devices/app.py
```

La app intenta cargar la librería en este orden (si no pasas ruta en el sidebar):

1. Variable de entorno `DUCKCLAW_EDGE_LIB_PATH`
2. `./libedgecore.so` o `./libedgecore.dylib` (directorio de trabajo actual)
3. `integrations/edge-devices/native/libedgecore.{so,dylib}`

## Bridge a Redis (workers)

El script `edge_bridge` en `duckclaw.forge.skills` usa el mismo cliente (`duckclaw_edge_devices.client`). En un checkout mínimo del VPS sincroniza al menos `integrations/edge-devices` y la dependencia editable de `duckclaw-agents`, o instala `duckclaw-edge-devices` en editable desde esta carpeta.

## API C

Ver `native/edge_core.h`: `EdgeTelemetry`, `read_system_frame`, `init_serial_port`, `read_sensor_frame`, `close_serial_port`.
