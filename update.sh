#!/usr/bin/env bash
# Atualiza o Sankhya Schema MCP: baixa a versão publicada e reinstala as dependências.
#
# Pode rodar com o cliente MCP aberto. A versão nova só vale depois de
# reiniciar o cliente.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$DIR/.venv/bin/python"

if [ ! -x "$PYTHON" ]; then
    echo "[ERRO] Ambiente virtual não encontrado em $DIR/.venv. Rode o setup.sh." >&2
    exit 1
fi

echo "[1/3] Baixando a versão publicada..."
# --ff-only: com alteração local no clone, falha em vez de criar um merge.
if ! git -C "$DIR" pull --ff-only; then
    echo "[ERRO] git pull falhou. Verifique alterações locais em $DIR (git status)." >&2
    exit 1
fi

echo "[2/3] Reinstalando dependências..."
"$PYTHON" -m pip install -r "$DIR/requirements.txt" --quiet

# O driver do SQL Server é opcional: só atualiza quem já o tem instalado.
if "$PYTHON" -c "import pymssql" 2>/dev/null; then
    "$PYTHON" -m pip install -r "$DIR/requirements-sqlserver.txt" --quiet
fi

echo "[3/3] Conferindo o SDK MCP..."
if ! "$PYTHON" -c "import mcp.server.mcpserver"; then
    echo "[ERRO] O SDK MCP 2.x não ficou disponível no ambiente virtual." >&2
    exit 1
fi

echo "[OK] Atualizado. Reinicie o cliente MCP (Claude Code / Codex) para carregar a nova versão."
