# RADAR — External Intelligence Agent

## Propósito

RADAR monitorea el mundo técnico 24/7 y trae solo lo relevante
para el propietario. Opera en segundo plano via PM2 scheduled jobs.

## Fase: 4

## Jobs PM2

- `axis-cve-watcher`: cada 6 horas
- `axis-news-pulse`: cada 2 horas
- `axis-exploit-watch`: diario
- `axis-paper-harvest`: semanal
- `axis-mitre-sync`: mensual

Spec: SPEC-01 v0.2.0 §6.4 | PLAN ADF v1.0.0
