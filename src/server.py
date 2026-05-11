"""
Sankhya Schema MCP Server
Conecta ao banco Oracle local (container Docker) via oracledb em modo thick
com Oracle Instant Client 21c.
"""

import os
from pathlib import Path
from typing import Optional

import oracledb
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Oracle Instant Client — inicialização lazy para não bloquear o handshake MCP
# ---------------------------------------------------------------------------

_INSTANTCLIENT_DIR = str(Path(__file__).parent.parent / "instantclient")
_oracle_client_initialized = False


def _ensure_oracle_client():
    global _oracle_client_initialized
    if not _oracle_client_initialized:
        oracledb.init_oracle_client(lib_dir=_INSTANTCLIENT_DIR)
        _oracle_client_initialized = True


# ---------------------------------------------------------------------------
# Configuração de conexão
# ---------------------------------------------------------------------------

DB_CONFIG = {
    "host":     os.getenv("SANKHYA_DB_HOST",     "localhost"),
    "port":     int(os.getenv("SANKHYA_DB_PORT", "1521")),
    "sid":      os.getenv("SANKHYA_DB_SERVICE",  "XE"),
    "user":     os.getenv("SANKHYA_DB_USER",     "SANKHYA"),
    "password": os.getenv("SANKHYA_DB_PASSWORD", "oracle"),
}

_pool: Optional[oracledb.ConnectionPool] = None


def get_pool() -> oracledb.ConnectionPool:
    global _pool
    if _pool is None:
        _ensure_oracle_client()
        dsn = oracledb.makedsn(DB_CONFIG["host"], DB_CONFIG["port"], sid=DB_CONFIG["sid"])
        _pool = oracledb.create_pool(
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            dsn=dsn,
            min=1,
            max=5,
            increment=1,
        )
    return _pool


def execute_query(sql: str, params: list = None, limit: int = 200) -> list[dict]:
    """Executa uma query e retorna lista de dicionários."""
    with get_pool().acquire() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or [])
            columns = [col[0].lower() for col in cur.description]
            rows = cur.fetchmany(limit)
            return [dict(zip(columns, row)) for row in rows]


def rows_to_markdown(rows: list[dict]) -> str:
    """Converte lista de dicts para tabela Markdown."""
    if not rows:
        return "_Nenhum resultado encontrado._"
    headers = list(rows[0].keys())
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for row in rows:
        cells = [str(row.get(h, "") or "") for h in headers]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def resolve_table_name(name: str) -> tuple[str, list[dict]]:
    """
    Resolve EntityName (NOMEINSTANCIA) para nome de tabela Oracle via TDDINS.
    Retorna (table_name, entity_rows).
    Se não encontrar em TDDINS, devolve o nome original em maiúsculas e lista vazia.
    """
    sql = """
        SELECT NOMETAB, NOMEINSTANCIA, DESCRINSTANCIA, RAIZ, NUINSTANCIAPAI
        FROM TDDINS
        WHERE UPPER(NOMEINSTANCIA) = UPPER(:1)
          AND ATIVO = 'S'
        ORDER BY RAIZ DESC, NUINSTANCIA
    """
    rows = execute_query(sql, [name])
    if rows:
        return rows[0]["nometab"], rows
    return name.upper(), []


# ---------------------------------------------------------------------------
# Servidor MCP
# ---------------------------------------------------------------------------

