# Sankhya Schema MCP

Servidor MCP (Model Context Protocol) que conecta o Claude Code e/ou o Codex CLI ao banco Oracle do Sankhya ERP, permitindo explorar tabelas, campos, índices, relacionamentos e executar queries SQL diretamente durante uma conversa.

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
| Claude Code e/ou Codex CLI | qualquer | `claude --version` / `codex --version` |
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
1. Menu de seleção dos CLIs onde registrar o MCP (Claude Code, Codex CLI ou ambos — default: Claude Code)
2. Download e extração do Oracle Instant Client 21c (do GitHub Releases)
3. Criação do ambiente virtual Python (`.venv/`)
4. Instalação das dependências (`mcp`, `oracledb`, `python-dotenv`)
5. Registro do servidor MCP nos CLIs escolhidos (Claude Code: `~/.claude.json` / Codex: `~/.codex/config.toml`)

Para pular o menu (automação), use a flag de CLI:

```powershell
# Windows
pwsh -File setup.ps1 -Cli both     # claude | codex | both
```

```bash
# Linux
bash setup.sh --cli both           # claude | codex | both
```

Após o setup, configure as credenciais do banco no arquivo `.env` e reinicie o CLI escolhido.

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
# Conexão por SID (padrão). Para conectar por service name, use SANKHYA_DB_SERVICE_NAME (tem precedência).
SANKHYA_DB_SERVICE=XE
# SANKHYA_DB_SERVICE_NAME=ORCLPDB1
SANKHYA_DB_USER=SANKHYA
SANKHYA_DB_PASSWORD=developer
```

> O arquivo `.env` está no `.gitignore` e nunca será versionado.

### Configuração por projeto (override)

O `.env` acima é a configuração **geral** (usada por padrão em qualquer projeto). Para apontar o MCP a um banco diferente em um projeto específico, crie um arquivo **`.sankhya-mcp.env`** na raiz desse projeto (o diretório onde você abre o Claude Code).

Na inicialização, o MCP carrega primeiro o `.env` geral e, em seguida, o `.sankhya-mcp.env` do projeto — as variáveis do projeto **sobrescrevem** as do geral. Inclua apenas o que difere; o restante é herdado.

Exemplo de `.sankhya-mcp.env` em um projeto que conecta por service name:
```ini
SANKHYA_DB_HOST=10.100.56.7
SANKHYA_DB_SERVICE_NAME=MEUBANCO.EXEMPLO.COM.BR
SANKHYA_DB_USER=USUARIO_PROJETO
SANKHYA_DB_PASSWORD=senha_do_projeto
```

> **Atenção:** o `.sankhya-mcp.env` contém credenciais. Adicione-o ao `.gitignore` do projeto.

---

## Verificação

**Claude Code** — reinicie e execute:

```
/mcp
```

O servidor `sankhya-schema` deve aparecer com status **connected**.

**Codex CLI** — reinicie e execute no terminal:

```bash
codex mcp list
```

O servidor `sankhya-schema` deve aparecer na lista. Na primeira chamada de tool, aprove quando solicitado (ou ajuste a `approval_policy` no `~/.codex/config.toml`).

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
- A validação é textual e não cobre tudo: uma função que já existe no schema com `PRAGMA AUTONOMOUS_TRANSACTION`, chamada em `SELECT pacote.funcao(x) FROM DUAL`, grava mesmo assim. Conecte sempre com um usuário Oracle sem privilégio de escrita — é a única defesa efetiva contra esse caso
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

## Ambiente de Desenvolvimento Local

### Banco de Dados com Docker

#### Criando o volume de dados

Antes de iniciar o container, crie um volume para garantir a persistência dos dados:

```bash
docker volume create skdev-oracle-volume
```

#### Iniciando o container

```bash
docker run -d --name skdev-oracle --shm-size=1g -p 1521:1521 -p 5500:5500 -v skdev-oracle-volume:/opt/oracle/oradata sankhyaimages/skdev-oracle:1.1.0
```

> ⚠️ A primeira inicialização pode levar de 20 a 30 minutos. Acompanhe o progresso com: `docker logs -f skdev-oracle`.

#### Credenciais de conexão

Use estas credenciais para conectar ao banco a partir do WPM ou de um cliente de banco de dados:

| Endereço | Porta | SID | Usuário | Senha |
|---|---|---|---|---|
| `localhost` | `1521` | `XE` | `SANKHYA` | `developer` |

#### Parar e reiniciar o container

```bash
docker stop skdev-oracle    # parar
docker start skdev-oracle   # reiniciar
```

---

### Servidor de Aplicação (WildFly)

Faça o download do [WildFly 23.0](https://downloads.sankhya.com.br/downloads?app=WildFly&c=1) e extraia em um local de fácil acesso (ex: `C:\wildfly` ou `/home/user/wildfly`).

Inicie o servidor a partir da pasta `bin` do WildFly:

- Windows:
```bash
.\standalone.bat
```

- Linux:
```bash
./standalone.sh
```

Para manuais detalhados de instalação:
- [Manual de Instalação em Linux](https://ajuda.sankhya.com.br/hc/pt-br/articles/360045547894-Manual-de-Instala%C3%A7%C3%A3o-Sankhya-Om-em-Ambiente-Linux#Configura%C3%A7%C3%A3odoWildfly)
- [Manual de Instalação em Windows](https://ajuda.sankhya.com.br/hc/pt-br/articles/360045695134-Manual-de-Instala%C3%A7%C3%A3o-Sankhya-Om-em-Ambiente-Windows)

---

### Configuração do WPM e Sankhya OM

1. Acesse o WPM no navegador: `http://localhost:8080/wpm/`
2. A senha padrão no primeiro acesso é `admin` — você será solicitado a alterá-la.
3. Na tela de configuração, insira os dados de conexão do banco configurado no Docker.
4. Após a conexão, o WPM permitirá que você baixe e instale a versão desejada do Sankhya OM. Escolha sempre a versão mais recente disponível.
5. Siga o processo de instalação. Ao final, seu ambiente estará pronto.

---

## Licença

Uso interno para parceiros e desenvolvedores Sankhya.
