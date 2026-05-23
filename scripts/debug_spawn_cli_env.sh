#!/usr/bin/env bash
# Diagnóstico local: por qué `spawn` no está en PATH (debug session fd1dbb).
set -euo pipefail

LOG_PATH="${DUCKCLAW_DEBUG_LOG:-$(cd "$(dirname "$0")/.." && pwd)/.cursor/debug-fd1dbb.log}"
SESSION_ID="${DUCKCLAW_DEBUG_SESSION:-fd1dbb}"
RUN_ID="${DUCKCLAW_DEBUG_RUN_ID:-pre-fix}"

_log() {
  local hyp="$1" loc="$2" msg="$3" data="$4"
  printf '%s\n' "{\"sessionId\":\"${SESSION_ID}\",\"runId\":\"${RUN_ID}\",\"hypothesisId\":\"${hyp}\",\"location\":\"${loc}\",\"message\":\"${msg}\",\"data\":${data},\"timestamp\":$(($(date +%s) * 1000))}" >>"${LOG_PATH}"
}

which_spawn="$(command -v spawn 2>/dev/null || true)"
if [[ -n "${which_spawn}" ]]; then
  _log "A" "debug_spawn_cli_env.sh" "spawn in PATH" "{\"which\":\"${which_spawn}\"}"
else
  _log "A" "debug_spawn_cli_env.sh" "spawn NOT in PATH" "{\"which\":null,\"exit\":127}"
fi

_spawn_cli_dir="${SPAWN_CLI_DIR:-}"
_tilde_fail=false
if [[ "${_spawn_cli_dir}" == *"~"* ]]; then
  _tilde_fail=true
fi
if [[ -n "${_spawn_cli_dir}" && -f "${_spawn_cli_dir}/packages/cli/src/local/main.ts" ]]; then
  _log "B" "debug_spawn_cli_env.sh" "SPAWN_CLI_DIR resolves to local main" "{\"dir\":\"${_spawn_cli_dir}\",\"tilde_unexpanded\":${_tilde_fail}}"
else
  _log "B" "debug_spawn_cli_env.sh" "SPAWN_CLI_DIR does not point at fork CLI" "{\"dir\":\"${_spawn_cli_dir}\",\"tilde_unexpanded\":${_tilde_fail}}"
fi

_home_spawn="${HOME}/Desktop/spawn"
if [[ -f "${_home_spawn}/packages/cli/src/local/main.ts" ]]; then
  _log "C" "debug_spawn_cli_env.sh" "fork local main exists" "{\"path\":\"${_home_spawn}/packages/cli/src/local/main.ts\"}"
else
  _log "C" "debug_spawn_cli_env.sh" "fork local main missing" "{\"path\":\"${_home_spawn}\"}"
fi

if [[ -f "${_home_spawn}/packages/cli/cli.js" ]]; then
  _log "D" "debug_spawn_cli_env.sh" "cli.js built" "{\"path\":\"${_home_spawn}/packages/cli/cli.js\"}"
else
  _log "D" "debug_spawn_cli_env.sh" "cli.js not built (bun run build needed)" "{\"path\":\"${_home_spawn}/packages/cli/cli.js\"}"
fi

bun_path="$(command -v bun 2>/dev/null || true)"
_log "E" "debug_spawn_cli_env.sh" "bun availability" "{\"bun\":\"${bun_path:-null}\"}"

_spawn_home="${HOME}/Desktop/spawn/manifest.json"
_duck_in_fork=false
if [[ -f "${_spawn_home}" ]] && grep -q '"duckclaw"' "${_spawn_home}" 2>/dev/null; then
  _duck_in_fork=true
fi
_log "F" "debug_spawn_cli_env.sh" "fork manifest has duckclaw agent" "{\"fork_manifest\":\"${_spawn_home}\",\"has_duckclaw\":${_duck_in_fork}}"

_cwd_manifest="$(pwd)/manifest.json"
_cwd_has_duck=false
if [[ -f "${_cwd_manifest}" ]] && grep -q '"duckclaw"' "${_cwd_manifest}" 2>/dev/null; then
  _cwd_has_duck=true
fi
_log "G" "debug_spawn_cli_env.sh" "cwd manifest used by spawn CLI" "{\"cwd\":\"$(pwd)\",\"manifest\":\"${_cwd_manifest}\",\"has_duckclaw\":${_cwd_has_duck}}"

_cache_manifest="${HOME}/.cache/spawn/manifest.json"
_cache_has_duck=false
if [[ -f "${_cache_manifest}" ]] && grep -q '"duckclaw"' "${_cache_manifest}" 2>/dev/null; then
  _cache_has_duck=true
fi
_log "H" "debug_spawn_cli_env.sh" "cached manifest (upstream fallback)" "{\"cache\":\"${_cache_manifest}\",\"has_duckclaw\":${_cache_has_duck}}"

_shared="${HOME}/Desktop/spawn/packages/cli/node_modules/@openrouter/spawn-shared"
_has_shared=false
[[ -d "${_shared}" ]] && _has_shared=true
_log "I" "debug_spawn_cli_env.sh" "spawn workspace package linked" "{\"spawn_shared\":\"${_shared}\",\"present\":${_has_shared}}"

echo "Wrote diagnostics to ${LOG_PATH}"
echo "spawn in PATH: ${which_spawn:-<missing>}"
echo "SPAWN_CLI_DIR=${SPAWN_CLI_DIR:-<unset>}"
echo "Use: export SPAWN_CLI_DIR=\"\$HOME/Desktop/spawn\"  # not ~/Desktop/spawn"
echo "Or install: curl -fsSL https://openrouter.ai/labs/spawn/cli/install.sh | bash"
echo "Or run: bash \"\$HOME/Desktop/spawn/sh/local/duckclaw.sh\""
