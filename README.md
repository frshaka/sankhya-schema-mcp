# sankhya-schema MCP

Servidor MCP para exploração do schema Oracle do Sankhya ERP,
conectando ao banco Oracle local via Oracle Instant Client (modo thick).

## Tools disponíveis

| Tool | Descrição |
|---|---|
| `describe_table` | Colunas, tipos e comentários de uma tabela |
| `search_tables` | Busca tabelas por nome parcial |
| `search_columns` | Em quais tabelas existe determinado campo |
| `search_entities` | Busca EntityNames (instâncias) por nome ou descrição |
| `get_foreign_keys` | Relacionamentos (FK) de uma tabela |
| `get_indexes` | Índices de uma tabela |
| `run_query` | Executa SELECT e retorna resultado formatado |
| `validate_query` | Valida sintaxe via EXPLAIN PLAN sem executar |
| `table_sample` | Amostra de dados reais da tabela |
| `list_modules` | Visão geral dos módulos por prefixo de tabela |

## Instalação rápida

```powershell
git clone https://github.com/frshaka/sankhya-schema-mcp.git
cd sankhya-schema-mcp
pwsh -File setup.ps1
```

O script baixa o Oracle Instant Client, cria o ambiente virtual Python, instala as dependências e registra o MCP no Claude Code automaticamente.

Veja [INSTALACAO.md](INSTALACAO.md) para o guia completo com configuração de credenciais e solução de problemas.

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
```

## Segurança

- Apenas SELECT é permitido no `run_query` — INSERT, UPDATE, DELETE etc. são bloqueados
- Conexão permanece local — nenhum dado sai da máquina
