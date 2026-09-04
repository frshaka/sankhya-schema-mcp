"""
Sankhya Schema MCP Server
Conecta ao banco Oracle local (container Docker) via oracledb em modo thick
com Oracle Instant Client 21c.
"""

import os
import re
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
    "host":         os.getenv("SANKHYA_DB_HOST",         "localhost"),
    "port":         int(os.getenv("SANKHYA_DB_PORT",     "1521")),
    "sid":          os.getenv("SANKHYA_DB_SERVICE",      "XE"),
    "service_name": os.getenv("SANKHYA_DB_SERVICE_NAME", None),
    "user":         os.getenv("SANKHYA_DB_USER",         "SANKHYA"),
    "password":     os.getenv("SANKHYA_DB_PASSWORD",     "oracle"),
}

_pool: Optional[oracledb.ConnectionPool] = None


def get_pool() -> oracledb.ConnectionPool:
    global _pool
    if _pool is None:
        _ensure_oracle_client()
        # service_name tem precedência sobre SID quando informado
        if DB_CONFIG["service_name"]:
            dsn = oracledb.makedsn(
                DB_CONFIG["host"], DB_CONFIG["port"],
                service_name=DB_CONFIG["service_name"],
            )
        else:
            dsn = oracledb.makedsn(
                DB_CONFIG["host"], DB_CONFIG["port"],
                sid=DB_CONFIG["sid"],
            )
        _pool = oracledb.create_pool(
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            dsn=dsn,
            min=1,
            max=5,
            increment=1,
        )
    return _pool


# Teto para buscas abertas (search_*), cujo resultado cresce com o schema inteiro
# e não com uma tabela específica. Metadados de uma única tabela usam limit=None.
DEFAULT_ROW_LIMIT = 200
# Schemas internos do Oracle, excluídos de toda consulta a metadados. Interpolado
# via f-string nas queries (é lista fixa, nunca vem de entrada do usuário).
SYSTEM_OWNERS = "('SYS','SYSTEM','DBSNMP','OUTLN')"
# Identifica os planos gerados por este servidor dentro da PLAN_TABLE.
PLAN_STATEMENT_ID = "SANKHYA_MCP"
# Teto de colunas da amostra quando o chamador nao escolhe quais quer ver.
# Tabela Sankhya e larga (TGFTOP passa de 600 colunas): um SELECT * inteiro
# entope a janela de contexto de quem chamou sem ensinar nada a mais.
SAMPLE_COLUMN_LIMIT = 25


def fetch_rows(
    sql: str, params: list = None, limit: Optional[int] = DEFAULT_ROW_LIMIT
) -> tuple[list[dict], bool]:
    """
    Executa uma query e retorna (linhas, truncado).

    Com `limit` numérico, busca `limit + 1` linhas para descobrir se o resultado foi
    cortado sem precisar de um COUNT extra: `truncado` é True quando há mais linhas
    no banco.

    Com `limit=None` não há teto — o resultado vem inteiro e `truncado` é sempre
    False. É o modo usado pelas consultas de metadados de uma única tabela
    (colunas, índices, FKs), onde o volume é limitado pela própria tabela e um
    corte esconderia parte do schema.

    A sessão é forçada a READ ONLY antes da execução: qualquer DML/DDL que
    porventura escape da validação de aplicação é bloqueado pelo próprio Oracle
    (ORA-01456). É a segunda camada de proteção contra escrita.
    """
    # `limit` chega do cliente MCP sem validação: 0 devolveria lista vazia com
    # truncado=True (resultado com linhas anunciado como vazio) e um negativo
    # cortaria o fim do resultado em `rows[:limit]`.
    if limit is not None:
        limit = max(1, limit)
    with get_pool().acquire() as conn:
        # Garante início de transação limpo antes de marcá-la como somente leitura
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute(sql, params or [])
            columns = [col[0].lower() for col in cur.description]
            if limit is None:
                rows, truncated = cur.fetchall(), False
            else:
                rows = cur.fetchmany(limit + 1)
                truncated = len(rows) > limit
                rows = rows[:limit]
            result = [dict(zip(columns, row)) for row in rows]
        # Encerra a transação somente leitura antes de devolver a conexão ao pool
        conn.rollback()
        return result, truncated


