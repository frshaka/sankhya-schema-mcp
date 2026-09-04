# Sankhya Schema MCP

Servidor MCP (Model Context Protocol) que conecta o Claude Code e/ou o Codex CLI ao banco do Sankhya ERP, permitindo explorar tabelas, campos, índices, relacionamentos e executar queries SQL diretamente durante uma conversa.

Suporta os **dois bancos** distribuídos pela Sankhya no ambiente de desenvolvimento:

| Banco | Driver | Imagem Docker | Porta | Endereçamento |
|-------|--------|---------------|-------|---------------|
| Oracle (padrão) | `oracledb` em modo **thick** (Instant Client 21c, compatível com Oracle 11.2+) | `sankhyaimages/skdev-oracle:1.1.0` | 1521 | SID `XE` |
| SQL Server | `pymssql` (wheel com FreeTDS embutido — não exige driver de sistema operacional) | `sankhyaimages/skdev-mssql:1.1.0` | 1433 | database `jiva` |

A escolha é feita por `SANKHYA_DB_TYPE` no `.env` — veja [Configuração do banco](#configuração-do-banco).

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
| `validate_query` | Valida sintaxe SQL sem executar (EXPLAIN PLAN no Oracle, SHOWPLAN_ALL no SQL Server) |
| `table_sample` | Retorna amostra de dados reais da tabela |
| `list_modules` | Visão geral dos módulos Sankhya por prefixo de tabela |

---

## Pré-requisitos

| Requisito | Versão mínima | Como verificar |
|-----------|---------------|----------------|
| Python | 3.10+ | `python --version` |
| Git | qualquer | `git --version` |
| Claude Code e/ou Codex CLI | qualquer | `claude --version` / `codex --version` |
| Banco | Oracle 11.2+ ou SQL Server 2017+ | Acesso via host:porta |

**Windows adicional:** PowerShell 7+ (`pwsh`) — [Instalar aqui](https://aka.ms/powershell)

**Linux adicional (somente para Oracle):**
```bash
sudo apt-get install -y curl unzip libaio1
# Ubuntu 24+: substituir libaio1 por libaio1t64
```

> Para SQL Server não há dependência de sistema operacional: o `pymssql` traz o FreeTDS na própria wheel.

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
2. Download e extração do Oracle Instant Client 21c (do GitHub Releases — necessário só para Oracle)
3. Criação do ambiente virtual Python (`.venv/`)
4. Instalação das dependências (`mcp`, `oracledb`, `pymssql`, `python-dotenv`)
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

### Escolhendo o banco

Duas chaves definem o destino:

| Chave | Valores | Default | Para que serve |
|-------|---------|---------|----------------|
| `SANKHYA_DB_TYPE` | `oracle` \| `sqlserver` | `oracle` | Escolhe o dialeto, o driver e as queries de catálogo |
| `SANKHYA_DB_DATABASE` | nome do database | `jiva` | Só no SQL Server, que endereça database em vez de SID/service name |

O default é `oracle` de propósito: uma instalação existente continua funcionando sem tocar no `.env`.
Valor desconhecido em `SANKHYA_DB_TYPE` faz o servidor falhar na subida, em vez de conectar no banco errado.

**Oracle** (`.env`):
```ini
SANKHYA_DB_TYPE=oracle
SANKHYA_DB_HOST=localhost
SANKHYA_DB_PORT=1521
# Conexão por SID (padrão). Para conectar por service name, use SANKHYA_DB_SERVICE_NAME (tem precedência).
SANKHYA_DB_SERVICE=XE
# SANKHYA_DB_SERVICE_NAME=ORCLPDB1
SANKHYA_DB_USER=SANKHYA
SANKHYA_DB_PASSWORD=developer
```

**SQL Server** (`.env`):
```ini
SANKHYA_DB_TYPE=sqlserver
SANKHYA_DB_HOST=localhost
SANKHYA_DB_PORT=1433
SANKHYA_DB_DATABASE=jiva
SANKHYA_DB_USER=SANKHYA
SANKHYA_DB_PASSWORD=developer
```

> O arquivo `.env` está no `.gitignore` e nunca será versionado.

### Configuração por projeto (override)

O `.env` acima é a configuração **geral** (usada por padrão em qualquer projeto). Para apontar o MCP a um banco diferente em um projeto específico, crie um arquivo **`.sankhya-mcp.env`** na raiz desse projeto (o diretório onde você abre o Claude Code).

Na inicialização, o MCP carrega primeiro o `.env` geral e, em seguida, o `.sankhya-mcp.env` do projeto — as variáveis do projeto **sobrescrevem** as do geral. Inclua apenas o que difere; o restante é herdado.

Isso vale também para o **tipo de banco**: dá para manter o `.env` geral no Oracle e apontar um projeto específico para o SQL Server — ou o contrário — sem mexer na configuração dos outros.

Exemplo de `.sankhya-mcp.env` em um projeto que conecta por service name:
```ini
SANKHYA_DB_HOST=10.100.56.7
SANKHYA_DB_SERVICE_NAME=MEUBANCO.EXEMPLO.COM.BR
SANKHYA_DB_USER=USUARIO_PROJETO
SANKHYA_DB_PASSWORD=senha_do_projeto
```

Exemplo de um projeto que roda contra o SQL Server, herdando o resto do `.env` geral:
```ini
SANKHYA_DB_TYPE=sqlserver
SANKHYA_DB_PORT=1433
SANKHYA_DB_DATABASE=jiva
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

- Apenas `SELECT` é permitido — comandos DML/DDL (INSERT, UPDATE, DELETE, DROP etc.) são bloqueados por uma allowlist textual na aplicação
- A validação é textual e não cobre tudo: uma função que já existe no schema com `PRAGMA AUTONOMOUS_TRANSACTION`, chamada em `SELECT pacote.funcao(x) FROM DUAL`, grava mesmo assim
- A conexão é local — nenhum dado sai da máquina
- Credenciais ficam no `.env` local, fora do controle de versão
- Como o usuário recomendado é somente-leitura e normalmente **não** é o dono das tabelas, defina `SANKHYA_DB_SCHEMA` com o schema onde elas moram (ver abaixo) — sem isso, parte das tools responde `ORA-00942`

---

## Schema das tabelas (`SANKHYA_DB_SCHEMA`)

Nomes de tabela sem qualificação são resolvidos pelo Oracle no schema do usuário conectado. Quando o login do MCP não é o dono das tabelas — o caso normal ao seguir a recomendação de usar um usuário somente-leitura — três tools param de funcionar:

| Tool | Sintoma |
|---|---|
| `table_sample` | `ORA-00942: table or view does not exist` |
| `search_entities` | falha ao ler `TDDINS` |
| `describe_table`, `get_indexes`, `get_foreign_keys` | funcionam, mas **perdem** a tradução de EntityName (`describe_table("CabecalhoNota")`) sem exibir erro |

As demais tools leem as views de catálogo (`ALL_TAB_COLUMNS`, `ALL_TABLES`, …) e não são afetadas.

A correção é apontar a sessão para o schema certo:

```ini
# .env (pasta do MCP) — padrão de todos os projetos
SANKHYA_DB_SCHEMA=SANKHYA
```

O MCP emite um `ALTER SESSION SET CURRENT_SCHEMA` por conexão. A variável ausente mantém o comportamento anterior, sem alterar a sessão.

Para um projeto que precisa de outro schema, sobrescreva apenas ali com o `.sankhya-mcp.env` (ver `INSTALACAO.md`):

```ini
# .sankhya-mcp.env na raiz do projeto
SANKHYA_DB_SCHEMA=TESTE
```

Para uma consulta pontual em outro schema, qualifique no `run_query`: `SELECT ... FROM TREINA.TGFCAB`.

### A segunda camada de proteção é mais fraca no SQL Server

Além da validação da aplicação, cada consulta roda dentro de uma transação de leitura. **O que essa transação garante não é igual nos dois bancos** — e a diferença é real, não uma formalidade:

| Banco | Comando | O que o banco faz com uma escrita que escape da validação |
|-------|---------|-----------------------------------------------------------|
| Oracle | `SET TRANSACTION READ ONLY` | **Recusa a escrita.** O servidor devolve `ORA-01456` e nada é executado |
| SQL Server | `BEGIN TRANSACTION` + `ROLLBACK` sempre | **Executa a escrita** e depois a desfaz no rollback |

Não existe no SQL Server um equivalente ao `SET TRANSACTION READ ONLY` do Oracle. `BEGIN TRANSACTION` com rollback garantido é o mais próximo disponível, mas é uma proteção de natureza diferente: ela **desfaz**, não **impede**. Verificado nesta base de desenvolvimento — dentro dessa transação o SQL Server aceitou `SELECT ... INTO`, `UPDATE` e `INSERT` sem reclamar; só o rollback da aplicação desfez.

Na prática isso significa que, no SQL Server:

- uma escrita chega a rodar no servidor antes de ser desfeita — com todos os efeitos colaterais que isso implica (triggers disparam, sequências e `IDENTITY` avançam, locks são tomados);
- se o processo do MCP morrer entre a escrita e o rollback, o SQL Server desfaz a transação ao derrubar a conexão — mas isso depende do servidor perceber a queda, não de a escrita ter sido barrada;
- a defesa que de fato impede a escrita é o **privilégio do login**.

> **Recomendação para SQL Server:** conecte o MCP com um login mapeado apenas em `db_datareader` no database do Sankhya. É a única camada que **impede** a escrita em vez de desfazê-la, e é o que torna a proteção comparável à do Oracle. No Oracle a mesma recomendação vale (um usuário sem privilégio de escrita cobre o caso da função com `AUTONOMOUS_TRANSACTION`), mas lá o `READ ONLY` já cobre o caso comum sozinho.

---

## Equivalências de catálogo entre os bancos

As tools respondem a mesma coisa nos dois bancos, lendo catálogos diferentes:

| Informação | Oracle | SQL Server |
|-----------|--------|------------|
| Colunas, tipos e nulabilidade | `ALL_TAB_COLUMNS` (`DATA_TYPE`, `DATA_LENGTH`, `DATA_PRECISION`, `DATA_SCALE`, `NULLABLE`) | `INFORMATION_SCHEMA.COLUMNS` (`DATA_TYPE`, `CHARACTER_MAXIMUM_LENGTH`, `NUMERIC_PRECISION`, `NUMERIC_SCALE`, `IS_NULLABLE`) |
| Lista de tabelas | `ALL_TABLES` | `INFORMATION_SCHEMA.TABLES` (`TABLE_TYPE = 'BASE TABLE'`) |
| Contagem de linhas | `ALL_TABLES.NUM_ROWS` | soma de `sys.partitions.rows` (`index_id IN (0,1)`) |
| Comentário de tabela/coluna | `ALL_TAB_COMMENTS` / `ALL_COL_COMMENTS` | `sys.extended_properties` com `name = 'MS_Description'` |
| Índices | `ALL_INDEXES` + `ALL_IND_COLUMNS` | `sys.indexes` + `sys.index_columns` + `sys.columns` |
| Foreign keys | `ALL_CONSTRAINTS` + `ALL_CONS_COLUMNS` | `sys.foreign_keys` + `sys.foreign_key_columns` |
| Schema do objeto | `OWNER` | `TABLE_SCHEMA` |
| Schemas de sistema, excluídos | `SYS`, `SYSTEM`, `DBSNMP`, `OUTLN` | `sys`, `INFORMATION_SCHEMA`, `guest` |
| Limite de linhas da amostra | `WHERE ROWNUM <= :1` | `SELECT TOP (%s) *` |
| Prefixo de módulo (`list_modules`) | `REGEXP_SUBSTR` não existe no SQL Server | os 3 primeiros caracteres do nome, agrupados em Python — mesmo caminho para os dois bancos |
| Plano de execução (`validate_query`) | `EXPLAIN PLAN` + `PLAN_TABLE` | `SET SHOWPLAN_ALL ON` (devolve o plano estimado sem executar a query) |
| Transação de leitura | `SET TRANSACTION READ ONLY` | `BEGIN TRANSACTION` + rollback — **não é equivalente**, ver [Segurança](#a-segunda-camada-de-proteção-é-mais-fraca-no-sql-server) |

Notas:

- O **dicionário Sankhya (`TDDINS`)** é tabela da aplicação, não do catálogo: as queries que o usam (`describe_table`, `search_entities`, resolução de EntityName) são idênticas nos dois bancos — só o placeholder de bind muda (`:1` no Oracle, `%s` no `pymssql`).
- **Comentários de coluna vêm vazios no SQL Server** nas bases de desenvolvimento distribuídas pela Sankhya (nenhuma `MS_Description` cadastrada). A coluna aparece em branco, sem erro.
- `NULLABLE` sai como `Y`/`N` no Oracle e `YES`/`NO` no SQL Server, e `DATA_LENGTH` vem nulo para tipos numéricos do SQL Server — o catálogo de origem é diferente, os valores refletem isso.
- `list_modules` agrupa pelo **prefixo de 3 caracteres** (`TGFCAB`, `TGFITE` e `TGFPAR` contam para `TGF`), que é a convenção de nomenclatura do Sankhya; tabelas customizadas caem em `AD_`. Prefixo com uma tabela só fica de fora.
- O **schema** é tratado como dado nos dois bancos, nunca fixado na query: na base `jiva` distribuída pela Sankhya as tabelas ficam em `SANKHYA` (não em `dbo`). Quando a mesma tabela aparece em mais de um schema, o `describe_table` escolhe o do usuário conectado e avisa onde mais ela existe.

---

## Estrutura do projeto

```
sankhya-schema-mcp/
├── src/
│   ├── server.py          # Servidor MCP: tools, formatação e validação
│   └── dialects.py        # Queries, conexão e transação por banco (Oracle/SQL Server)
├── instantclient/         # Oracle Instant Client (baixado pelo setup)
├── .venv/                 # Ambiente virtual Python (criado pelo setup)
├── .env                   # Credenciais do banco (não versionado)
├── .env.example           # Modelo de credenciais
├── start.ps1              # Script de inicialização (Windows)
├── start.sh               # Script de inicialização (Linux)
├── setup.ps1              # Instalador automático (Windows)
├── setup.sh               # Instalador automático (Linux)
├── requirements.txt       # Dependências Python
├── test_server.py         # Autoteste das funções puras (não requer banco)
└── INSTALACAO.md          # Guia detalhado de instalação
```

---

## Ambiente de Desenvolvimento Local

### Banco de Dados com Docker

A Sankhya distribui as duas imagens em
[developer.sankhya.com.br](https://developer.sankhya.com.br/docs/01_ambiente.md).
Escolha uma e aponte o `SANKHYA_DB_TYPE` para ela.

#### Oracle — `skdev-oracle`

##### Criando o volume de dados

Antes de iniciar o container, crie um volume para garantir a persistência dos dados:

```bash
docker volume create skdev-oracle-volume
```

##### Iniciando o container

```bash
docker run -d --name skdev-oracle --shm-size=1g -p 1521:1521 -p 5500:5500 -v skdev-oracle-volume:/opt/oracle/oradata sankhyaimages/skdev-oracle:1.1.0
```

> ⚠️ A primeira inicialização pode levar de 20 a 30 minutos. Acompanhe o progresso com: `docker logs -f skdev-oracle`.

##### Credenciais de conexão

Use estas credenciais para conectar ao banco a partir do WPM ou de um cliente de banco de dados:

| Endereço | Porta | SID | Usuário | Senha |
|---|---|---|---|---|
| `localhost` | `1521` | `XE` | `SANKHYA` | `developer` |

##### Parar e reiniciar o container

```bash
docker stop skdev-oracle    # parar
docker start skdev-oracle   # reiniciar
```

#### SQL Server — `skdev-mssql`

```bash
docker volume create skdev-mssql-volume

docker run -d --name skdev-mssql -p 1433:1433 \
  -v skdev-mssql-volume:/var/opt/mssql sankhyaimages/skdev-mssql:1.1.0
```

> ⚠️ A primeira inicialização também leva de 20 a 30 minutos. Acompanhe com: `docker logs -f skdev-mssql`.
> O container está pronto quando o log mostra `SQL Server is now ready for client connections`.

##### Credenciais de conexão

| Endereço | Porta | Database | Usuário | Senha |
|---|---|---|---|---|
| `localhost` | `1433` | `jiva` | `SANKHYA` | `developer` |

Configuração correspondente no `.env`:
```ini
SANKHYA_DB_TYPE=sqlserver
SANKHYA_DB_PORT=1433
SANKHYA_DB_DATABASE=jiva
```

##### Parar e reiniciar o container

```bash
docker stop skdev-mssql    # parar
docker start skdev-mssql   # reiniciar
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
