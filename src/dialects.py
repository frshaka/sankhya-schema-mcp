"""
Dialetos de banco do Sankhya Schema MCP.

Concentra tudo que difere entre Oracle e SQL Server: as queries de catálogo, a
abertura de conexão, o comando que abre a transação de leitura e o EXPLAIN.
O `server.py` não sabe em qual banco está — pede a query pelo nome e conecta.

Não há classe abstrata aqui de propósito: são duas implementações concretas e
fechadas. Um dict de queries por dialeto e uma função de conexão bastam.
"""

import os
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


# ---------------------------------------------------------------------------
# Placeholders de bind
# ---------------------------------------------------------------------------
# Cada query carrega o próprio placeholder já no texto: `:1`/`:2` no oracledb,
# `%s` no pymssql. Os templates usam `{p1}`/`{p2}` e `query()` resolve.
# Regra: um parâmetro por placeholder — o pymssql não reaproveita bind como o
# Oracle faz com `:1` repetido.

_BIND = {
    "oracle":    lambda n: f":{n}",
    "sqlserver": lambda n: "%s",
}


# ---------------------------------------------------------------------------
# Queries do dicionário Sankhya (TDDINS)
# ---------------------------------------------------------------------------
# TDDINS é tabela da aplicação, não do catálogo: idêntica nos dois bancos.
# Só o placeholder muda, então estas três não são duplicadas por dialeto.

_TDDINS_QUERIES = {
    "resolve_table": """
        SELECT NOMETAB, NOMEINSTANCIA, DESCRINSTANCIA, RAIZ, NUINSTANCIAPAI
        FROM {schema}TDDINS
        WHERE UPPER(NOMEINSTANCIA) = UPPER({p1})
          AND ATIVO = 'S'
        ORDER BY RAIZ DESC, NUINSTANCIA
    """,
    "instances_by_table": """
        SELECT
            NOMEINSTANCIA  AS entity_name,
            DESCRINSTANCIA AS descricao,
            RAIZ           AS raiz,
            NUINSTANCIAPAI AS instancia_pai
        FROM {schema}TDDINS
        WHERE NOMETAB = {p1}
          AND ATIVO = 'S'
        ORDER BY RAIZ DESC, NOMEINSTANCIA
    """,
    "search_entities": """
        SELECT
            NOMETAB        AS tabela,
            NOMEINSTANCIA  AS entity_name,
            DESCRINSTANCIA AS descricao,
            RAIZ           AS raiz,
            DOMAIN         AS dominio
        FROM {schema}TDDINS
        WHERE (
            UPPER(NOMEINSTANCIA)     LIKE UPPER({p1})
            OR UPPER(DESCRINSTANCIA) LIKE UPPER({p2})
        )
          AND ATIVO = 'S'
          {filtro}
        ORDER BY RAIZ DESC, NOMETAB, NOMEINSTANCIA
    """,
}


# ---------------------------------------------------------------------------
# Queries de catálogo — Oracle
# ---------------------------------------------------------------------------
# Schemas internos, excluídos de toda consulta a metadados. Interpolado direto
# no texto (é lista fixa, nunca vem de entrada do usuário).
_ORACLE_SYSTEM_OWNERS = "('SYS','SYSTEM','DBSNMP','OUTLN')"