def execute_query(
    sql: str, params: list = None, limit: Optional[int] = DEFAULT_ROW_LIMIT
) -> list[dict]:
    """Atalho para `fetch_rows` quando o aviso de truncamento não é necessário."""
    return fetch_rows(sql, params, limit)[0]


def truncation_note(truncated: bool, limit: int = DEFAULT_ROW_LIMIT) -> str:
    """
    Aviso explícito de corte. Resultado truncado em silêncio é pior que resultado
    vazio: o consumidor conclui que os dados faltantes não existem.
    """
    if not truncated:
        return ""
    return f"\n\n> ⚠️ Resultado truncado em {limit} linha(s). Refine a busca para ver o restante."


def select_columns(
    rows: list[dict], columns: str = ""
) -> tuple[list[dict], list[str], int]:
    """
    Projeta colunas sobre linhas que ja vieram do banco.
    Retorna (linhas_projetadas, nomes_nao_encontrados, qtd_colunas_cortadas).

    A projecao acontece em Python e nao no SELECT de proposito: sem SQL dinamico
    nao ha superficie nova de injecao nem validacao nova a escrever, e as chaves
    dos dicts que `fetch_rows` devolve ja vem na ordem das colunas da tabela.
    Trazer 600 colunas de 10 linhas e descartar quase todas nao custa nada.

    Sem `columns`, mantem as SAMPLE_COLUMN_LIMIT primeiras (ordem da tabela) e
    informa quantas ficaram de fora — cabe ao chamador avisar, porque resultado
    cortado em silencio e pior que resultado vazio.

    Com `columns`, o match e case-insensitive e tolerante a espacos (as chaves
    chegam minusculas de `fetch_rows` e o usuario digita em maiusculas), e os
    nomes pedidos que nao existem voltam em `nomes_nao_encontrados` em vez de
    sumirem. Quando nenhum dos pedidos existe, as linhas voltam vazias.
    """
    if not rows:
        return rows, [], 0

    disponiveis = list(rows[0])

    if columns.strip():
        pedidas = list(dict.fromkeys(c.strip() for c in columns.split(",") if c.strip()))
        indice = {c.lower(): c for c in disponiveis}
        mantidas = [indice[p.lower()] for p in pedidas if p.lower() in indice]
        ausentes = [p for p in pedidas if p.lower() not in indice]
        cortadas = 0
    else:
        mantidas = disponiveis[:SAMPLE_COLUMN_LIMIT]
        ausentes = []
        cortadas = len(disponiveis) - len(mantidas)

    projetadas = [{c: row[c] for c in mantidas} for row in rows] if mantidas else []
    return projetadas, ausentes, cortadas


def rows_to_markdown(rows: list[dict]) -> str:
    """Converte lista de dicts para tabela Markdown."""
    if not rows:
        return "_Nenhum resultado encontrado._"
    headers = list(rows[0].keys())
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for row in rows:
        # Só None vira célula vazia: 0, False e Decimal("0.00") são valores
        # reais e virariam NULL aos olhos de quem lê a tabela. O `|` é escapado
        # porque comentário de coluna do dicionário Sankhya pode conter um.
        cells = [
            "" if row.get(h) is None else str(row[h]).replace("|", "\\|")
            for h in headers
        ]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def pick_owner(owners: set[str]) -> str:
    """
    Escolhe um único schema quando a mesma tabela aparece em mais de um owner
    visível: o do usuário conectado, se estiver entre eles; senão o primeiro em
    ordem alfabética.
    """
    conectado = (DB_CONFIG["user"] or "").upper()
    return conectado if conectado in owners else sorted(owners)[0]


def _is_missing_object(exc: oracledb.DatabaseError) -> bool:
    """True se o erro for ORA-00942 (tabela/view inexistente ou sem acesso)."""
    return "ORA-00942" in str(exc)


