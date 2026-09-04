#!/usr/bin/env bash
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Parser chave=valor — NÃO usa `source`: um .env de um repositório qualquer não
# deve executar comandos no host. Mesmo comportamento do Import-EnvFile do start.ps1.
load_env() {
    [ -f "$1" ] || return 0
    local line key value
    while IFS= read -r line || [ -n "$line" ]; do
        line="${line#"${line%%[![:space:]]*}"}"
        line="${line%"${line##*[![:space:]]}"}"
        case "$line" in
            ''|'#'*) continue ;;
        esac
        line="${line#export }"
        case "$line" in
            *=*) ;;
            *) continue ;;
        esac
        key="${line%%=*}"
        value="${line#*=}"
        key="${key%"${key##*[![:space:]]}"}"
        value="${value#"${value%%[![:space:]]*}"}"
        value="${value%"${value##*[![:space:]]}"}"
        [[ $key =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
        case "$value" in
            \"*\") value="${value#\"}"; value="${value%\"}" ;;
            \'*\') value="${value#\'}"; value="${value%\'}" ;;
        esac
        export "$key=$value"
    done < "$1"
}

# 1. .env geral do MCP (base/defaults)
load_env "$DIR/.env"
# 2. .sankhya-mcp.env do projeto (override) — mesma ordem do start.ps1
load_env "$PWD/.sankhya-mcp.env"

export LD_LIBRARY_PATH="$DIR/instantclient:$LD_LIBRARY_PATH"
exec "$DIR/.venv/bin/python" "$DIR/src/server.py"
