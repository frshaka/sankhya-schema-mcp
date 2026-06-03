#!/usr/bin/env bash
# URL base do repositório e do instantclient Linux no GitHub Releases
REPO_URL="https://github.com/frshaka/sankhya-schema-mcp.git"
INSTANTCLIENT_URL="https://github.com/frshaka/sankhya-schema-mcp/releases/download/v1.1/instantclient-linux.zip"

set -e

# ---------------------------------------------------------------------------
# Parse argumentos
#   --config-dir <path>      Diretório onde gravar .claude.json e settings.json
#                            (default: $HOME/.claude.json + $HOME/.claude/settings.json)
#   --cli claude|codex|both  CLIs onde registrar o MCP (sem flag: menu interativo)
# ---------------------------------------------------------------------------
CONFIG_DIR=""
CLI=""
EXTRA_ARGS=()

while [ $# -gt 0 ]; do
    case "$1" in
        --config-dir)
            CONFIG_DIR="$2"
            shift 2
            ;;
        --config-dir=*)
            CONFIG_DIR="${1#*=}"
            shift
            ;;
        --cli)
            CLI="$2"
            shift 2
            ;;
        --cli=*)
            CLI="${1#*=}"
            shift
            ;;
        *)
            EXTRA_ARGS+=("$1")
            shift
            ;;
    esac
done

echo "=== Setup Sankhya Schema MCP ==="
echo ""

# ---------------------------------------------------------------------------
# Seleção de CLIs para registro do MCP
# - Com --cli claude|codex|both: usa o valor informado (não interativo)
# - Sem --cli: exibe menu interativo (default: Claude Code)
# ---------------------------------------------------------------------------
if [ -z "$CLI" ]; then
    echo "Em quais CLIs deseja registrar o MCP?"
    echo "  [1] Claude Code"
    echo "  [2] Codex CLI"
    echo "  [3] Ambos"
    read -rp "Escolha [Enter para 1]: " CLI_CHOICE
    case "$CLI_CHOICE" in
        ""|"1") CLI="claude" ;;
        "2")    CLI="codex" ;;
        "3")    CLI="both" ;;
        *)
            echo "[ERRO] Opção inválida: '$CLI_CHOICE'. Use 1, 2 ou 3."
            exit 1
            ;;
    esac
else
    CLI=$(echo "$CLI" | tr '[:upper:]' '[:lower:]')
    case "$CLI" in
        claude|codex|both) ;;
        *)
            echo "[ERRO] Valor inválido para --cli: '$CLI'. Use claude, codex ou both."
            exit 1
            ;;
    esac
fi

INSTALL_CLAUDE=0
INSTALL_CODEX=0
case "$CLI" in
    claude|both) INSTALL_CLAUDE=1 ;;
esac
case "$CLI" in
    codex|both) INSTALL_CODEX=1 ;;
esac

if [ "$INSTALL_CLAUDE" = "1" ]; then
    if [ -n "$CONFIG_DIR" ]; then
        CLAUDE_JSON="$CONFIG_DIR/.claude.json"
        SETTINGS_JSON="$CONFIG_DIR/settings.json"
        echo "[INFO] Usando diretório de configuração: $CONFIG_DIR"
    else
        CLAUDE_JSON="$HOME/.claude.json"
        SETTINGS_JSON="$HOME/.claude/settings.json"
        echo "[INFO] Usando configuração padrão do Claude Code."
    fi
fi

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
        if [ -n "$CONFIG_DIR" ]; then
            bash "$CLONED_SETUP" --config-dir "$CONFIG_DIR" --cli "$CLI"
        else
            bash "$CLONED_SETUP" --cli "$CLI"
        fi
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
if [ "$INSTALL_CLAUDE" = "1" ]; then

echo "[4/5] Registrando MCP no Claude Code..."

python3 - <<PYEOF
import json, os

claude_json = "$CLAUDE_JSON"
start_script = "$START_SCRIPT"