_ORACLE_QUERIES = {
    "columns": f"""
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
        WHERE c.TABLE_NAME = {{p1}}
          AND c.OWNER NOT IN {_ORACLE_SYSTEM_OWNERS}
        ORDER BY c.COLUMN_ID
    """,
    "tables": f"""
        SELECT
            t.TABLE_NAME,
            t.NUM_ROWS,
            cm.COMMENTS
        FROM ALL_TABLES t
        LEFT JOIN ALL_TAB_COMMENTS cm
            ON cm.TABLE_NAME = t.TABLE_NAME
            AND cm.OWNER = t.OWNER
        WHERE t.TABLE_NAME LIKE {{p1}}
          AND t.OWNER NOT IN {_ORACLE_SYSTEM_OWNERS}
        ORDER BY t.TABLE_NAME
    """,
    "columns_search": f"""
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
        WHERE c.COLUMN_NAME LIKE {{p1}}
          AND c.OWNER NOT IN {_ORACLE_SYSTEM_OWNERS}
          {{filtro}}
        ORDER BY c.TABLE_NAME, c.COLUMN_ID
    """,
    "foreign_keys": """
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
          AND a.TABLE_NAME = {p1}
        ORDER BY a.CONSTRAINT_NAME, a.POSITION
    """,
    "indexes": f"""
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
        WHERE i.TABLE_NAME = {{p1}}
          AND i.OWNER NOT IN {_ORACLE_SYSTEM_OWNERS}
        ORDER BY i.INDEX_NAME, ic.COLUMN_POSITION
    """,
    # `list_modules` agrupa o prefixo em Python (ver `group_prefixes`): o
    # SQL Server não tem REGEXP_SUBSTR e agrupar dos dois lados no mesmo código
    # garante que os dois bancos respondam a mesma coisa.
    "table_names": f"""
        SELECT TABLE_NAME
        FROM ALL_TABLES
        WHERE OWNER NOT IN {_ORACLE_SYSTEM_OWNERS}
          AND TABLE_NAME NOT LIKE 'BIN$%'
    """,
    "table_sample": "SELECT * FROM {schema}{tabela} WHERE ROWNUM <= {p1}",
}


# ---------------------------------------------------------------------------
# Queries de catálogo — SQL Server
# ---------------------------------------------------------------------------
# O OWNER do Oracle vira o schema do SQL Server. Na base `jiva` distribuída pela
# Sankhya o schema das tabelas é `SANKHYA` (não `dbo`), então ele é tratado como
# dado — nunca fixado no texto da query — e `pick_owner` continua decidindo qual
# schema vence quando a mesma tabela aparece em mais de um.
_MSSQL_SYSTEM_OWNERS = "('sys','INFORMATION_SCHEMA','guest')"

# Comentário de tabela/coluna: o Oracle tem ALL_TAB_COMMENTS/ALL_COL_COMMENTS,
# o SQL Server só a propriedade estendida `MS_Description`. Na base de
# desenvolvimento ela vem vazia — o LEFT JOIN degrada para NULL sem quebrar.
_MSSQL_OBJECT_ID = "OBJECT_ID(QUOTENAME(c.TABLE_SCHEMA) + '.' + QUOTENAME(c.TABLE_NAME))"

