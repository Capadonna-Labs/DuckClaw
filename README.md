# DuckClaw 🦆⚔️

**High-performance C++ analytical memory layer for sovereign AI agents.**

Optimized for Cross-Platform (Win/Lin/Mac) · Multi-tenant · Microservices Ready · Powered by DuckDB

---

## Architecture (Monorepo)

DuckClaw is now organized as a modular monorepo to support high scalability and independent deployments.

```
duckclaw/
├── packages/               # Lógica modular
│   ├── core/              # DuckDB Native (C++)
│   ├── agents/            # LangGraph & Workers
│   └── shared/            # Utils, CLI & Integrations
├── services/              # Microservicios
│   ├── api-gateway/       # FastAPI Gateway
│   └── db-writer/         # Singleton Writer Bridge
├── config/                # Centralización de configuración
├── data/                  # Datalake & Databases
├── docker/                # Multi-stage Dockerfiles
└── specs/                 # Technical Specs (SDM)
```

## Key Components

- **Singleton Writer Bridge**: Prevents DuckDB write locks by queuing all modifications in Redis.
- **API Gateway**: Decouples network/auth from agent logic, supporting SSE streaming.
- **Cross-Platform CLI**: `duckops` (Python-based) manages services on Linux, Windows, and macOS.

## Quick Start (Docker)

```bash
docker build -t duckclaw-base -f docker/base/Dockerfile .
docker build -t duckclaw-api -f docker/api/Dockerfile .
```

## Spec-Driven Management (SDM)

This project follows **SDM**. No feature is implemented without an approved specification in `specs/`.

---
Built by [IoTCoreLabs](https://iotcorelabs.io)
