# Smoke report â€” DuckClaw Full Docker

Date: 2026-09-18T22:14:44.8251995-05:00
Host: DESKTOP-6NCBEF1

## Results

| Check | Result |
|-------|--------|
| Docker Desktop | OK |
| Image build (wall) | 584s |
| First `compose up` â†’ health | 27s |
| Second `compose up` â†’ health | 13s |
| gateway /health | OK |
| admin /login | OK |
| Containers (gateway, db-writer, redis, knowledge-indexer, heartbeat, admin) | OK |
| Login credentials present in .env | OK (admin@duckclaw.local) |
| No quant_core / quant tables in base DB | OK |
| Manual .env / console edits | None required |

## Notes

- Stack path: `deploy/docker`
- Auth: `DUCKCLAW_ADMIN_EMAIL` / `DUCKCLAW_ADMIN_PASSWORD` from `.env`
- Quant-Trader / quant_core intentionally absent (import via worker zip = paso 2)
- Tailscale not required for this smoke (localhost only)

## Verdict

**PASS** â€” ready for launcher .exe smoke / friend PC after packaging images.