_MSSQL_QUERIES = {
    "columns": f"""
        SELECT
            c.COLUMN_NAME,
            c.DATA_TYPE,
            c.CHARACTER_MAXIMUM_LENGTH      AS DATA_LENGTH,
            c.NUMERIC_PRECISION             AS DATA_PRECISION,
            c.NUMERIC_SCALE                 AS DATA_SCALE,
            c.IS_NULLABLE                   AS NULLABLE,
            CAST(ep.value AS NVARCHAR(MAX)) AS COMMENTS,
            c.TABLE_SCHEMA                  AS OWNER
        FROM INFORMATION_SCHEMA.COLUMNS c
        LEFT JOIN sys.extended_properties ep
            ON ep.major_id = {_MSSQL_OBJECT_ID}
            AND ep.minor_id = c.ORDINAL_POSITION
            AND ep.class = 1
            AND ep.name = 'MS_Description'
        WHERE c.TABLE_NAME = {{p1}}
          AND c.TABLE_SCHEMA NOT IN {_MSSQL_SYSTEM_OWNERS}
        ORDER BY c.ORDINAL_POSITION
    """,
    # NUM_ROWS: o Oracle tem ALL_TABLES.NUM_ROWS (estatística do otimizador); o
    # equivalente aqui é somar as partições do heap/índice clusterizado.
    "tables": f"""
        SELECT
            t.TABLE_NAME,
            (
                SELECT SUM(p.rows)
                FROM sys.partitions p
                WHERE p.object_id = OBJECT_ID(QUOTENAME(t.TABLE_SCHEMA) + '.' + QUOTENAME(t.TABLE_NAME))
                  AND p.index_id IN (0, 1)
            ) AS NUM_ROWS,
            CAST(ep.value AS NVARCHAR(MAX)) AS COMMENTS
        FROM INFORMATION_SCHEMA.TABLES t
        LEFT JOIN sys.extended_properties ep
            ON ep.major_id = OBJECT_ID(QUOTENAME(t.TABLE_SCHEMA) + '.' + QUOTENAME(t.TABLE_NAME))
            AND ep.minor_id = 0
            AND ep.class = 1
            AND ep.name = 'MS_Description'
        WHERE t.TABLE_NAME LIKE {{p1}}
          AND t.TABLE_SCHEMA NOT IN {_MSSQL_SYSTEM_OWNERS}
          AND t.TABLE_TYPE = 'BASE TABLE'
        ORDER BY t.TABLE_NAME
    """,
    "columns_search": f"""
        SELECT
            c.TABLE_NAME,
            c.COLUMN_NAME,
            c.DATA_TYPE,
            c.IS_NULLABLE                   AS NULLABLE,
            CAST(ep.value AS NVARCHAR(MAX)) AS COMMENTS
        FROM INFORMATION_SCHEMA.COLUMNS c
        LEFT JOIN sys.extended_properties ep
            ON ep.major_id = {_MSSQL_OBJECT_ID}
            AND ep.minor_id = c.ORDINAL_POSITION
            AND ep.class = 1
            AND ep.name = 'MS_Description'
        WHERE c.COLUMN_NAME LIKE {{p1}}
          AND c.TABLE_SCHEMA NOT IN {_MSSQL_SYSTEM_OWNERS}
          {{filtro}}
        ORDER BY c.TABLE_NAME, c.ORDINAL_POSITION
    """,
    # O schema entra no WHERE por paridade com o lado Oracle, onde o #5 excluiu
    # os owners de sistema destas duas queries: com a mesma tabela visível em
    # dois schemas, as linhas voltariam multiplicadas.
    "foreign_keys": f"""
        SELECT
            fk.name AS CONSTRAINT_NAME,
            pc.name AS coluna_origem,
            rt.name AS tabela_destino,
            rc.name AS coluna_destino
        FROM sys.foreign_keys fk
        JOIN sys.foreign_key_columns fkc ON fkc.constraint_object_id = fk.object_id
        JOIN sys.tables  pt ON pt.object_id = fk.parent_object_id
        JOIN sys.schemas ps ON ps.schema_id = pt.schema_id
        JOIN sys.columns pc ON pc.object_id = fkc.parent_object_id
                           AND pc.column_id = fkc.parent_column_id
        JOIN sys.tables  rt ON rt.object_id = fk.referenced_object_id
        JOIN sys.columns rc ON rc.object_id = fkc.referenced_object_id
                           AND rc.column_id = fkc.referenced_column_id
        WHERE pt.name = {{p1}}
          AND ps.name NOT IN {_MSSQL_SYSTEM_OWNERS}
        ORDER BY fk.name, fkc.constraint_column_id
    """,
    "indexes": f"""
        SELECT
            i.name         AS INDEX_NAME,
            i.type_desc    AS INDEX_TYPE,
            CASE WHEN i.is_unique = 1 THEN 'UNIQUE' ELSE 'NONUNIQUE' END AS UNIQUENESS,
            c.name         AS COLUMN_NAME,
            ic.key_ordinal AS COLUMN_POSITION
        FROM sys.indexes i
        JOIN sys.tables t ON t.object_id = i.object_id
        JOIN sys.schemas s ON s.schema_id = t.schema_id
        JOIN sys.index_columns ic ON ic.object_id = i.object_id
                                 AND ic.index_id = i.index_id
        JOIN sys.columns c ON c.object_id = ic.object_id
                          AND c.column_id = ic.column_id
        WHERE t.name = {{p1}}
          AND i.name IS NOT NULL
          AND s.name NOT IN {_MSSQL_SYSTEM_OWNERS}
        ORDER BY i.name, ic.key_ordinal
    """,
    "table_names": f"""
        SELECT TABLE_NAME
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_TYPE = 'BASE TABLE'
          AND TABLE_SCHEMA NOT IN {_MSSQL_SYSTEM_OWNERS}
    """,
    "table_sample": "SELECT TOP ({p1}) * FROM {schema}{tabela}",
}


