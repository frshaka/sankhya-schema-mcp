# Sankhya Schema MCP

Servidor MCP (Model Context Protocol) que conecta o Claude Code ao banco Oracle do Sankhya ERP, permitindo explorar tabelas, campos, índices, relacionamentos e executar queries SQL diretamente durante uma conversa.

O servidor opera em modo **thick** via Oracle Instant Client 21c, garantindo compatibilidade com bancos Oracle 11.2 em diante.

---

## Funcionalidades

| Tool | O que faz |
|------|-----------|
| `describe_table` | Retorna colunas, tipos de dados, nullable e comentários de uma tabela |
| `search_tables` | Busca tabelas por nome parcial (ex: `TGF`, `TSIUSU`) |
| `search_columns` | Descobre em quais tabelas existe determinado campo (ex: `CODPARC`) |
| `search_entities` | Busca EntityNames (instâncias Sankhya) por nome ou descrição |
| `get_foreign_keys` | Lista relacionamentos (FK) de entrada e saída de uma tabela |
| `get_indexes` | Mostra índices e suas colunas |
| `run_query` | Executa SELECT e retorna resultado formatado (somente leitura) |
| `validate_query` | Valida sintaxe SQL via EXPLAIN PLAN sem executar |
| `table_sample` | Retorna amostra de dados reais da tabela |
| `list_modules` | Visão geral dos módulos Sankhya por prefixo de tabela |

---

## Pré-requisitos

| Requisito | Versão mínima | Como verificar |
|-----------|---------------|----------------|
| Python | 3.10+ | `python --version` |
| Git | qualquer | `git --version` |
| Claude Code | qualquer | `claude --version` |
| Banco Oracle | 11.2+ | Acesso via host:porta/service |

**Windows adicional:** PowerShell 7+ (`pwsh`) — [Instalar aqui](https://aka.ms/powershell)

**Linux adicional:**
```bash
sudo apt-get install -y curl unzip libaio1
# Ubuntu 24+: substituir libaio1 por libaio1t64
```

---

## Instalação rápida

### Windows

```powershell
git clone https://github.com/frshaka/sankhya-schema-mcp.git
cd sankhya-schema-mcp
pwsh -File setup.ps1
```

### Linux

```bash
git clone https://github.com/frshaka/sankhya-schema-mcp.git
cd sankhya-schema-mcp
bash setup.sh
```

O script de setup executa automaticamente:
1. Download e extração do Oracle Instant Client 21c (do GitHub Releases)
2. Criação do ambiente virtual Python (`.venv/`)
3. Instalação das dependências (`mcp`, `oracledb`, `python-dotenv`)
4. Registro do servidor MCP no Claude Code (`~/.claude.json`)

Após o setup, configure as credenciais do banco no arquivo `.env` e reinicie o Claude Code.

Veja **[INSTALACAO.md](INSTALACAO.md)** para o guia completo passo a passo, configuração de credenciais e solução de problemas.

---

## Configuração do banco

Copie o arquivo de exemplo e edite com suas credenciais:

```bash
cp .env.example .env
```

Conteúdo do `.env`:
```ini
SANKHYA_DB_HOST=localhost
SANKHYA_DB_PORT=1521
SANKHYA_DB_SERVICE=XE
SANKHYA_DB_USER=SANKHYA
SANKHYA_DB_PASSWORD=developer
```

> O arquivo `.env` está no `.gitignore` e nunca será versionado.

---

## Verificação

Reinicie o Claude Code e execute:

```
/mcp
```

O servidor `sankhya-schema` deve aparecer com status **connected**.

---

## Exemplos de uso no chat

```
Descreva a tabela TGFCAB

Quais tabelas do Sankhya têm o campo CODPARC?

Mostre os índices de TGFDIN

Valide esta query:
SELECT CAB.NUNOTA, CAB.CODPARC, DIN.DTVENC
FROM TGFCAB CAB
JOIN TGFDIN DIN ON DIN.NUNOTA = CAB.NUNOTA
WHERE CAB.CODTIPOPER = 1

Liste os módulos disponíveis no schema

Busque a entidade "Parceiro"
```

---

## Segurança

- Apenas `SELECT` é permitido — comandos DML/DDL (INSERT, UPDATE, DELETE, DROP etc.) são bloqueados
- A conexão é local — nenhum dado sai da máquina
- Credenciais ficam no `.env` local, fora do controle de versão

---

## Estrutura do projeto

```
sankhya-schema-mcp/
├── src/
│   └── server.py          # Servidor MCP principal
├── instantclient/         # Oracle Instant Client (baixado pelo setup)
├── .venv/                 # Ambiente virtual Python (criado pelo setup)
├── .env                   # Credenciais do banco (não versionado)
├── .env.example           # Modelo de credenciais
├── start.ps1              # Script de inicialização (Windows)
├── start.sh               # Script de inicialização (Linux)
├── setup.ps1              # Instalador automático (Windows)
├── setup.sh               # Instalador automático (Linux)
├── requirements.txt       # Dependências Python
└── INSTALACAO.md          # Guia detalhado de instalação
```

---

## Licença

Uso interno para parceiros e desenvolvedores Sankhya.
