# Manual de Instalação — Sankhya Schema MCP

Este MCP conecta o Claude Code ao banco Oracle do Sankhya local,
permitindo explorar tabelas, campos, índices e executar queries diretamente
durante uma conversa com o Claude.

---

## Pré-requisitos

- **Python 3.10 ou superior** — [python.org/downloads](https://www.python.org/downloads/)
  Marque "Add Python to PATH" durante a instalação.
- **PowerShell 7+** (pwsh) — [aka.ms/powershell](https://aka.ms/powershell)
- **Claude Code** instalado e funcionando
- Acesso ao banco Oracle do Sankhya (local ou container Docker)

---

## Passo 1 — Clonar o projeto

```powershell
git clone https://github.com/frshaka/sankhya-schema-mcp.git
cd sankhya-schema-mcp
```

---

## Passo 2 — Rodar o setup automático

O script `setup.ps1` baixa o Oracle Instant Client (~135 MB), cria o ambiente
virtual Python e instala todas as dependências de uma vez:

```powershell
pwsh -File setup.ps1
```

O que o script faz:
1. Baixa e extrai `instantclient/` do GitHub Releases (pulado se já existir)
2. Cria o ambiente virtual `.venv/` (pulado se já existir)
3. Instala as dependências: `mcp`, `oracledb`, `python-dotenv`

> **Pré-requisitos:** Python 3.10+ e PowerShell 7+ instalados e no PATH.

---

## Passo 3 — Ajustar as credenciais do banco

Abra o arquivo `start.ps1` e edite as variáveis conforme o ambiente:

```powershell
$env:SANKHYA_DB_HOST     = "localhost"   # IP ou hostname do servidor Oracle
$env:SANKHYA_DB_PORT     = "1521"        # porta (padrão Oracle)
$env:SANKHYA_DB_SERVICE  = "XE"          # SID ou Service Name do banco
$env:SANKHYA_DB_USER     = "SANKHYA"     # usuário Oracle
$env:SANKHYA_DB_PASSWORD = "developer"   # senha
```

> As duas últimas linhas do `start.ps1` **não precisam ser alteradas** —
> elas já usam o caminho relativo correto.

---

## Passo 4 — Registrar o MCP no Claude Code

Descubra o caminho completo da pasta onde você colocou o projeto:

```powershell
# Cole este comando no PowerShell para obter o caminho exato
Resolve-Path ".\start.ps1"
```

Anote o resultado (ex.: `C:\projetos\sankhya-mcp\start.ps1`).

### Opção A — Claude Code CLI (recomendado)

Execute no terminal:

```bash
claude mcp add sankhya-schema -- pwsh -File "C:\SEU_CAMINHO\sankhya-mcp\start.ps1"
```

Substitua `C:\SEU_CAMINHO\sankhya-mcp\start.ps1` pelo caminho anotado acima.

### Opção B — Editar o arquivo de configuração manualmente

Abra o arquivo de configuração do Claude Code:

```
C:\Users\<seu-usuario>\.claude\settings.json
```

Localize a seção `"mcpServers"` (crie se não existir) e adicione:

```json
{
  "mcpServers": {
    "sankhya-schema": {
      "command": "pwsh",
      "args": ["-File", "C:\\SEU_CAMINHO\\sankhya-mcp\\start.ps1"]
    }
  }
}
```

> Use barras duplas `\\` no JSON. Substitua `SEU_CAMINHO` pelo caminho real.

---

## Passo 5 — Verificar a instalação

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

### "python não é reconhecido"
O Python não está no PATH. Reinstale marcando a opção "Add Python to PATH"
ou informe o caminho completo do executável em `start.ps1`.

### "pwsh não é reconhecido"
Instale o PowerShell 7+: [aka.ms/powershell](https://aka.ms/powershell)

### MCP aparece mas dá erro de conexão
- Verifique se o banco Oracle está rodando e acessível
- Confirme host, porta, SID e credenciais no `start.ps1`
- Teste a conexão direto pelo Python:
  ```powershell
  .\.venv\Scripts\python.exe -c "import oracledb; print('oracledb OK')"
  ```

### "DPI-1047: Cannot locate a 64-bit Oracle Client library"
A pasta `instantclient\` está ausente ou incompleta. Rode novamente o setup:
```powershell
Remove-Item instantclient -Recurse -Force   # remove pasta corrompida
pwsh -File setup.ps1
```

---

## Estrutura das credenciais por ambiente

| Variável               | Desenvolvimento | Produção (exemplo) |
|------------------------|-----------------|-------------------|
| `SANKHYA_DB_HOST`      | `localhost`     | `192.168.1.10`    |
| `SANKHYA_DB_PORT`      | `1521`          | `1521`            |
| `SANKHYA_DB_SERVICE`   | `XE`            | `SANKHYA`         |
| `SANKHYA_DB_USER`      | `SANKHYA`       | `SANKHYA`         |
| `SANKHYA_DB_PASSWORD`  | `developer`     | *(consultar DBA)* |