QUERIES = {
    "oracle":    {**_TDDINS_QUERIES, **_ORACLE_QUERIES},
    "sqlserver": {**_TDDINS_QUERIES, **_MSSQL_QUERIES},
}


# ---------------------------------------------------------------------------
# Seleção do dialeto
# ---------------------------------------------------------------------------

def resolve_db_type(value: Optional[str]) -> str:
    """
    Normaliza o valor de `SANKHYA_DB_TYPE`.

    Ausente ou vazio cai em `oracle`: era o único banco suportado, e uma
    instalação existente não pode passar a exigir configuração nova.
    Valor desconhecido falha alto — conectar no banco errado é pior que não subir.
    """
    tipo = (value or "").strip().lower() or "oracle"
    if tipo not in QUERIES:
        raise ValueError(
            f"SANKHYA_DB_TYPE inválido: {value!r}. Use 'oracle' ou 'sqlserver'."
        )
    return tipo


DB_TYPE = resolve_db_type(os.getenv("SANKHYA_DB_TYPE"))

DB_CONFIG = {
    "host":         os.getenv("SANKHYA_DB_HOST",         "localhost"),
    "port":         int(os.getenv("SANKHYA_DB_PORT",     "1433" if DB_TYPE == "sqlserver" else "1521")),
    "sid":          os.getenv("SANKHYA_DB_SERVICE",      "XE"),
    "service_name": os.getenv("SANKHYA_DB_SERVICE_NAME", None),
    # SQL Server endereça database, não SID/service name.
    "database":     os.getenv("SANKHYA_DB_DATABASE",     "jiva"),
    "user":         os.getenv("SANKHYA_DB_USER",         "SANKHYA"),
    # `developer` é a senha dos containers de desenvolvimento distribuídos pela
    # Sankhya (skdev-oracle e skdev-mssql), que é o cenário padrão deste MCP.
    "password":     os.getenv("SANKHYA_DB_PASSWORD",     "developer"),
    # Schema onde as tabelas do Sankhya moram, quando não é o do usuário conectado.
    "schema":       os.getenv("SANKHYA_DB_SCHEMA",       None),
}

_IDENTIFIER_RE = re.compile(r"^[A-Z][A-Z0-9_$#]*$")


def resolve_schema(value: Optional[str]) -> Optional[str]:
    """
    Normaliza `SANKHYA_DB_SCHEMA`. Ausente ou vazio devolve None.

    O nome é interpolado no texto das queries e do `ALTER SESSION` — nenhum dos
    dois aceita bind para identificador —, então é validado aqui. Valor com
    ponto, espaço ou pontuação falha alto em vez de virar SQL.
    """
    schema = (value or "").strip().upper()
    if not schema:
        return None
    if not _IDENTIFIER_RE.match(schema):
        raise ValueError(
            f"SANKHYA_DB_SCHEMA inválido: {value!r}. Use apenas o nome do "
            "schema, sem ponto nem espaço."
        )
    return schema


DB_CONFIG["schema"] = resolve_schema(DB_CONFIG["schema"])


