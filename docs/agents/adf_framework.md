# Agent Definition Framework (ADF)

DuckClaw workers are assembled from declarative templates plus runtime skills.

## Required Building Blocks

- `manifest.yaml`: worker identity, capabilities, and bootstrap metadata.
- `soul.md`: role constraints, tone, and behavior contract.
- `domain_closure.md`: what is in/out of domain.
- Optional skills/atoms for specialized operations.

## Authoring Flow

1. Define scope and constraints in `soul.md` and `domain_closure.md`.
2. Register worker metadata in `manifest.yaml`.
3. Attach tools/skills in factory registration.
4. Validate routing and role behavior through traces/tests.

## Runtime Integration

- Manager graph decides assignment based on intent and available templates.
- Worker-specific prompts and skills are loaded from template metadata.
- Auditing and traces are emitted from the manager + worker nodes.
