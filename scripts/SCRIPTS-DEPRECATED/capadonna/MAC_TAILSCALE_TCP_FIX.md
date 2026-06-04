# Mac: TCP a `100.75.4.17` no conecta (pero `tailscale ping` sí)

## Síntoma

```bash
curl http://100.75.4.17:8002/health   # cuelga
curl http://87.99.156.231:8002/health # {"status":"ok"}
```

`tailscale ping` usa el protocolo WireGuard de Tailscale, **no** prueba TCP al puerto 8002.

## En el VPS (ya aplicado o vía script)

```bash
bash scripts/SCRIPTS-DEPRECATED/capadonna/vps_fix_tailscale_api.sh
```

- UFW: `8002` + reglas `tailscale0` en `before.rules`
- `tailscale serve --bg 8002` → HTTPS MagicDNS en la tailnet

## En el Mac (orden recomendado)

1. **Actualizar Tailscale** (hay warning de versión cliente ≠ servidor):
   ```bash
   brew upgrade tailscale
   sudo tailscale down && sudo tailscale up
   ```

2. **Diagnóstico**:
   ```bash
   tailscale netcheck
   tailscale status
   route -n get 100.75.4.17   # debe salir interface utun*
   ```

3. **Probar MagicDNS (Serve)** — suele funcionar cuando la IP Tailscale no enruta TCP:
   ```bash
   curl -sS https://ubuntu-2gb-ash-1.tailc85db0.ts.net/health
   ```

4. **ACL en** [admin.tailscale.com](https://login.tailscale.com/admin/acls) — permitir tráfico entre nodos:
   ```json
   {
     "action": "accept",
     "src": ["autogroup:members"],
     "dst": ["autogroup:members:*"]
   }
   ```

5. **`.env` del gateway** — elige una opción que responda en `curl …/health`:

   | Opción | URLs |
   |--------|------|
   | Tailscale IP | `http://100.75.4.17:8002/api/...` |
   | MagicDNS Serve | `https://ubuntu-2gb-ash-1.tailc85db0.ts.net/api/...` |
   | IP pública (Hetzner) | `http://87.99.156.231:8002/api/...` (restringe firewall si puedes) |

Mismas rutas para `IBKR_PORTFOLIO_API_URL`, `IBKR_MARKET_DATA_URL`, `IBKR_EXECUTE_ORDER_URL`.