def schema_prefix() -> str:
    """
    Prefixo a colar antes de nome de tabela não qualificado (`SANKHYA.`), ou
    string vazia quando não há schema configurado.

    Toda query que nomeia uma tabela da aplicação — as três do TDDINS e a
    amostra — passa por aqui. Sem isso, o banco resolve o nome no schema do
    usuário conectado; quando ele não é o dono das tabelas, o caso normal ao
    usar um login somente-leitura, a resposta é "objeto não existe".
    """
    return f"{DB_CONFIG['schema']}." if DB_CONFIG["schema"] else ""


def query(name: str, **fmt) -> str:
    """
    Devolve a query `name` do dialeto ativo com os placeholders já resolvidos.

    `fmt` preenche os buracos dinâmicos que sobram no texto (`filtro`, `tabela`)
    e também passa pela resolução de placeholder — assim um filtro opcional pode
    escrever `{p2}` sem que o chamador saiba qual banco está ativo.
    O `%s` do pymssql passa intacto pelo `str.format`.
    """
    bind = _BIND[DB_TYPE]
    buracos = {"p1": bind(1), "p2": bind(2), "schema": schema_prefix()}
    fmt = {chave: valor.format(**buracos) for chave, valor in fmt.items()}
    return QUERIES[DB_TYPE][name].format(**{**buracos, **fmt})


# ---------------------------------------------------------------------------
# Conexão
# ---------------------------------------------------------------------------

_INSTANTCLIENT_DIR = str(Path(__file__).parent.parent / "instantclient")
_pool = None


def _set_current_schema(conn, requested_tag):
    """
    Aponta a sessão Oracle para `SANKHYA_DB_SCHEMA`.

    Redundante para as queries deste servidor, que já vão qualificadas por
    `schema_prefix()`. Serve ao `run_query`, cujo SQL é escrito por quem chama:
    com a sessão apontada, `FROM TGFCAB` funciona sem qualificar à mão.

    Não há equivalente no SQL Server — lá o schema padrão vem do mapeamento do
    login (`ALTER USER ... WITH DEFAULT_SCHEMA`), é persistente e exige
    privilégio, então não é papel deste servidor mexer nisso. Ver a seção
    Segurança do README.

    Registrado como `session_callback` do pool: roda uma vez por conexão física
    criada, não a cada query — o `ALTER SESSION` vale por toda a sessão.
    """
    with conn.cursor() as cur:
        cur.execute(f"ALTER SESSION SET CURRENT_SCHEMA = {DB_CONFIG['schema']}")


def _oracle_pool():
    """
    Pool Oracle, criado sob demanda. O Instant Client é inicializado junto: em
    modo thick a carga da biblioteca é cara e travaria o handshake MCP se
    acontecesse no import.
    """
    global _pool
    if _pool is None:
        import oracledb

        oracledb.init_oracle_client(lib_dir=_INSTANTCLIENT_DIR)
        # service_name tem precedência sobre SID quando informado
        if DB_CONFIG["service_name"]:
            dsn = oracledb.makedsn(
                DB_CONFIG["host"], DB_CONFIG["port"],
                service_name=DB_CONFIG["service_name"],
            )
        else:
            dsn = oracledb.makedsn(
                DB_CONFIG["host"], DB_CONFIG["port"], sid=DB_CONFIG["sid"],
            )
        _pool = oracledb.create_pool(
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            dsn=dsn,
            min=1,
            max=5,
            increment=1,
            session_callback=_set_current_schema if DB_CONFIG["schema"] else None,
        )
    return _pool


