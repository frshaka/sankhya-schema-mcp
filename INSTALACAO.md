# Manual de Instalação — Sankhya Schema MCP

Este MCP conecta o Claude Code ao banco Oracle do Sankhya local,
permitindo explorar tabelas, campos, índices e executar queries diretamente
durante uma conversa com o Claude.

---

## Pré-requisitos

- **Python 3.10 ou superior**
- **Claude Code** instalado e funcionando
- Acesso ao banco Oracle do Sankhya (local ou container Docker)

**Windows:** PowerShell 7+ (pwsh) — [aka.ms/powershell](https://aka.ms/powershell)

**Linux:** `bash`, `curl`, `unzip`, `python3-venv`, `libaio1`
```bash
sudo apt-get install -y curl unzip python3-venv libaio1
```

---

## Instalação no Windows

### Passo 1 — Clonar o projeto

```powershell
git clone https://github.com/frshaka/sankhya-schema-mcp.git
cd sankhya-schema-mcp
```

### Passo 2 — Rodar o setup automático

```powershell
pwsh -File setup.ps1
```

O que o script faz:
1. Baixa e extrai `instantclient/` do GitHub Releases — pulado se já existir
2. Cria o ambiente virtual `.venv/` — pulado se já existir
3. Instala as dependências: `mcp`, `oracledb`, `python-dotenv`
4. Registra o MCP no Claude Code (`~/.claude/.claude.json`)

### Passo 3 — Ajustar as credenciais do banco

Abra o arquivo `start.ps1` e edite as variáveis conforme o ambiente:

```powershell
$env:SANKHYA_DB_HOST     = "localhost"
$env:SANKHYA_DB_PORT     = "1521"
$env:SANKHYA_DB_SERVICE  = "XE"
$env:SANKHYA_DB_USER     = "SANKHYA"
$env:SANKHYA_DB_PASSWORD = "developer"
```

### Passo 4 — Registro manual do MCP (se necessário)

Edite `C:\Users\<seu-usuario>\.claude\.claude.json` e adicione:

```json
"mcpServers": {
  "sankhya-schema": {
    "type": "stdio",
    "command": "pwsh",
    "args": ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "C:\\SEU_CAMINHO\\sankhya-mcp\\start.ps1"],
    "env": {}
  }
}
```

---

## Instalação no Linux

### Passo 1 — Clonar o projeto

```bash
git clone https://github.com/frshaka/sankhya-schema-mcp.git
cd sankhya-schema-mcp
```

### Passo 2 — Rodar o setup automático

```bash
bash setup.sh
```

O que o script faz:
1. Baixa e extrai `instantclient/` (Linux) do GitHub Releases — pulado se já existir
2. Verifica se `libaio1` está instalado — avisa se não estiver
3. Cria o ambiente virtual `.venv/` — pulado se já existir
4. Instala as dependências: `mcp`, `oracledb`, `python-dotenv`
5. Registra o MCP no Claude Code (`~/.claude/.claude.json`)

> Se o download do instantclient falhar, baixe manualmente em:
> https://www.oracle.com/database/technologies/instant-client/linux-x86-64-downloads.html
> Extraia para a pasta `instantclient/` dentro do projeto.

### Passo 3 — Ajustar as credenciais do banco

Abra o arquivo `start.sh` e edite as variáveis:

```bash
export SANKHYA_DB_HOST="localhost"
export SANKHYA_DB_PORT="1521"
export SANKHYA_DB_SERVICE="XE"
export SANKHYA_DB_USER="SANKHYA"
export SANKHYA_DB_PASSWORD="developer"
```

### Passo 4 — Registro manual do MCP (se necessário)

Edite `~/.claude/.claude.json` e adicione:

```json
"mcpServers": {
  "sankhya-schema": {
    "type": "stdio",
    "command": "bash",
    "args": ["/SEU_CAMINHO/sankhya-mcp/start.sh"],
    "env": {}
  }
}
```

---

## Verificar a instalação (Windows e Linux)

Reinicie o Claude Code e execute no chat:

```
/mcp
```

Deve aparecer `sankhya-schema` com status **connected** e as tools listadas:

- `describe_table`
- `search_tables`
- `search_columns`
- `get_foreign_keys`
- `get_indexes`
- `run_query`
- `validate_query`
- `table_sample`
- `list_modules`
- `search_entities`

**Teste rápido:**

```
Liste os módulos do schema Sankhya
```

ou

```
Descreva a tabela TGFCAB
```

---

## Solução de problemas

### Windows — "python não é reconhecido"
O Python não está no PATH. Reinstale marcando "Add Python to PATH".

### Windows — "pwsh não é reconhecido"
Instale o PowerShell 7+: [aka.ms/powershell](https://aka.ms/powershell)

### Windows — MCP com erro de conexão
- Verifique se o banco Oracle está rodando e acessível
- Confirme credenciais no `start.ps1`
- Teste: `.\.venv\Scripts\python.exe -c "import oracledb; print('OK')"`

### Windows — "DPI-1047: Cannot locate a 64-bit Oracle Client library"
```powershell
Remove-Item instantclient -Recurse -Force
pwsh -File setup.ps1
```

### Linux — "DPI-1047: Cannot locate a 64-bit Oracle Client library"
```bash
rm -rf instantclient/
bash setup.sh
```
Se persistir, verifique se `libaio1` está instalado:
```bash
sudo apt-get install -y libaio1
```

### Linux — MCP com erro de conexão
- Confirme credenciais no `start.sh`
- Teste: `.venv/bin/python -c "import oracledb; print('OK')"`
- Verifique se `LD_LIBRARY_PATH` aponta para `instantclient/`

---

## Estrutura das credenciais por ambiente

| Variável               | Desenvolvimento | Produção (exemplo) |
|------------------------|-----------------|-------------------|
| `SANKHYA_DB_HOST`      | `localhost`     | `192.168.1.10`    |
| `SANKHYA_DB_PORT`      | `1521`          | `1521`            |
| `SANKHYA_DB_SERVICE`   | `XE`            | `SANKHYA`         |
| `SANKHYA_DB_USER`      | `SANKHYA`       | `SANKHYA`         |
| `SANKHYA_DB_PASSWORD`  | `developer`     | *(consultar DBA)* |