mcp = FastMCP(
    name="sankhya-schema",
    instructions=(
        "Servidor de exploração do schema Oracle do Sankhya ERP. "
        "Use as tools para entender estrutura de tabelas, buscar campos, "
        "validar queries e explorar relacionamentos antes de escrever SQL.\n\n"
        "REGRAS OBRIGATÓRIAS:\n"
        "- NUNCA tente conexão direta ao banco Oracle. Use EXCLUSIVAMENTE as tools deste MCP.\n"
        "- NUNCA invente, chute ou assuma credenciais (usuário, senha, host, service name).\n"
        "- Se uma tool falhar ou o MCP não responder, informe o usuário e aguarde orientação.\n"
        "- Não tente contornar o MCP usando scripts Python, curl, ou qualquer outro meio."
    ),
)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def describe_table(table_name: str) -> str:
    """
    Retorna todas as colunas de uma tabela Sankhya: nome, tipo de dado,
    tamanho, precisão, se aceita nulo e comentário do campo.
    Aceita tanto o nome da tabela Oracle quanto o EntityName (NOMEINSTANCIA).

    Exemplos:
      describe_table("TGFCAB")
      describe_table("CabeçalhoNota")
    """
    resolved, entity_rows = resolve_table_name(table_name)

    sql = """
        SELECT
            c.COLUMN_NAME,
            c.DATA_TYPE,
            c.DATA_LENGTH,
            c.DATA_PRECISION,
            c.DATA_SCALE,
            c.NULLABLE,
            cm.COMMENTS
        FROM ALL_TAB_COLUMNS c
        LEFT JOIN ALL_COL_COMMENTS cm
            ON cm.TABLE_NAME = c.TABLE_NAME
            AND cm.COLUMN_NAME = c.COLUMN_NAME
            AND cm.OWNER = c.OWNER
        WHERE c.TABLE_NAME = :1
          AND c.OWNER NOT IN ('SYS','SYSTEM','DBSNMP','OUTLN')
        ORDER BY c.COLUMN_ID
    """
    rows = execute_query(sql, [resolved])
    if not rows:
        return f"Tabela `{resolved}` não encontrada ou sem colunas."

    header = f"## {resolved}"
    if entity_rows:
        e = entity_rows[0]
        header += f"\n**EntityName:** `{e['nomeinstancia']}` — {e['descrinstancia']}"

    result = f"{header}\n\n{rows_to_markdown(rows)}"

    inst_sql = """
        SELECT
            NOMEINSTANCIA  AS entity_name,
            DESCRINSTANCIA AS descricao,
            RAIZ           AS raiz,
            NUINSTANCIAPAI AS instancia_pai
        FROM TDDINS
        WHERE NOMETAB = :1
          AND ATIVO = 'S'
        ORDER BY RAIZ DESC, NOMEINSTANCIA
    """
    inst_rows = execute_query(inst_sql, [resolved])
    if inst_rows:
        result += f"\n\n## Instâncias (EntityNames) — {resolved}\n\n{rows_to_markdown(inst_rows)}"

    return result


@mcp.tool()
def search_tables(keyword: str) -> str:
    """
    Busca tabelas cujo nome contenha o termo informado.
    Útil para descobrir tabelas relacionadas a um módulo.

    Exemplos:
      search_tables("TGF")   → todas as tabelas de movimento
      search_tables("PARC")  → tabelas relacionadas a parceiros
      search_tables("FIN")   → tabelas financeiras
    """
    sql = """
        SELECT
            t.TABLE_NAME,
            t.NUM_ROWS,
            cm.COMMENTS
        FROM ALL_TABLES t
        LEFT JOIN ALL_TAB_COMMENTS cm
            ON cm.TABLE_NAME = t.TABLE_NAME
            AND cm.OWNER = t.OWNER
        WHERE t.TABLE_NAME LIKE :1
          AND t.OWNER NOT IN ('SYS','SYSTEM','DBSNMP','OUTLN')
        ORDER BY t.TABLE_NAME
    """
    rows = execute_query(sql, [f"%{keyword.upper()}%"])
    return rows_to_markdown(rows)


@mcp.tool()
def search_columns(column_keyword: str, table_keyword: str = "") -> str:
    """
    Busca em quais tabelas existe um campo com o nome informado.
    Permite filtrar por prefixo de tabela.

    Exemplos:
      search_columns("CODPARC")           → onde CODPARC aparece
      search_columns("CODPARC", "TGF")    → apenas em tabelas TGF*
      search_columns("DTFATUR")           → onde está o campo de faturamento
    """
    table_filter = f"AND c.TABLE_NAME LIKE :2" if table_keyword else ""
    sql = f"""
        SELECT
            c.TABLE_NAME,
            c.COLUMN_NAME,
            c.DATA_TYPE,
            c.NULLABLE,
            cm.COMMENTS
        FROM ALL_TAB_COLUMNS c
        LEFT JOIN ALL_COL_COMMENTS cm
            ON cm.TABLE_NAME = c.TABLE_NAME
            AND cm.COLUMN_NAME = c.COLUMN_NAME
            AND cm.OWNER = c.OWNER
        WHERE c.COLUMN_NAME LIKE :1
          AND c.OWNER NOT IN ('SYS','SYSTEM','DBSNMP','OUTLN')
          {table_filter}
        ORDER BY c.TABLE_NAME, c.COLUMN_ID
    """
    params = [f"%{column_keyword.upper()}%"]
    if table_keyword:
        params.append(f"{table_keyword.upper()}%")
    rows = execute_query(sql, params)
    return rows_to_markdown(rows)