@contextmanager
def connect():
    """
    Entrega uma conexão com o banco ativo.

    O driver é importado aqui dentro, não no topo do módulo: quem só usa Oracle
    não precisa ter o pymssql instalado, e quem só usa SQL Server não precisa do
    Instant Client.

    Oracle vem de um pool (inicializar o Instant Client é caro). SQL Server abre
    e fecha por chamada: o pymssql não traz pool e a carga deste servidor é a de
    um cliente MCP só.
    """
    if DB_TYPE == "sqlserver":
        try:
            import pymssql
        except ModuleNotFoundError as exc:
            # O driver está fora do requirements.txt para não onerar quem só usa
            # Oracle; sem esta mensagem o usuário recebe só o ModuleNotFoundError.
            raise ModuleNotFoundError(
                "SANKHYA_DB_TYPE=sqlserver exige o driver pymssql, que não está "
                "instalado. Rode: pip install -r requirements-sqlserver.txt"
            ) from exc

        conn = pymssql.connect(
            server=DB_CONFIG["host"],
            port=str(DB_CONFIG["port"]),
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            database=DB_CONFIG["database"],
        )
        try:
            yield conn
        finally:
            conn.close()
    else:
        with _oracle_pool().acquire() as conn:
            yield conn


# Abertura da transação de leitura de `fetch_rows`.
#
# Oracle: `SET TRANSACTION READ ONLY` faz o próprio banco recusar qualquer DML
# na sessão (ORA-01456), mesmo que a validação da aplicação falhe.
#
# SQL Server: NÃO existe equivalente. Uma transação explícita sempre desfeita é
# o mais próximo — ela reverte uma escrita, mas não a impede. Ver a seção
# Segurança do README: a garantia forte depende de um login `db_datareader`.
BEGIN_READ_ONLY = {
    "oracle":    "SET TRANSACTION READ ONLY",
    "sqlserver": "BEGIN TRANSACTION",
}

# Erro de "objeto não existe / sem acesso". Usado para degradar sem quebrar
# quando o dicionário Sankhya (TDDINS) não está no schema conectado.
_MISSING_OBJECT = {
    "oracle":    ("ORA-00942",),
    "sqlserver": ("Invalid object name",),
}


def is_missing_object(exc: Exception) -> bool:
    """True se o erro for de tabela/view inexistente ou sem acesso."""
    return any(marca in str(exc) for marca in _MISSING_OBJECT[DB_TYPE])


# ---------------------------------------------------------------------------
# Plano de execução
# ---------------------------------------------------------------------------


# Identifica os planos gerados por este servidor dentro da PLAN_TABLE do Oracle.
PLAN_STATEMENT_ID = "SANKHYA_MCP"


