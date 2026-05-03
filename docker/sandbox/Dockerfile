# duckclaw/sandbox — imagen base para el Strix Sandbox
# Spec: specs/features/Strix Sandbox & Security Policy Engine (Zero-Trust Execution).md §2
#
# ML4T: solo diagnostic + event backtest runtime (extras [backtest]), sin ml4t-data —
# ingestión de mercado sigue en DuckClaw (Gateway / DuckDB).
#
# Build: docker build -t duckclaw/sandbox:latest docker/sandbox/
# Uso  : gestionado automáticamente por StrixSandboxManager

FROM python:3.12-slim

# Instalar uv como gestor de paquetes.
RUN pip install --no-cache-dir uv

# Dependencias analíticas: pandas, matplotlib, duckdb; scipy + sklearn (HRP);
# Cabecera inyectada en sandbox.py menciona pandas, scipy, pypfopt, ML4T (diagnostic/backtest).
# + yfinance (VIX/Yahoo; solo si sandbox tiene red o datos cacheados offline)
RUN pip install --no-cache-dir \
        pandas==2.2.3 \
        matplotlib==3.9.4 \
        mplfinance==0.12.10b0 \
        seaborn==0.13.2 \
        duckdb==1.2.0 \
        scipy==1.14.1 \
        scikit-learn==1.6.1 \
        PyPortfolioOpt==1.6.0 \
        pyarrow==19.0.1 \
        requests==2.32.3 \
        vaderSentiment==3.3.2 \
        yfinance==0.2.66 \
    && rm -rf /root/.cache/pip

# ML4T: diagnóstico + motor backtest — sin extras [data] ni [viz]/[all] (pip install ml4t-diagnostic[backtest]==0.1.0b15)
RUN pip install --no-cache-dir "ml4t-diagnostic[backtest]==0.1.0b15" \
    && rm -rf /root/.cache/pip

RUN python -c "import ml4t.diagnostic, ml4t.backtest as _bt; print('ml4t ok:', _bt.__file__)"

# Dependencias browser/LLM para automatización en sandbox (según requerimiento).
RUN uv pip install --system browser-use langchain-openai playwright \
    && python -m playwright install --with-deps chromium

# Estructura de directorios del workspace
RUN mkdir -p /workspace/data /workspace/output

WORKDIR /workspace

# Usuario sin privilegios (refuerza --cap-drop=ALL en runtime)
RUN useradd -m sandbox \
    && chown -R sandbox:sandbox /workspace

USER sandbox

CMD ["tail", "-f", "/dev/null"]