def resolve_table_name(name: str) -> tuple[str, list[dict]]:
    """
    Resolve EntityName (NOMEINSTANCIA) para nome de tabela Oracle via TDDINS.
    Retorna (table_name, entity_rows).
    Se não encontrar em TDDINS, devolve o nome original em maiúsculas e lista vazia.

    Enriquecimento opcional: quando o dicionário Sankhya (TDDINS) não existe no
    schema conectado (ORA-00942), degrada silenciosamente e devolve o nome cru,
    para não inviabilizar quem só quer descrever colunas de uma tabela Oracle.
    """
    sql = """
        SELECT NOMETAB, NOMEINSTANCIA, DESCRINSTANCIA, RAIZ, NUINSTANCIAPAI
        FROM TDDINS
        WHERE UPPER(NOMEINSTANCIA) = UPPER(:1)
          AND ATIVO = 'S'
        ORDER BY RAIZ DESC, NUINSTANCIA
    """
    try:
        rows = execute_query(sql, [name], limit=None)
    except oracledb.DatabaseError as exc:
        if _is_missing_object(exc):
            return name.upper(), []
        raise
    if rows:
        # Oracle é case-insensitive sem aspas, mas `assert_safe_identifier` só
        # aceita maiúsculas: sem o .upper() um NOMETAB minúsculo no TDDINS
        # reprovaria uma tabela válida.
        return rows[0]["nometab"].upper(), rows
    return name.upper(), []


def assert_read_only_query(sql: str) -> Optional[str]:
    """
    Valida que `sql` é uma única consulta de leitura (SELECT ou WITH ... SELECT).
    Retorna a mensagem de erro se reprovar, ou None se aprovar.

    Usa allowlist (mais seguro que blocklist):
    - remove comentários (-- de linha e /* de bloco */) para impedir disfarce;
    - exige que o comando comece com SELECT ou WITH;
    - rejeita múltiplos comandos (;) e PL/SQL inline (WITH FUNCTION/PROCEDURE),
      que poderiam contornar a transação READ ONLY via transação autônoma.
    """
    no_block = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    no_comments = re.sub(r"--[^\n]*", " ", no_block)
    core = no_comments.strip().rstrip(";").strip()

    if not core:
        return "Query vazia."
    if ";" in core:
        return "Múltiplos comandos não são permitidos (apenas um SELECT por chamada)."

    upper = core.upper()
    if not re.match(r"^(SELECT|WITH)\b", upper):
        return "Apenas comandos SELECT (ou WITH ... SELECT) são permitidos."
    if re.match(r"^WITH\s+(FUNCTION|PROCEDURE)\b", upper):
        return "WITH FUNCTION/PROCEDURE não é permitido."

    return None


_IDENTIFIER_RE = re.compile(r"^[A-Z0-9_$#]+(\.[A-Z0-9_$#]+)?$")


def assert_safe_identifier(name: str) -> Optional[str]:
    """
    Valida um nome de tabela antes de interpolá-lo em SQL.
    Retorna a mensagem de erro se reprovar, ou None se aprovar.

    Necessário porque `resolve_table_name` devolve o texto informado pelo usuário
    (em maiúsculas) quando o dicionário Sankhya não resolve o nome — ou seja, o
    valor não pode ser tratado como confiável.
    """
    if not _IDENTIFIER_RE.match(name or ""):
        return f"Nome de tabela inválido: `{name}`."
    return None


# ---------------------------------------------------------------------------
# Servidor MCP
# ---------------------------------------------------------------------------

