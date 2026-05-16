# ExilProductions/discord-mcp — imagen MCP HTTP (Discord Gateway en proceso aparte).
# Context: directorio padre debe contener subcarpeta `discord-src/` con clone del repo.
FROM python:3.12-slim-bookworm AS base
RUN pip install --no-cache-dir uv
WORKDIR /srv
COPY discord-src/pyproject.toml discord-src/uv.lock discord-src/DISCORD_MCP_EXIL.md ./
COPY discord-src/src ./src
RUN uv sync --frozen --no-dev
ENV PATH="/srv/.venv/bin:$PATH"
WORKDIR /srv
EXPOSE 8010
CMD ["python", "-m", "discord_mcp.main"]
