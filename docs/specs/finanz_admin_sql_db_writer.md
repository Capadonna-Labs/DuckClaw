# Finanz admin_sql db-writer

**Scope:** contract between Finanz (and related workers), the API Gateway, Redis queues, and the singleton **DB-Writer** for `admin_sql` and related durable mutations. Keeps ledger-critical writes on a single ACID path.

**Where to read the full spec:** canonical file in the repo:

`specs/features/Finanz admin_sql db-writer.md`

**Related docs:** [Singleton Writer](../architecture/singleton_writer.md) · [DB Writer API](../api/db_writer.md) · [Operations / Commands](../COMANDOS.md)
