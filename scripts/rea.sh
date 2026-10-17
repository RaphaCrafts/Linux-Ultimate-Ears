#!/usr/bin/env bash
# Use the pinned, project-local REA and JADX without changing agent configuration.
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
rea_cli="$project_root/.local/tools/node_modules/.bin/rea"
jadx_jar="$project_root/.local/tools/jadx-headless-mcp-0.7.1-all.jar"
if [[ ! -x "$rea_cli" || ! -f "$jadx_jar" ]]; then
  echo 'Research tools missing. Follow docs/research-workflow.md.' >&2
  exit 1
fi
expected='6e5eacf500b64292bfb73c49797c1958f6ee44646e43e868039ae7feb573ff75'
actual="$(sha256sum -- "$jadx_jar")"
if [[ "${actual%% *}" != "$expected" ]]; then
  echo 'JADX engine SHA-256 does not match the pinned REA engine.' >&2
  exit 1
fi
export REA_JADX_MCP_JAR="$jadx_jar"
exec "$rea_cli" "$@"