parent = os.path.dirname(claude_json)
if parent:
    os.makedirs(parent, exist_ok=True)

if os.path.exists(claude_json):
    with open(claude_json, "r", encoding="utf-8") as f:
        data = json.load(f)
else:
    data = {}

if "mcpServers" not in data:
    data["mcpServers"] = {}

if "sankhya-schema" in data["mcpServers"]:
    print(f"  [OK] MCP já registrado em {claude_json}.")
else:
    data["mcpServers"]["sankhya-schema"] = {
        "type": "stdio",
        "command": "bash",
        "args": [start_script],
        "env": {}
    }
    with open(claude_json, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"  [OK] MCP registrado em {claude_json}.")
PYEOF

# ---------------------------------------------------------------------------
# 6. Liberar permissoes das tools MCP no Claude Code
# ---------------------------------------------------------------------------
echo "[5/5] Liberando permissões das tools MCP..."

python3 - <<PYEOF
import json, os

settings_json = "$SETTINGS_JSON"

parent = os.path.dirname(settings_json)
if parent:
    os.makedirs(parent, exist_ok=True)

if os.path.exists(settings_json):
    with open(settings_json, "r", encoding="utf-8") as f:
        settings = json.load(f)
else:
    settings = {}

permission_rule = "mcp__sankhya-schema__*"

if "permissions" not in settings:
    settings["permissions"] = {"allow": [permission_rule]}
    changed = True
elif "allow" not in settings["permissions"]:
    settings["permissions"]["allow"] = [permission_rule]
    changed = True
elif permission_rule not in settings["permissions"]["allow"]:
    settings["permissions"]["allow"].append(permission_rule)
    changed = True
else:
    changed = False
    print("  [OK] Permissões já configuradas.")

if changed:
    with open(settings_json, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
    print(f"  [OK] Permissões configuradas em {settings_json}.")
PYEOF

fi # fim INSTALL_CLAUDE

# ---------------------------------------------------------------------------
# 7. Registrar MCP no Codex CLI
# - Config: $CODEX_HOME/config.toml (default: ~/.codex/config.toml)
# - Codex não tem allow-list por tool; aprovação segue a approval policy global
# ---------------------------------------------------------------------------
if [ "$INSTALL_CODEX" = "1" ]; then
    echo "[Codex] Registrando MCP no Codex CLI..."

    CODEX_HOME_DIR="${CODEX_HOME:-$HOME/.codex}"
    CODEX_CONFIG="$CODEX_HOME_DIR/config.toml"

    if [ -f "$CODEX_CONFIG" ] && grep -Eq '^[[:space:]]*\[mcp_servers\.sankhya-schema\]' "$CODEX_CONFIG"; then
        echo "  [OK] MCP já registrado em $CODEX_CONFIG."
    else
        mkdir -p "$CODEX_HOME_DIR"
        # Garantir newline final no arquivo existente antes do append
        if [ -s "$CODEX_CONFIG" ] && [ -n "$(tail -c 1 "$CODEX_CONFIG")" ]; then
            echo "" >> "$CODEX_CONFIG"
        fi
        cat >> "$CODEX_CONFIG" <<EOF

[mcp_servers.sankhya-schema]
command = "bash"
args = ["$START_SCRIPT"]
EOF
        echo "  [OK] MCP registrado em $CODEX_CONFIG."
    fi
fi

echo ""
echo "=== Instalação concluída! ==="
echo "Próximo passo: edite as credenciais em .env (use .env.example como modelo)."
if [ "$INSTALL_CLAUDE" = "1" ]; then
    echo "Claude Code: reinicie e rode /mcp para confirmar. As tools foram liberadas automaticamente."
fi
if [ "$INSTALL_CODEX" = "1" ]; then
    echo "Codex CLI: reinicie e rode 'codex mcp list' para confirmar. Aprove as tools na primeira chamada ou ajuste a approval policy."
fi
