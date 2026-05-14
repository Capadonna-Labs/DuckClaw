# Núcleo nativo edge (`edge_core`)

Las fuentes canónicas están en **`integrations/edge-devices/native/`** (raíz del monorepo).

Compila `edge_core.cpp` + `edge_core.h` en esa carpeta y define `DUCKCLAW_EDGE_LIB_PATH` apuntando al `.so` / `.dylib` generado. No dupliques estos archivos bajo `forge/skills/`.