@mcp.tool()
def get_foreign_keys(table_name: str) -> str:
    """
    Retorna as foreign keys de uma tabela: qual coluna local aponta
    para qual tabela/coluna de destino.
    Aceita tanto o nome da tabela Oracle quanto o EntityName (NOMEINSTANCIA).

    Exemplos:
      get_foreign_keys("TGFITE")
      get_foreign_keys("ItemNota")
    """
    resolved, _ = resolve_table_name(table_name)
    sql = """
        SELECT
            a.CONSTRAINT_NAME,
            a.COLUMN_NAME         AS coluna_origem,
            c.TABLE_NAME          AS tabela_destino,
            c_pk.COLUMN_NAME      AS coluna_destino
        FROM ALL_CONS_COLUMNS a
        JOIN ALL_CONSTRAINTS   b  ON a.OWNER = b.OWNER
                                  AND a.CONSTRAINT_NAME = b.CONSTRAINT_NAME
        JOIN ALL_CONSTRAINTS   c  ON b.R_OWNER = c.OWNER
                                  AND b.R_CONSTRAINT_NAME = c.CONSTRAINT_NAME
        JOIN ALL_CONS_COLUMNS  c_pk ON c.OWNER = c_pk.OWNER
                                   AND c.CONSTRAINT_NAME = c_pk.CONSTRAINT_NAME
        WHERE b.CONSTRAINT_TYPE = 'R'
          AND a.TABLE_NAME = :1
        ORDER BY a.CONSTRAINT_NAME, a.POSITION
    """
    rows = execute_query(sql, [resolved])
    if not rows:
        return f"Nenhuma FK encontrada para `{resolved}`."
    return f"## Foreign Keys — {resolved}\n\n{rows_to_markdown(rows)}"


@mcp.tool()
def get_indexes(table_name: str) -> str:
    """
    Lista os índices de uma tabela e suas colunas.
    Útil para otimizar queries e entender chaves de busca.
    Aceita tanto o nome da tabela Oracle quanto o EntityName (NOMEINSTANCIA).

    Exemplos:
      get_indexes("TGFCAB")
      get_indexes("CabeçalhoNota")
    """
    resolved, _ = resolve_table_name(table_name)
    sql = """
        SELECT
            i.INDEX_NAME,
            i.INDEX_TYPE,
            i.UNIQUENESS,
            ic.COLUMN_NAME,
            ic.COLUMN_POSITION
        FROM ALL_INDEXES i
        JOIN ALL_IND_COLUMNS ic
            ON ic.INDEX_NAME = i.INDEX_NAME
            AND ic.TABLE_NAME = i.TABLE_NAME
        WHERE i.TABLE_NAME = :1
          AND i.OWNER NOT IN ('SYS','SYSTEM')
        ORDER BY i.INDEX_NAME, ic.COLUMN_POSITION
    """
    rows = execute_query(sql, [resolved])
    if not rows:
        return f"Nenhum índice encontrado para `{resolved}`."
    return f"## Índices — {resolved}\n\n{rows_to_markdown(rows)}"


@mcp.tool()
def run_query(sql: str, limit: int = 50) -> str:
    """
    Executa uma query SELECT na base Sankhya local e retorna até
    `limit` linhas formatadas como tabela Markdown.

    ATENÇÃO: Apenas SELECT é permitido. Queries de escrita serão bloqueadas.

    Exemplo:
      run_query("SELECT NUNOTA, CODPARC, VLRNOTA FROM TGFCAB WHERE ROWNUM <= 5")
    """
    sql_clean = sql.strip().upper()
    forbidden = ["INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE", "ALTER", "CREATE", "MERGE"]
    for keyword in forbidden:
        if sql_clean.startswith(keyword):
            return f"❌ Operação `{keyword}` não permitida. Apenas SELECT."

    try:
        rows = execute_query(sql, limit=limit)
        if not rows:
            return "_Query executada sem retorno de linhas._"
        total = len(rows)
        result = rows_to_markdown(rows)
        suffix = f"\n\n_Exibindo {total} linha(s). Use `limit` para ajustar._"
        return result + suffix
    except Exception as e:
        return f"❌ Erro ao executar query:\n```\n{str(e)}\n```"