def _cursor_rows(cur) -> list[dict]:
    columns = [col[0].lower() for col in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def explain_plan(sql: str) -> list[dict]:
    """
    Devolve o plano estimado de `sql` sem executá-la.

    Oracle usa EXPLAIN PLAN + PLAN_TABLE; SQL Server usa `SET SHOWPLAN_ALL ON`,
    que faz o servidor devolver o plano no lugar do resultado. Nos dois casos a
    transação é desfeita ao final e nada é gravado.

    Chamador trata as exceções: é por elas que a query inválida se anuncia.
    """
    with connect() as conn:
        cur = conn.cursor()
        try:
            if DB_TYPE == "sqlserver":
                # SHOWPLAN_ALL precisa ser o único comando do batch — o pymssql
                # manda um batch por execute(), então isso já está garantido.
                cur.execute("SET SHOWPLAN_ALL ON")
                try:
                    cur.execute(sql)
                    plano = _cursor_rows(cur)
                finally:
                    # Sem desligar, a conexão seguiria devolvendo plano em vez
                    # de dado — e ela volta para o processo, não é descartada.
                    cur.execute("SET SHOWPLAN_ALL OFF")
                # Reduz o SHOWPLAN_ALL às colunas equivalentes às do EXPLAIN
                # PLAN do Oracle — as demais (StmtText, Argument, OutputList)
                # são longas demais para uma tabela Markdown. Na linha do
                # comando em si o PhysicalOp vem nulo; `Type` (SELECT) é o que
                # o Oracle mostra ali como SELECT STATEMENT.
                rows = [
                    {
                        "operation": linha.get("physicalop") or linha.get("type"),
                        "options": linha.get("logicalop"),
                        "cost": linha.get("totalsubtreecost"),
                        "cardinality": linha.get("estimaterows"),
                    }
                    for linha in plano
                ]
            else:
                # Sem `SET TRANSACTION READ ONLY` aqui: o próprio EXPLAIN PLAN
                # grava na PLAN_TABLE e seria bloqueado com ORA-01456. O
                # rollback ao final desfaz tudo, e a allowlist do chamador já
                # garante que `sql` é somente leitura.
                cur.execute(
                    f"EXPLAIN PLAN SET STATEMENT_ID = '{PLAN_STATEMENT_ID}' FOR {sql}"
                )
                # STATEMENT_ID isola o plano desta chamada: com PLAN_TABLE
                # permanente e compartilhada, um SELECT sem filtro traria também
                # o plano dos outros.
                cur.execute(
                    f"""
                    SELECT OPERATION, OPTIONS, OBJECT_NAME, COST, CARDINALITY
                    FROM PLAN_TABLE
                    WHERE STATEMENT_ID = {_BIND['oracle'](1)}
                    ORDER BY ID
                    """,
                    [PLAN_STATEMENT_ID],
                )
                rows = _cursor_rows(cur)
        finally:
            cur.close()
        conn.rollback()
    return rows


def is_plan_unavailable(exc: Exception) -> bool:
    """
    True quando o plano falhou por ambiente (PLAN_TABLE ausente ou sem acesso),
    não por defeito da query — reprovar a query nesse caso seria veredito falso.
    Só existe no Oracle: o SHOWPLAN_ALL não depende de objeto nenhum.
    """
    return DB_TYPE == "oracle" and (is_missing_object(exc) or "ORA-02404" in str(exc))


# ---------------------------------------------------------------------------
# Agrupamento de módulos
# ---------------------------------------------------------------------------

# Tamanho do prefixo de módulo. A nomenclatura do Sankhya é `<PRX><MOD3><CTX>`:
# TGFCAB, TGFITE e TGFPAR são o módulo TGF; AD_XXX são as tabelas customizadas.
PREFIXO_MODULO = 3


def group_prefixes(table_names: list[str]) -> list[dict]:
    """
    Agrupa nomes de tabela pelo prefixo de 3 caracteres (TGFCAB → TGF).

    Feito em Python, não em SQL, porque o SQL Server não tem REGEXP_SUBSTR — e
    com um só caminho os dois bancos respondem exatamente a mesma coisa.

    O SQL original agrupava por `REGEXP_SUBSTR(TABLE_NAME, '^[A-Z]+')`, a
    sequência de letras inicial. Num nome todo de letras isso casa o nome
    inteiro: `TGFCAB` virava um grupo de uma tabela só e o `HAVING COUNT(*) > 1`
    o descartava. Sobrevivia só quem tem dígito ou underscore depois das letras
    — `WWV_*` do APEX, `TFPS_*` — e os módulos principais (TGF, TSI, TCS) não
    apareciam. Três caracteres é a convenção real de nomenclatura do Sankhya.

    Prefixo com uma tabela só continua sendo ruído e fica de fora, como no
    `HAVING` original. Nome curto demais ou que não começa por letra é ignorado.
    """
    contagem: dict[str, int] = {}
    for nome in table_names or []:
        nome = nome or ""
        if len(nome) >= PREFIXO_MODULO and nome[0].isalpha():
            prefixo = nome[:PREFIXO_MODULO].upper()
            contagem[prefixo] = contagem.get(prefixo, 0) + 1
    return [
        {"prefixo": p, "qtd_tabelas": n}
        for p, n in sorted(contagem.items(), key=lambda kv: (-kv[1], kv[0]))
        if n > 1
    ]
