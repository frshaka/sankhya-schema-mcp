#!/usr/bin/env bash
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

load_env() {
    [ -f "$1" ] || return 0
    set -a
    # shellcheck disable=SC1090
    source "$1"
    set +a
}

# 1. .env geral do MCP (base/defaults)
load_env "$DIR/.env"
# 2. .sankhya-mcp.env do projeto (override) — mesma ordem do start.ps1
load_env "$PWD/.sankhya-mcp.env"

export LD_LIBRARY_PATH="$DIR/instantclient:$LD_LIBRARY_PATH"
exec "$DIR/.venv/bin/python" "$DIR/src/server.py"
