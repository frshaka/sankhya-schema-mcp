#!/usr/bin/env bash
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

set -a
source "$DIR/.env"
set +a

export LD_LIBRARY_PATH="$DIR/instantclient:$LD_LIBRARY_PATH"
exec "$DIR/.venv/bin/python" "$DIR/src/server.py"
