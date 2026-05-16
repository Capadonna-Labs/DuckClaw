# System overview

High-level view of how **ingress**, **agent compute**, **queues**, and **durable state** fit together. Canonical narrative and ASCII detail remain in the repository under **`specs/core/`** (for example `specs/core/00_Flujo de Vida del Dato (Wizard).md` and `specs/core/01_System_Infrastructure.md`). See the [Specs index](../specs/index.md) for how published docs relate to those paths.

## Architecture diagram (Mermaid)

```mermaid
flowchart TB
  subgraph Ingress["Ingress"]
    TG[Telegram / webhooks]
    HTTP[HTTP clients · n8n · Angular]
  end

  subgraph Gateway["API Gateway — services/api-gateway"]
    API[FastAPI · chat · db/write · fly · VLM · health]
  end

  subgraph Compute["Agent compute — read-only vaults"]
    MGR[Manager graph · LangGraph]
    WRK[Workers · forge tools · MCP]
  end

  subgraph Sidecars["Optional processes"]
    HB[services/heartbeat — proactive ticks]
    PM2[PM2 jobs — HRP weekly · MOC pipeline · …]
  end

  subgraph Async["Redis"]
    QW[(duckdb write queue)]
    DD[(dedup · caches · state_delta queues)]
  end

  subgraph Writer["Singleton writer"]
    DW[services/db-writer]
  end

  subgraph Data["Durable state"]
    VAULT[(DuckDB vaults — per-tenant / user)]
  end

  TG --> API
  HTTP --> API
  HB --> API
  PM2 -->|"enqueue SQL / alerts"| QW
  PM2 -->|"read-only jobs"| VAULT

  API --> MGR
  MGR --> WRK
  WRK -->|"read_sql · inspect_schema — read_only"| VAULT

  API -->|"POST /api/v1/db/write"| QW
  WRK -->|"StateDelta / finance enqueue"| DD
  DD --> QW

  QW --> DW
  DW -->|"ACID mutations"| VAULT
```

## Invariants (short)

| Concern | Rule |
|--------|------|
| Who writes DuckDB? | **Only** `services/db-writer` (singleton path). Gateway and workers use **read-only** opens for vault paths in normal operation. |
| How do agents persist? | Enqueues to Redis; DB-Writer applies in a transaction. |
| Where is truth? | Product/architecture detail: **`specs/`**; this page is an overview for MkDocs readers. |

## Related docs

- [Singleton Writer](singleton_writer.md) — queue contract and mutation path.
- [Tri-Cameral Memory](tri_cameral_memory.md) — SQL / PGQ / VSS roles.
- [Strix Sandbox](strix_sandbox.md) — isolated execution boundary.
- [Specs index](../specs/index.md) — curated links into `specs/`.