@mcp.tool()
def validate_query(sql: str) -> str:
    """
    Valida a sintaxe de uma query sem executá-la de fato.
    Usa EXPLAIN PLAN do Oracle para checar erros de sintaxe,
    tabelas inexistentes e colunas inválidas.

    Exemplo: validate_query("SELECT NUNOTA, CODPARC FROM TGFCAB WHERE CODTIPOPER = 1")
    """
    try:
        with get_pool().acquire() as conn:
            with conn.cursor() as cur:
                cur.execute(f"EXPLAIN PLAN FOR {sql}")
                cur.execute("""
                    SELECT OPERATION, OPTIONS, OBJECT_NAME, COST, CARDINALITY
                    FROM PLAN_TABLE
                    ORDER BY ID
                """)
                columns = [col[0].lower() for col in cur.description]
                rows = [dict(zip(columns, row)) for row in cur.fetchall()]
            conn.rollback()

        if not rows:
            return "✅ Query válida (sem plano retornado)."
        return f"✅ Query válida.\n\n## Plano de Execução\n\n{rows_to_markdown(rows)}"
    except Exception as e:
        return f"❌ Query inválida:\n```\n{str(e)}\n```"


@mcp.tool()
def table_sample(table_name: str, limit: int = 10) -> str:
    """
    Retorna uma amostra de dados reais de uma tabela.
    Útil para entender o conteúdo e o formato dos campos.
    Aceita tanto o nome da tabela Oracle quanto o EntityName (NOMEINSTANCIA).

    Exemplos:
      table_sample("TGFTOP", limit=5)
      table_sample("TipoOperacao", limit=5)
    """
    resolved, _ = resolve_table_name(table_name)
    try:
        sql = f"SELECT * FROM {resolved} WHERE ROWNUM <= :1"
        rows = execute_query(sql, [limit])
        if not rows:
            return f"Tabela `{resolved}` está vazia ou não existe."
        return f"## Amostra — {resolved} ({len(rows)} linha(s))\n\n{rows_to_markdown(rows)}"
    except Exception as e:
        return f"❌ Erro:\n```\n{str(e)}\n```"


@mcp.tool()
def search_entities(keyword: str, only_root: bool = False) -> str:
    """
    Busca instâncias (EntityNames) do Sankhya por nome ou descrição.
    Útil para descobrir qual EntityName ou tabela corresponde a um conceito de negócio.

    Parâmetros:
      keyword   — termo de busca em português ou nome de entidade
      only_root — se True, retorna apenas instâncias raiz (exclui sub-instâncias com filtro)

    Exemplos:
      search_entities("nota fiscal")   → entidades de NF
      search_entities("pedido")        → entidades de pedido de venda
      search_entities("parceiro")      → entidades de parceiro/cliente/fornecedor
      search_entities("CabeçalhoNota") → busca direta por EntityName
    """
    root_filter = "AND RAIZ = 'S'" if only_root else ""
    sql = f"""
        SELECT
            NOMETAB        AS tabela,
            NOMEINSTANCIA  AS entity_name,
            DESCRINSTANCIA AS descricao,
            RAIZ           AS raiz,
            DOMAIN         AS dominio
        FROM TDDINS
        WHERE (
            UPPER(NOMEINSTANCIA)  LIKE UPPER(:1)
            OR UPPER(DESCRINSTANCIA) LIKE UPPER(:1)
        )
          AND ATIVO = 'S'
          {root_filter}
        ORDER BY RAIZ DESC, NOMETAB, NOMEINSTANCIA
    """
    rows = execute_query(sql, [f"%{keyword}%"])
    if not rows:
        return f"_Nenhuma entidade encontrada para `{keyword}`._"
    return f"## Entidades — '{keyword}'\n\n{rows_to_markdown(rows)}"


@mcp.tool()
def list_modules() -> str:
    """
    Lista os principais grupos de tabelas do Sankhya por prefixo,
    com contagem de tabelas em cada módulo.

    Retorna uma visão geral dos módulos disponíveis no schema.
    """
    sql = """
        SELECT
            REGEXP_SUBSTR(TABLE_NAME, '^[A-Z]+') AS prefixo,
            COUNT(*) AS qtd_tabelas
        FROM ALL_TABLES
        WHERE OWNER NOT IN ('SYS','SYSTEM','DBSNMP','OUTLN')
          AND TABLE_NAME NOT LIKE 'BIN$%'
        GROUP BY REGEXP_SUBSTR(TABLE_NAME, '^[A-Z]+')
        HAVING COUNT(*) > 1
        ORDER BY qtd_tabelas DESC
    """
    rows = execute_query(sql)
    return f"## Módulos do Schema Sankhya\n\n{rows_to_markdown(rows)}"


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
