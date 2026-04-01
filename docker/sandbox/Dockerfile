# duckclaw/sandbox — imagen base para el Strix Sandbox
# Spec: specs/Sandbox_de_Ejecucion_Libre_Basado_en_Strix.md §2
#
# Build: docker build -t duckclaw/sandbox:latest docker/sandbox/
# Uso  : gestionado automáticamente por StrixSandboxManager

FROM python:3.11-slim

# Instalar uv como gestor de paquetes.
RUN pip install --no-cache-dir uv

# Dependencias analíticas requeridas por la spec (pandas, matplotlib, duckdb)
# + scipy, sklearn para análisis avanzado
RUN pip install --no-cache-dir \
        pandas==2.2.3 \
        matplotlib==3.9.4 \
        mplfinance==0.12.10b0 \
        seaborn==0.13.2 \
        duckdb==1.2.0 \
        scipy==1.14.1 \
        scikit-learn==1.6.1 \
        pyarrow==19.0.1 \
        requests==2.32.3 \
        vaderSentiment==3.3.2 \
    && rm -rf /root/.cache/pip

# Dependencias browser/LLM para automatización en sandbox (según requerimiento).
RUN uv pip install --system browser-use langchain-openai playwright \
    && python -m playwright install --with-deps chromium

# Estructura de directorios del workspace
RUN mkdir -p /workspace/data /workspace/output

WORKDIR /workspace

# Usuario sin privilegios (refuerza --cap-drop=ALL en runtime)
RUN useradd -m sandbox
USER sandbox

CMD ["tail", "-f", "/dev/null"]
