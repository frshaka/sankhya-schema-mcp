#!/usr/bin/env bash
export SANKHYA_DB_HOST="localhost"
export SANKHYA_DB_PORT="1521"
export SANKHYA_DB_SERVICE="XE"
export SANKHYA_DB_USER="SKCONTAINER"
export SANKHYA_DB_PASSWORD="tecsis"

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export LD_LIBRARY_PATH="$DIR/instantclient:$LD_LIBRARY_PATH"
exec "$DIR/.venv/bin/python" "$DIR/src/server.py"
