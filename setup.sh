#!/usr/bin/env bash
# URL base do repositório e do instantclient Linux no GitHub Releases
REPO_URL="https://github.com/frshaka/sankhya-schema-mcp.git"
INSTANTCLIENT_URL="https://github.com/ratk/sankhya-schema-mcp-assets/releases/download/v1.0/instantclient-linux.zip"

set -e

echo "=== Setup Sankhya Schema MCP ==="
echo ""

# ---------------------------------------------------------------------------
# Determinar raiz do projeto
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -f "$SCRIPT_DIR/src/server.py" ] && [ -f "$SCRIPT_DIR/requirements.txt" ]; then
    PROJECT_ROOT="$SCRIPT_DIR"
    echo "[OK] Projeto encontrado em: $PROJECT_ROOT"
else
    DEFAULT_DIR="$HOME/projetos/sankhya-mcp"
    read -rp "Informe o caminho de instalação [Enter para $DEFAULT_DIR]: " USER_INPUT
    PROJECT_ROOT="${USER_INPUT:-$DEFAULT_DIR}"

    if [ -f "$PROJECT_ROOT/src/server.py" ]; then
        echo "[OK] Projeto já existe em: $PROJECT_ROOT"
    else
        echo "[0] Clonando repositório em: $PROJECT_ROOT ..."
        git clone "$REPO_URL" "$PROJECT_ROOT"
        echo "[OK] Repositório clonado."
    fi

    CLONED_SETUP="$PROJECT_ROOT/setup.sh"
    CURRENT_SCRIPT="$(realpath "${BASH_SOURCE[0]}")"
    RESOLVED_CLONE="$(realpath "$CLONED_SETUP" 2>/dev/null || echo '')"
    if [ "$CURRENT_SCRIPT" != "$RESOLVED_CLONE" ]; then
        echo ""
        echo "Continuando setup a partir do projeto clonado..."
        bash "$CLONED_SETUP"
        exit $?
    fi
fi

INSTANTCLIENT_DIR="$PROJECT_ROOT/instantclient"
ZIP_PATH="$PROJECT_ROOT/instantclient-linux.zip"
VENV_DIR="$PROJECT_ROOT/.venv"
REQUIREMENTS_FILE="$PROJECT_ROOT/requirements.txt"
START_SCRIPT="$PROJECT_ROOT/start.sh"

# ---------------------------------------------------------------------------
# 1. Oracle Instant Client
# ---------------------------------------------------------------------------
if [ -d "$INSTANTCLIENT_DIR" ] && ls "$INSTANTCLIENT_DIR"/libclntsh.so* 1>/dev/null 2>&1; then
    echo "[OK] instantclient/ já existe — pulando download."
else
    echo "[1/3] Baixando Oracle Instant Client para Linux..."

    if ! curl -fL -o "$ZIP_PATH" "$INSTANTCLIENT_URL"; then
        echo ""
        echo "[ERRO] Falha no download de: $INSTANTCLIENT_URL"
        echo ""
        echo "Instale o Oracle Instant Client manualmente:"
        echo "  1. Baixe 'instantclient-basic-linux.x64-*.zip' em:"
        echo "     https://www.oracle.com/database/technologies/instant-client/linux-x86-64-downloads.html"
        echo "  2. Extraia para '$INSTANTCLIENT_DIR'"
        echo "  3. Execute este script novamente."
        exit 1
    fi

    echo "[1/3] Extraindo instantclient-linux.zip..."
    unzip -q "$ZIP_PATH" -d "$PROJECT_ROOT"
    rm -f "$ZIP_PATH"

    if ! ls "$INSTANTCLIENT_DIR"/libclntsh.so* 1>/dev/null 2>&1; then
        echo "[ERRO] Extração falhou: libclntsh.so não encontrado em instantclient/"
        exit 1
    fi

    # Criar symlink libclntsh.so sem versão se não existir (necessário para oracledb)
    if [ ! -f "$INSTANTCLIENT_DIR/libclntsh.so" ]; then
        VERSIONED=$(ls "$INSTANTCLIENT_DIR"/libclntsh.so.* 2>/dev/null | head -1)
        if [ -n "$VERSIONED" ]; then
            ln -sf "$(basename "$VERSIONED")" "$INSTANTCLIENT_DIR/libclntsh.so"
        fi
    fi

    echo "[OK] instantclient/ extraído com sucesso."
