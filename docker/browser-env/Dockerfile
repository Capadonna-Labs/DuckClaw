# duckclaw/browser-env — Strix browser sandbox (browser-use, Playwright, Xvfb, noVNC)
# Specs: specs/features/Strix Browser Sandbox.md, specs/features/OSINT JobHunter (Web-Wide Recruitment Agent).md
#
# Build: docker build -t duckclaw/browser-env:latest docker/browser-env/
# Runtime: STRIX_BROWSER_IMAGE=duckclaw/browser-env:latest (see packages/agents/.../sandbox.py)
#
# Depuración visual: publicar 6080 (p. ej. STRIX_BROWSER_PUBLISH_NOVNC=1 o docker run -p 6080:6080).
# URL típica: http://127.0.0.1:6080/vnc.html (launch.sh de novnc). Solo entornos de confianza.

FROM python:3.11-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    DISPLAY=:99 \
    PYTHONUNBUFFERED=1

COPY strix-browser-init.sh /usr/local/bin/strix-browser-init.sh
RUN chmod +x /usr/local/bin/strix-browser-init.sh

RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    fluxbox \
    x11vnc \
    novnc \
    python3-websockify \
    chromium \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Playwright (navegador usado por browser-use). noVNC: /usr/share/novnc/utils/launch.sh + python3-websockify (apt).
RUN pip install --no-cache-dir \
    playwright==1.49.1 \
    pandas==2.2.3 \
    pyarrow==19.0.1 \
    "pydantic>=2.6,<3" \
    "browser-use>=0.1.40" \
    "langchain-openai>=0.2.10" \
    && playwright install --with-deps chromium \
    && rm -rf /root/.cache/pip

EXPOSE 6080

RUN mkdir -p /workspace/data /workspace/output \
    && useradd -m -u 1000 sandbox \
    && chown -R 1000:1000 /workspace /ms-playwright

USER sandbox
WORKDIR /workspace

CMD ["tail", "-f", "/dev/null"]
