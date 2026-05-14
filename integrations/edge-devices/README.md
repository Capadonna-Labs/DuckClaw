# Edge devices (`libedgecore`)

Integración en un solo sitio: **fuentes C**, bindings **ctypes** y **Streamlit** para telemetría.

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