fi

# ---------------------------------------------------------------------------
# Verificar libaio (dependência do Oracle Instant Client no Linux)
# Ubuntu 24+ renomeou libaio.so.1 para libaio.so.1t64 — cria symlink local
# ---------------------------------------------------------------------------
LIBAIO_PATH=$(ldconfig -p 2>/dev/null | grep "libaio.so" | awk '{print $NF}' | head -1)

if [ -z "$LIBAIO_PATH" ]; then
    echo ""
    echo "[AVISO] libaio não encontrado. Instale com:"
    echo "  Ubuntu 24+:    sudo apt-get install -y libaio1t64"
    echo "  Ubuntu 22/20:  sudo apt-get install -y libaio1"
    echo "  RHEL/CentOS:   sudo yum install -y libaio"
    echo ""
elif [ ! -f "$INSTANTCLIENT_DIR/libaio.so.1" ]; then
    # Se só existe libaio.so.1t64 (Ubuntu 24+), cria symlink dentro do instantclient/
    # para que LD_LIBRARY_PATH resolva sem sudo
    if echo "$LIBAIO_PATH" | grep -q "1t64"; then
        ln -sf "$LIBAIO_PATH" "$INSTANTCLIENT_DIR/libaio.so.1"
        echo "[OK] Symlink libaio.so.1 criado → $LIBAIO_PATH"
    fi
fi

# ---------------------------------------------------------------------------
# 2. Ambiente virtual Python
# ---------------------------------------------------------------------------
if [ -f "$VENV_DIR/bin/python" ]; then
    echo "[OK] Ambiente virtual já existe — pulando criação."
else
    echo "[2/3] Criando ambiente virtual Python..."
    python3 -m venv "$VENV_DIR"
    echo "[OK] Ambiente virtual criado."
fi

# ---------------------------------------------------------------------------
# 3. Dependências
# ---------------------------------------------------------------------------
echo "[3/3] Instalando dependências Python..."
"$VENV_DIR/bin/pip" install -r "$REQUIREMENTS_FILE" --quiet
echo "[OK] Dependências instaladas."

# ---------------------------------------------------------------------------
# 4. Tornar start.sh executável
# ---------------------------------------------------------------------------
chmod +x "$START_SCRIPT"

# ---------------------------------------------------------------------------
# 5. Registrar MCP no Claude Code
# ---------------------------------------------------------------------------
echo "[4/4] Registrando MCP no Claude Code..."

CLAUDE_JSON="$HOME/.claude.json"

python3 - <<PYEOF
import json, os

claude_json = "$CLAUDE_JSON"
start_script = "$START_SCRIPT"

os.makedirs(os.path.dirname(claude_json), exist_ok=True)

if os.path.exists(claude_json):
    with open(claude_json, "r", encoding="utf-8") as f:
        data = json.load(f)
else:
    data = {}

if "mcpServers" not in data:
    data["mcpServers"] = {}

if "sankhya-schema" in data["mcpServers"]:
    print("  [OK] MCP já registrado.")
else:
    data["mcpServers"]["sankhya-schema"] = {
        "type": "stdio",
        "command": "bash",
        "args": [start_script],
        "env": {}
    }
    with open(claude_json, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print("  [OK] MCP registrado com sucesso.")
PYEOF

echo ""
echo "=== Instalação concluída! ==="
echo "Próximo passo: edite as credenciais em start.sh, reinicie o Claude Code e rode /mcp para confirmar."
