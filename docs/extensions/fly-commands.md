# Fly command extensions

DuckClaw core ships built-in slash commands (`/help`, `/vault`, `/workers`, …). Additional commands can be registered from **any external repository** without modifying DuckClaw source.

## Environment variables

| Variable | Example | Purpose |
|----------|---------|---------|
| `DUCKCLAW_EXTENSION_ROOT` | `/path/to/MyProduct` | Root of the external repo (`:` or `os.pathsep` for multiple) |
| `DUCKCLAW_EXTENSION_LIB_PATH` | `workers/duckclaw/lib` | Python plugin directory relative to each root (default: `lib`) |
| `DUCKCLAW_FLY_DISPATCHERS` | `fly_commands:dispatch` | Comma/semicolon list of `module:callable` entrypoints |
| `DUCKCLAW_FLY_MANIFEST` | `workers/duckclaw/fly_extension.yaml` | Optional YAML manifest (absolute or relative to extension root) |
| `DUCKCLAW_FLY_READ_ONLY_EXTRA` | `export-report,summarize-thread` | Extra commands safe for read-only vault opens |

## Dispatcher contract

```python
def dispatch(
    name: str,
    db: Any,
    chat_id: Any,
    args: str,
    **kwargs: Any,
) -> str | None:
    """
    name: parsed command without leading slash (e.g. trading_session)
    kwargs: requester_id, tenant_id, vault_user_id, entry_worker_id, username
    Return None if this dispatcher does not handle the command.
    """
```

Dispatchers are tried in order until one returns a non-`None` string.

## Manifest example (external repo)

```yaml
lib_path: workers/duckclaw/lib
package_name: my_product_lib
fly_dispatchers:
  - fly_commands:dispatch
read_only_commands:
  - my-command
help_entries:
  - name: my-command
    description: "Does something without LLM"
```

## Outbound charts

Register PNG payloads for the gateway/admin UI:

```python
from duckclaw.commands.fly_outbound import register_fly_outbound_chart_b64

register_fly_outbound_chart_b64(chat_id, png_b64, chart_name="snapshot.png")
```

The gateway collects charts via `pop_all_fly_outbound_charts(chat_id)` after `handle_command`.

## Read-only vault safety

`services/api-gateway/core/fly_command_invocation.py` merges core safe commands with `extension_fly_read_only_command_names()`. Extension commands that only read DuckDB should be listed in the manifest or `DUCKCLAW_FLY_READ_ONLY_EXTRA`.

## Worker skill hooks

Register additional LangChain tools when a worker graph is built (external product bridges, domain skills, etc.).

| Variable | Example | Purpose |
|----------|---------|---------|
| `DUCKCLAW_WORKER_SKILL_HOOKS` | `skill_hooks:register_worker_skills` | Colon/comma list of `module:callable` entrypoints (relative to extension lib) |

Manifest key `worker_skill_hooks` (same YAML file as fly commands):

```yaml
worker_skill_hooks:
  - skill_hooks:register_worker_skills
```

### Hook contract

```python
def register_worker_skills(
    *,
    tools: list[Any],
    spec: Any,
    db: Any,
    llm: Any,
    logical_worker_id: str,
    worker_path: str,
) -> None:
    """Append tools to the worker tool list. Exceptions are logged and skipped."""
```

Hooks run after core `skill_tool_registry` post-LLM registration and before homeostasis/sandbox tools.
