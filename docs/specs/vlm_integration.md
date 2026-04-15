# VLM Integration

**Scope:** vision-language model (VLM) integration for DuckClaw (e.g. image understanding paths, gateway/agents configuration, and operational constraints on Mac vs server).

**Where to read the full spec:** canonical file in the repo:

`specs/features/VLM INTEGRATION.md`

## Operational quick reference (gateway)

The API Gateway ingests photos and visual documents for Telegram (and related paths) before the manager graph runs. Typical backends: **MLX** (`mlx_vlm` in-process or MLX HTTP) → **Gemini** when a key is set → **OpenAI vision** only if explicitly enabled.

| Variable | Role |
|----------|------|
| `GEMINI_API_KEY` / `GOOGLE_API_KEY` | Gemini VLM; also `DUCKCLAW_VLM_GEMINI_API_KEY`. |
| `OPENAI_API_KEY` | Vision only with `DUCKCLAW_VLM_ALLOW_OPENAI_VISION=1`. |
| `DUCKCLAW_VLM_PRIMARY` | `mlx` (default) or `openai` / `cloud` / `openai_first`. |
| `DUCKCLAW_VLM_ALLOW_OPENAI_VISION` | Must be truthy to use OpenAI for vision. |
| `DUCKCLAW_VLM_DISABLE_LOCAL_MLX_VLM`, `VLM_MLX_DISABLE_LOCAL`, `DUCKCLAW_VLM_MLX_DISABLE_LOCAL` | Disable in-process `mlx_vlm` when set truthy. |

If Gemini returns **503**, users may get a short Telegram notice suggesting retry or local MLX (Gemma VLM / `mlx_vlm`).

Full Spanish runbook (Redis, Telegram, PM2, tables above expanded): **[Commands (COMANDOS)](../COMANDOS.md)** §5.2.

**Related docs:** [Agents overview](../agents/adf_framework.md) · [SFT & conversation traces](../agents/sft_conversation_traces.md) · [Operations hub](../operations/index.md)
