# Browse MCP — daemon timeout

## Síntoma

`Timeout waiting for daemon to start` al llamar `browser_navigate` / tools del plugin `plugin-browse-browser`.

## Causa raíz en esta máquina (seguro)

**No hay Google Chrome instalado.** Solo Brave:

`/Applications/Brave Browser.app/Contents/MacOS/Brave Browser`

El daemon `browse-cli` busca Chrome en rutas fijas (`Google Chrome.app`). Si no arranca en **30s**, lanza `Timeout waiting for daemon to start`.

Verificado: con `CHROME_PATH` apuntando a Brave, `browse --json open http://127.0.0.1:3001/login` responde en ~3s.

Otras causas posibles:

1. PID stale en `$TMPDIR/browse-default.pid`
2. Conflicto con Playwright headed / otro Chromium
3. Permisos macOS (Accessibility para Cursor)

## Fix recomendado

### A) `CHROME_PATH` → Brave (sin instalar Chrome)

En Cursor → Settings → MCP → server del browse plugin → **Environment**:

```
CHROME_PATH=/Applications/Brave Browser.app/Contents/MacOS/Brave Browser
```

O en shell antes de reiniciar Cursor:

```bash
export CHROME_PATH="/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
rm -f "$TMPDIR"/browse-default.pid
```

Luego **Restart** del MCP `plugin-browse-browser`.

### B) Instalar Google Chrome

[https://www.google.com/chrome/](https://www.google.com/chrome/) — el launcher encuentra la ruta por defecto.

### C) Alternativa estable para DuckClaw Admin

Playwright local (`.tmp/ui-probe/`) contra `http://127.0.0.1:3001` — no depende del daemon browse.

## Limpieza rápida

```bash
rm -f "$TMPDIR"/browse-default.pid
pkill -f 'browse.*daemon' 2>/dev/null || true
```
