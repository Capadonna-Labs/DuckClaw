# Optimización de Pipeline CI/CD (Ubuntu)

## 1. Objetivo Arquitectónico
Reducir el tiempo de CI de 23 minutos a < 3 minutos mediante el uso de **GitHub Actions Cache** para los artefactos de compilación de C++ y la utilización de **Wheels pre-compilados** para las dependencias pesadas.

## 2. Estrategia de Optimización

### A. Caché de `uv` y `ccache`
`uv` es extremadamente rápido, pero no puede evitar la compilación de C++ si los archivos fuente cambian. Usaremos `ccache` para cachear los objetos compilados de C++.

### B. Docker Multi-Stage (La solución definitiva)
En lugar de compilar en el runner de GitHub, usaremos un **Docker Image Registry** (GitHub Container Registry - GHCR).
1.  **Build:** Un job separado que construye una imagen Docker con el core de `duckclaw` ya compilado.
2.  **Test:** Los jobs de test simplemente descargan esta imagen (que ya tiene todo compilado) y ejecutan los tests.

---

## 3. Especificación del Pipeline Optimizado (`.github/workflows/deploy.yml`)

```yaml
jobs:
  build-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      # 1. Cache de dependencias de uv
      - name: Cache uv
        uses: actions/cache@v3
        with:
          path: .venv
          key: ${{ runner.os }}-uv-${{ hashFiles('uv.lock') }}

      # 2. Cache de ccache (para C++)
      - name: Cache ccache
        uses: actions/cache@v3
        with:
          path: .ccache
          key: ${{ runner.os }}-ccache-${{ github.sha }}
          restore-keys: |
            ${{ runner.os }}-ccache-

      - name: Install dependencies
        run: |
          export CCACHE_DIR=$GITHUB_WORKSPACE/.ccache
          uv sync --extra serve
```

## 4. Especificación de Skill: `PrecompiledBinary`
Para evitar compilar DuckDB/pybind11:
*   **Acción:** En lugar de `uv sync` desde cero, configura tu entorno para usar **Wheels** (binarios pre-compilados) de DuckDB.
*   **Configuración:** Asegúrate de que tu `pyproject.toml` no fuerce la compilación desde fuente (`--no-binary :all:`). Deja que `uv` descargue el wheel oficial de DuckDB para Linux.

## 5. Protocolo de "Docker-as-a-Cache" (Recomendado)
Si el proyecto sigue creciendo, esta es la mejor forma:

1.  **Dockerfile:**
    ```dockerfile
    FROM python:3.12-slim
    RUN apt-get update && apt-get install -y build-essential cmake
    COPY . .
    RUN uv sync --extra serve # Compila una sola vez
    ```
2.  **GitHub Action:**
    *   El job de `build` construye la imagen y la sube a `ghcr.io/arevalojj2020/duckclaw:latest`.
    *   El job de `test` hace `docker pull` y ejecuta `pytest` dentro del contenedor.
    *   **Resultado:** El tiempo de test baja a segundos porque la compilación ya ocurrió en el job de `build`.