mcp = FastMCP(
    name="sankhya-schema",
    instructions=(
        "Servidor de exploração do schema Oracle do Sankhya ERP.\n\n"
        "AÇÃO IMEDIATA — LEIA ANTES DE QUALQUER OUTRA DECISÃO:\n"
        "Quando o usuário mencionar tabelas, campos, queries, SQL, schema, ou qualquer "
        "entidade do Sankhya (notas, produtos, parceiros, qualidade, amostras, laudos, etc.), "
        "sua PRIMEIRA ação deve ser chamar search_tables ou describe_table deste MCP. "
        "Não use Agent, não use Bash, não use Grep, não tente pesquisar no código local. "
        "Vá direto às tools deste MCP como primeiro passo.\n\n"
        "FLUXO CORRETO:\n"
        "1. Usuário pede algo relacionado ao banco/schema → chame search_tables imediatamente\n"
        "2. Identifique as tabelas relevantes → chame describe_table para cada uma\n"
        "3. Com o schema real em mãos → escreva a query\n"
        "4. NUNCA pule os passos 1 e 2. NUNCA invente nomes de tabelas ou colunas.\n\n"
        "PROIBIÇÕES:\n"
        "- Só delegue tarefas que dependem deste MCP para subagents cuja definição inclua "
        "as tools `mcp__sankhya-schema__*`. Na dúvida, resolva no agente principal.\n"
        "- NUNCA tente conexão direta ao banco Oracle.\n"
        "- NUNCA invente, chute ou assuma credenciais.\n"
        "- NUNCA use listMcpResources para tentar acessar este servidor. Use as tools diretamente: "
        "search_tables, describe_table, etc.\n"
        "- Se uma tool falhar, informe o usuário e aguarde. Não contorne com scripts ou outros meios."
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

    sql = f"""
        SELECT
            c.COLUMN_NAME,
            c.DATA_TYPE,
            c.DATA_LENGTH,
            c.DATA_PRECISION,
            c.DATA_SCALE,
            c.NULLABLE,
            cm.COMMENTS,
            c.OWNER
        FROM ALL_TAB_COLUMNS c
        LEFT JOIN ALL_COL_COMMENTS cm
            ON cm.TABLE_NAME = c.TABLE_NAME
            AND cm.COLUMN_NAME = c.COLUMN_NAME
            AND cm.OWNER = c.OWNER
        WHERE c.TABLE_NAME = :1
          AND c.OWNER NOT IN {SYSTEM_OWNERS}
        ORDER BY c.COLUMN_ID
    """
    # limit=None: toda coluna da tabela precisa aparecer, sem exceção.
    rows = execute_query(sql, [resolved], limit=None)
    if not rows:
        return f"Tabela `{resolved}` não encontrada ou sem colunas."

    # A mesma tabela pode existir em vários schemas visíveis. Sem fixar um owner,
    # as colunas viriam duplicadas e o total no rodapé seria falso. Preferimos o
    # schema do usuário conectado; senão, o primeiro em ordem alfabética.
    owners = {r["owner"] for r in rows}
    owner = pick_owner(owners)
    rows = [r for r in rows if r["owner"] == owner]
    for r in rows:
        del r["owner"]

    header = f"## {resolved}"
    if len(owners) > 1:
        outros = ", ".join(f"`{o}`" for o in sorted(owners) if o != owner)
        header += (
            f"\n**Schema:** `{owner}` — atenção: esta tabela também existe em {outros}."
        )
    if entity_rows:
        e = entity_rows[0]
        header += f"\n**EntityName:** `{e['nomeinstancia']}` — {e['descrinstancia']}"

    result = f"{header}\n\n{rows_to_markdown(rows)}\n\n_{len(rows)} coluna(s)._"

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
    try:
        inst_rows = execute_query(inst_sql, [resolved], limit=None)
    except oracledb.DatabaseError as exc:
        if not _is_missing_object(exc):
            raise
        inst_rows = []  # dicionário Sankhya ausente: segue só com as colunas
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
    sql = f"""
        SELECT
            t.TABLE_NAME,
            t.NUM_ROWS,
            cm.COMMENTS
        FROM ALL_TABLES t
        LEFT JOIN ALL_TAB_COMMENTS cm
            ON cm.TABLE_NAME = t.TABLE_NAME
            AND cm.OWNER = t.OWNER
        WHERE t.TABLE_NAME LIKE :1
          AND t.OWNER NOT IN {SYSTEM_OWNERS}
        ORDER BY t.TABLE_NAME
    """
    rows, truncated = fetch_rows(sql, [f"%{keyword.upper()}%"])
    return rows_to_markdown(rows) + truncation_note(truncated)


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
    table_filter = "AND c.TABLE_NAME LIKE :2" if table_keyword else ""
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
          AND c.OWNER NOT IN {SYSTEM_OWNERS}
          {table_filter}
        ORDER BY c.TABLE_NAME, c.COLUMN_ID
    """
    params = [f"%{column_keyword.upper()}%"]
    if table_keyword:
        params.append(f"{table_keyword.upper()}%")
    rows, truncated = fetch_rows(sql, params)
    return rows_to_markdown(rows) + truncation_note(truncated)


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
    rows = execute_query(sql, [resolved], limit=None)
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
    sql = f"""
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
            AND ic.INDEX_OWNER = i.OWNER
            AND ic.TABLE_OWNER = i.TABLE_OWNER
        WHERE i.TABLE_NAME = :1
          AND i.OWNER NOT IN {SYSTEM_OWNERS}
        ORDER BY i.INDEX_NAME, ic.COLUMN_POSITION
    """
    rows = execute_query(sql, [resolved], limit=None)
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
    erro = assert_read_only_query(sql)
    if erro:
        return f"❌ {erro}"

    limit = max(1, limit)  # mesmo piso aplicado por fetch_rows, para o aviso não mentir
    try:
        rows, truncated = fetch_rows(sql, limit=limit)
        if not rows:
            return "_Query executada sem retorno de linhas._"
        suffix = f"\n\n_Exibindo {len(rows)} linha(s). Use `limit` para ajustar._"
        return rows_to_markdown(rows) + suffix + truncation_note(truncated, limit)
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
    erro = assert_read_only_query(sql)
    if erro:
        return f"❌ {erro}"

    try:
        # Sem SET TRANSACTION READ ONLY aqui: o próprio EXPLAIN PLAN grava na
        # PLAN_TABLE e seria bloqueado com ORA-01456. O rollback ao final desfaz
        # tudo, e a allowlist acima já garante que `sql` é somente leitura.
        with get_pool().acquire() as conn:
            with conn.cursor() as cur:
                # STATEMENT_ID isola o plano desta chamada. Quando a PLAN_TABLE é
                # permanente (criada via utlxplan.sql) e compartilhada entre usuários,
                # um SELECT sem filtro traria também o plano dos outros.
                # A limpeza das linhas fica por conta do rollback ao final.
                cur.execute(f"EXPLAIN PLAN SET STATEMENT_ID = '{PLAN_STATEMENT_ID}' FOR {sql}")
                cur.execute("""
                    SELECT OPERATION, OPTIONS, OBJECT_NAME, COST, CARDINALITY
                    FROM PLAN_TABLE
                    WHERE STATEMENT_ID = :1
                    ORDER BY ID
                """, [PLAN_STATEMENT_ID])
                columns = [col[0].lower() for col in cur.description]
                rows = [dict(zip(columns, row)) for row in cur.fetchall()]
            conn.rollback()

        if not rows:
            return "✅ Query válida (sem plano retornado)."
        return f"✅ Query válida.\n\n## Plano de Execução\n\n{rows_to_markdown(rows)}"
    except Exception as e:
        # PLAN_TABLE ausente/sem acesso (ORA-00942, ORA-02404) é falha de ambiente,
        # não da query: reprovar a query aqui seria um veredito falso.
        if _is_missing_object(e) or "ORA-02404" in str(e):
            return (
                "⚠️ Não foi possível analisar a query: a PLAN_TABLE não existe ou não "
                "está acessível para este usuário. Crie-a (`utlxplan.sql`) ou libere "
                "acesso a ela para usar o EXPLAIN PLAN.\n"
                f"```\n{str(e)}\n```"
            )
        return f"❌ Query inválida:\n```\n{str(e)}\n```"


@mcp.tool()
def table_sample(table_name: str, limit: int = 10, columns: str = "") -> str:
    """
    Retorna uma amostra de dados reais de uma tabela.
    Útil para entender o conteúdo e o formato dos campos.
    Aceita tanto o nome da tabela Oracle quanto o EntityName (NOMEINSTANCIA).

    Tabela Sankhya é larga (TGFTOP passa de 600 colunas). Sem `columns`, a
    amostra traz apenas as primeiras colunas na ordem da tabela e avisa quantas
    ficaram de fora — informe `columns` para ver exatamente as que interessam.

    Parâmetros:
      columns — colunas a exibir, separadas por vírgula. Case-insensitive e
                tolerante a espaços. Nome inexistente é reportado na saída.

    Fluxo natural: chame `describe_table` primeiro para conhecer os nomes das
    colunas, depois `table_sample` com as colunas de interesse.

    Exemplos:
      table_sample("TGFCAB", limit=5)
      table_sample("TGFCAB", limit=5, columns="NUNOTA,CODPARC,VLRNOTA")
      table_sample("TipoOperacao", limit=5, columns="CODTIPOPER, DESCROPER")
    """
    resolved, _ = resolve_table_name(table_name)
    erro = assert_safe_identifier(resolved)
    if erro:
        return f"❌ {erro}"

    try:
        sql = f"SELECT * FROM {resolved} WHERE ROWNUM <= :1"
        rows = execute_query(sql, [limit], limit=limit)
        if not rows:
            return f"Tabela `{resolved}` está vazia ou não existe."

        total_colunas = len(rows[0])
        amostra, ausentes, cortadas = select_columns(rows, columns)
        if not amostra:
            return (
                f"❌ Nenhuma das colunas pedidas existe em `{resolved}`: "
                f"{', '.join(ausentes)}.\n"
                f'Use `describe_table("{resolved}")` para ver os nomes válidos.'
            )

        avisos = []
        if ausentes:
            avisos.append(
                f"> ⚠️ Coluna(s) inexistente(s) em `{resolved}`, ignorada(s): "
                f"{', '.join(ausentes)}."
            )
        if cortadas:
            avisos.append(
                f"> ⚠️ Exibindo {len(amostra[0])} de {total_colunas} colunas — "
                f"{cortadas} ficaram de fora. Para ver as demais, informe "
                f'`columns="COL_A,COL_B"` (use `describe_table("{resolved}")` '
                f"para conhecer os nomes)."
            )
        rodape = "\n\n" + "\n".join(avisos) if avisos else ""

        return (
            f"## Amostra — {resolved} ({len(amostra)} linha(s))\n\n"
            f"{rows_to_markdown(amostra)}{rodape}"
        )
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
    rows, truncated = fetch_rows(sql, [f"%{keyword}%"])
    if not rows:
        return f"_Nenhuma entidade encontrada para `{keyword}`._"
    note = truncation_note(truncated)
    return f"## Entidades — '{keyword}'\n\n{rows_to_markdown(rows)}{note}"


@mcp.tool()
def list_modules() -> str:
    """
    Lista os principais grupos de tabelas do Sankhya por prefixo,
    com contagem de tabelas em cada módulo.

    Retorna uma visão geral dos módulos disponíveis no schema.
    """
    sql = f"""
        SELECT
            REGEXP_SUBSTR(TABLE_NAME, '^[A-Z]+') AS prefixo,
            COUNT(*) AS qtd_tabelas
        FROM ALL_TABLES
        WHERE OWNER NOT IN {SYSTEM_OWNERS}
          AND TABLE_NAME NOT LIKE 'BIN$%'
        GROUP BY REGEXP_SUBSTR(TABLE_NAME, '^[A-Z]+')
        HAVING COUNT(*) > 1
        ORDER BY qtd_tabelas DESC
    """
    rows = execute_query(sql, limit=None)
    return f"## Módulos do Schema Sankhya\n\n{rows_to_markdown(rows)}"


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
