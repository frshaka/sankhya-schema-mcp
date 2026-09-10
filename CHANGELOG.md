# Changelog

Todas as mudanças relevantes deste projeto são registradas aqui.

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e o
versionamento segue [SemVer](https://semver.org/lang/pt-BR/).

A tool `check_updates` do próprio servidor compara a versão instalada com a
última publicada e mostra as entradas deste arquivo no intervalo.

## [1.2.0] - 2026-09-10

### Adicionado

- `describe_table` agora traz a **descrição em português** de cada campo,
  vinda do dicionário Sankhya (`TDDCAM`). O comentário de coluna do catálogo
  vem vazio na base Sankhya (0 de 69.782 colunas medidas), então até aqui a
  tool devolvia uma coluna sempre em branco.
- `describe_table` agora traz **todos os valores aceitos** dos campos
  enumerados, com o rótulo, vindos de `TDDOPC` — por exemplo `TIPMOV` com
  `P=Pedido de venda; V=Venda; C=Compra`. Sem isso, quem escrevia a query
  precisava adivinhar o literal do `WHERE`: `V` e `P` são ambos válidos, e usar
  um pelo outro devolve o documento errado sem levantar erro de SQL.
- `get_foreign_keys` ganhou a seção **Ligações do dicionário** (`TDDLIG`), o
  relacionamento que o JAPE enxerga. Não coincide com a FK física: há ligação
  sem FK e FK sem ligação.
- Nova tool `check_updates`: compara a versão instalada com a última publicada
  no repositório de origem e mostra o que mudou e como atualizar.
- Aviso de atualização no boot do servidor, injetado nas instruções do MCP.
  Consulta em cache de 24h com timeout de 2s; offline não impede o start.
- Versionamento do projeto: `src/version.py` como fonte única, este CHANGELOG e
  tags SemVer.
- `tools/release.sh` e `tools/release.ps1`: validam testes, sincronia entre
  `__version__` e CHANGELOG, working tree limpa e ausência da tag antes de
  publicar.
- Suporte a **SQL Server** além do Oracle, via `SANKHYA_DB_TYPE`. Todas as
  queries de catálogo, a conexão, a transação de leitura e o plano de execução
  passaram para `src/dialects.py`.
- `table_sample` ganhou o parâmetro `columns` para projetar colunas.
- Suporte a conexão Oracle por *service name* (`SANKHYA_DB_SERVICE_NAME`).
- Suporte a `SANKHYA_DB_SCHEMA` para quando o login do MCP não é dono das
  tabelas.
- Configuração por projeto via `.sankhya-mcp.env`, sobrescrevendo o `.env` geral.
- Menu de CLIs no instalador, com suporte ao Codex.

### Alterado

- Saída de `describe_table` reformatada: tipo, tamanho, precisão e escala
  colapsados numa coluna só (`NUMBER(15,2)`) e indicador de nulo normalizado
  entre Oracle e SQL Server. Abre espaço para descrição e domínio sem inchar a
  tabela.
- Instruções do MCP passaram a exigir `describe_table` antes de escrever
  qualquer filtro com valor literal.
- Inicialização do Oracle Instant Client passou a ser preguiçosa, para não
  travar o handshake MCP.

### Corrigido

- `table_sample` fazia `SELECT *` e devolvia tabelas de 600 colunas inteiras:
  TGFTOP com `limit=2` gerava 11.902 caracteres. Agora projeta e avisa o corte.
- Queries de metadados fixam um único *owner*, evitando colunas duplicadas
  quando a mesma tabela existe em mais de um schema visível.
- Sessão Oracle passa a apontar para `SANKHYA_DB_SCHEMA`, para que `run_query`
  funcione sem qualificar tabela à mão.
- EntityName não reconhecido devolve mensagem explicando o que houve, em vez de
  "nenhum índice encontrado", que se lia como "esta tabela não tem índice".
- Valores *falsy* (`0`, `False`, `Decimal("0.00")`) deixaram de virar célula
  vazia no Markdown, e `|` em comentário passou a ser escapado.
- `run_query` fechou brechas de escrita disfarçada de leitura: comentários,
  múltiplos comandos, `WITH FUNCTION/PROCEDURE` e `SELECT ... INTO`.
- `start.sh` deixou de usar `source` para ler o `.env`: um arquivo de
  repositório qualquer não deve executar comandos no host.
- `describe_table` degrada em vez de quebrar quando o dicionário Sankhya não
  existe no schema conectado.

## [1.1.0] - 2026-05-11

### Adicionado

- Instalação automatizada no Linux (`setup.sh`, `start.sh`) com download do
  Oracle Instant Client via GitHub Releases.
- `tools/repackage-instantclient-linux.sh` para reempacotar o Instant Client.

### Corrigido

- Detecção de `libaio1t64` no Ubuntu 24+ e criação do symlink `libaio.so.1`.
- Criação do `~/.claude.json` quando ausente.
- Versão do `oracledb` limitada abaixo da 3.0.0.

## [1.0.0] - 2026-05-02

### Adicionado

- Primeira versão do servidor MCP de exploração do schema Sankhya em Oracle,
  com as tools `describe_table`, `search_tables`, `search_columns`,
  `get_foreign_keys`, `get_indexes`, `run_query`, `validate_query`,
  `table_sample`, `search_entities` e `list_modules`.

[1.2.0]: https://github.com/frshaka/sankhya-schema-mcp/releases/tag/v1.2.0
[1.1.0]: https://github.com/frshaka/sankhya-schema-mcp/releases/tag/v1.1
[1.0.0]: https://github.com/frshaka/sankhya-schema-mcp/releases/tag/v1.0
