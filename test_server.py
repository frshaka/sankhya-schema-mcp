r"""
Autoteste das funções puras do servidor MCP (não requer banco).

Execute:
    Windows: .\.venv\Scripts\python.exe test_server.py
    Linux:   .venv/bin/python test_server.py
"""

import sys
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import dialects  # noqa: E402
import server  # noqa: E402
from dialects import (  # noqa: E402
    BEGIN_READ_ONLY,
    QUERIES,
    group_prefixes,
    resolve_db_type,
    resolve_schema,
    schema_prefix,
)
from server import (  # noqa: E402
    assert_read_only_query,
    assert_safe_identifier,
    pick_owner,
    rows_to_markdown,
    select_columns,
    truncation_note,
    DEFAULT_ROW_LIMIT,
    SAMPLE_COLUMN_LIMIT,
)


def test_read_only_aceita_leitura():
    assert assert_read_only_query("SELECT 1 FROM DUAL") is None
    assert assert_read_only_query("  select nunota from tgfcab  ") is None
    assert assert_read_only_query("WITH x AS (SELECT 1 A FROM DUAL) SELECT * FROM x") is None
    assert assert_read_only_query("SELECT 1 FROM DUAL;") is None


def test_read_only_bloqueia_escrita():
    for sql in [
        "",
        "   ",
        "DELETE FROM TGFCAB",
        "UPDATE TGFCAB SET VLRNOTA = 0",
        "INSERT INTO TGFCAB (NUNOTA) VALUES (1)",
        "DROP TABLE TGFCAB",
        "BEGIN NULL; END;",
        "SELECT 1 FROM DUAL; DELETE FROM TGFCAB",
        "WITH FUNCTION f RETURN NUMBER IS BEGIN RETURN 1; END; SELECT f FROM DUAL",
        "-- SELECT 1\nDELETE FROM TGFCAB",
        "/* SELECT 1 */ DELETE FROM TGFCAB",
    ]:
        assert assert_read_only_query(sql) is not None, f"deveria bloquear: {sql!r}"


def test_identificador_seguro():
    for nome in ["TGFCAB", "AD_MINHA_TABELA", "SANKHYA.TGFCAB", "T$X#1"]:
        assert assert_safe_identifier(nome) is None, f"deveria aceitar: {nome!r}"

    for nome in [
        "",
        None,
        "TGFCAB WHERE 1=1",
        "DUAL UNION SELECT PASSWORD FROM TSIUSU",
        "TGFCAB; DELETE FROM TGFCAB",
        "tgfcab",  # resolve_table_name sempre entrega maiúsculas
    ]:
        assert assert_safe_identifier(nome) is not None, f"deveria bloquear: {nome!r}"


def test_markdown():
    assert rows_to_markdown([]) == "_Nenhum resultado encontrado._"
    md = rows_to_markdown([{"a": 1, "b": None}])
    assert md.splitlines() == ["| a | b |", "| --- | --- |", "| 1 |  |"]


def test_markdown_preserva_valores_falsy():
    # Só NULL pode virar célula vazia: zero é um valor, e quem lê a tabela
    # não tem como distinguir "0" apagado de "sem valor".
    md = rows_to_markdown([
        {"zero": 0, "falso": False, "decimal": Decimal("0.00"), "vazio": "", "nulo": None},
    ])
    assert md.splitlines()[-1] == "| 0 | False | 0.00 |  |  |"


def test_markdown_escapa_pipe():
    # Comentário de coluna do dicionário Sankhya pode conter `|`, que sem escape
    # cria colunas fantasma e desalinha a tabela inteira.
    md = rows_to_markdown([{"comentario": "Situação: A|I|C"}])
    assert md.splitlines()[-1] == r"| Situação: A\|I\|C |"


def test_owner_unico_por_tabela():
    # Com a tabela em vários schemas visíveis, vence o do usuário conectado.
    original = server.DB_CONFIG["user"]
    server.DB_CONFIG["user"] = "sankhya"
    try:
        assert pick_owner({"AUDIT", "SANKHYA", "TESTE"}) == "SANKHYA"
        # Sem o schema conectado entre eles, vence o primeiro em ordem alfabética.
        assert pick_owner({"TESTE", "AUDIT"}) == "AUDIT"
        assert pick_owner({"AUDIT"}) == "AUDIT"
    finally:
        server.DB_CONFIG["user"] = original


def test_aviso_de_truncamento():
    assert truncation_note(False, DEFAULT_ROW_LIMIT) == ""
    assert str(DEFAULT_ROW_LIMIT) in truncation_note(True, DEFAULT_ROW_LIMIT)


# --- Projeção de colunas da amostra (select_columns) ----------------------


def _linhas_largas(qtd_colunas=100, qtd_linhas=3):
    """Linhas no formato que fetch_rows devolve: chaves minúsculas, na ordem da tabela."""
    return [
        {f"col{i:03d}": f"v{linha}_{i}" for i in range(qtd_colunas)}
        for linha in range(qtd_linhas)
    ]


def test_projecao_corta_no_teto_e_informa_o_resto():
    linhas = _linhas_largas(qtd_colunas=600)
    projetadas, ausentes, cortadas = select_columns(linhas)
    assert len(projetadas) == len(linhas)  # corta coluna, nunca linha
    assert list(projetadas[0]) == [f"col{i:03d}" for i in range(SAMPLE_COLUMN_LIMIT)]
    assert ausentes == []
    assert cortadas == 600 - SAMPLE_COLUMN_LIMIT


def test_projecao_sem_teto_quando_tabela_e_estreita():
    projetadas, ausentes, cortadas = select_columns(_linhas_largas(qtd_colunas=3))
    assert len(projetadas[0]) == 3
    assert (ausentes, cortadas) == ([], 0)


def test_projecao_respeita_colunas_pedidas():
    linhas = _linhas_largas(qtd_colunas=600)
    projetadas, ausentes, cortadas = select_columns(linhas, "col005,col001")
    # Ordem de exibição é a que o usuário pediu, não a da tabela.
    assert list(projetadas[0]) == ["col005", "col001"]
    assert projetadas[0]["col005"] == "v0_5"
    # Pedido explícito não é cortado pelo teto, mesmo acima dele.
    assert (ausentes, cortadas) == ([], 0)
    acima_do_teto = ",".join(f"col{i:03d}" for i in range(SAMPLE_COLUMN_LIMIT + 10))
    projetadas, _, cortadas = select_columns(linhas, acima_do_teto)
    assert len(projetadas[0]) == SAMPLE_COLUMN_LIMIT + 10
    assert cortadas == 0


def test_projecao_e_case_insensitive_e_ignora_espacos():
    linhas = [{"nunota": 1, "codparc": 2, "vlrnota": 3.0}]
    projetadas, ausentes, _ = select_columns(linhas, " NUNOTA , VlrNota ")
    assert projetadas == [{"nunota": 1, "vlrnota": 3.0}]
    assert ausentes == []


def test_projecao_denuncia_coluna_inexistente():
    linhas = [{"nunota": 1, "codparc": 2}]
    projetadas, ausentes, _ = select_columns(linhas, "NUNOTA,NAOEXISTE")
    # A coluna válida sai; a inválida não é silenciada.
    assert projetadas == [{"nunota": 1}]
    assert ausentes == ["NAOEXISTE"]


def test_projecao_sem_nenhuma_coluna_valida_volta_vazia():
    linhas = [{"nunota": 1, "codparc": 2}]
    projetadas, ausentes, _ = select_columns(linhas, "FOO, BAR")
    # Linhas vazias sinalizam ao chamador que não há tabela a exibir, só erro.
    assert projetadas == []
    assert ausentes == ["FOO", "BAR"]


def test_projecao_sem_linhas_nao_quebra():
    assert select_columns([], "NUNOTA") == ([], [], 0)


# --- Dublês de banco: fetch_rows sem Oracle -------------------------------


class _FakeCursor:
    def __init__(self, total):
        self._total = total
        self.description = [("N",)]
        self.executado = []
        self.fetchall_calls = 0
        self.fetchmany_args = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params=None):
        self.executado.append(sql)

    def fetchall(self):
        self.fetchall_calls += 1
        return [(i,) for i in range(self._total)]

    def fetchmany(self, n):
        self.fetchmany_args.append(n)
        return [(i,) for i in range(min(n, self._total))]


class _FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def cursor(self):
        return self._cursor

    def rollback(self):
        pass


def _fetch_com_banco_falso(total, limit, db_type="oracle"):
    """Roda fetch_rows contra um cursor falso e devolve (linhas, truncado, cursor)."""
    cursor = _FakeCursor(total)

    @contextmanager
    def _connect_falso():
        yield _FakeConn(cursor)

    original_connect, original_tipo = server.connect, server.DB_TYPE
    server.connect, server.DB_TYPE = _connect_falso, db_type
    try:
        rows, truncated = server.fetch_rows("SELECT 1 FROM DUAL", limit=limit)
    finally:
        server.connect, server.DB_TYPE = original_connect, original_tipo
    return rows, truncated, cursor


def test_sem_teto_traz_a_tabela_inteira():
    # Uma tabela Oracle chega a 1000 colunas: describe_table nao pode cortar nenhuma.
    rows, truncated, cursor = _fetch_com_banco_falso(total=1000, limit=None)
    assert len(rows) == 1000
    assert truncated is False
    assert cursor.fetchall_calls == 1
    assert cursor.fetchmany_args == []


def test_com_teto_corta_e_sinaliza():
    rows, truncated, cursor = _fetch_com_banco_falso(total=1500, limit=DEFAULT_ROW_LIMIT)
    assert len(rows) == DEFAULT_ROW_LIMIT
    assert truncated is True
    # Busca limit+1 para detectar o corte sem um COUNT extra.
    assert cursor.fetchmany_args == [DEFAULT_ROW_LIMIT + 1]


def test_resultado_exato_no_teto_nao_e_truncado():
    rows, truncated, _ = _fetch_com_banco_falso(total=DEFAULT_ROW_LIMIT, limit=DEFAULT_ROW_LIMIT)
    assert len(rows) == DEFAULT_ROW_LIMIT
    assert truncated is False


def test_limite_zero_nao_esvazia_resultado():
    # limit=0 devolvia ([], truncado=True): query com linhas anunciada como vazia.
    rows, truncated, _ = _fetch_com_banco_falso(total=3, limit=0)
    assert len(rows) == 1
    assert truncated is True


def test_limite_negativo_nao_corta_o_fim():
    # rows[:-5] descartaria o fim do resultado em silêncio.
    rows, truncated, _ = _fetch_com_banco_falso(total=3, limit=-5)
    assert len(rows) == 1
    assert truncated is True


def test_aviso_de_truncamento_usa_o_limite_padrao():
    assert truncation_note(True) == truncation_note(True, DEFAULT_ROW_LIMIT)


def test_sessao_sempre_read_only():
    _, _, cursor = _fetch_com_banco_falso(total=5, limit=None)
    assert "SET TRANSACTION READ ONLY" in cursor.executado


def test_sessao_sqlserver_abre_transacao_explicita():
    # O SQL Server não tem READ ONLY de sessão: a transação explícita é o mais
    # próximo, e sem ela uma escrita que escapasse da validação ficaria gravada.
    _, _, cursor = _fetch_com_banco_falso(total=5, limit=None, db_type="sqlserver")
    assert "BEGIN TRANSACTION" in cursor.executado
    assert "SET TRANSACTION READ ONLY" not in cursor.executado


# --- Dialetos --------------------------------------------------------------


@contextmanager
def _dialeto(tipo):
    """Ativa um dialeto para o trecho, e devolve o anterior ao sair."""
    original = dialects.DB_TYPE
    dialects.DB_TYPE = tipo
    try:
        yield
    finally:
        dialects.DB_TYPE = original


def test_selecao_de_dialeto_por_env():
    # Ausente/vazio cai em oracle: instalação existente não pode passar a exigir
    # configuração nova para continuar funcionando.
    assert resolve_db_type(None) == "oracle"
    assert resolve_db_type("") == "oracle"
    assert resolve_db_type("   ") == "oracle"
    assert resolve_db_type("oracle") == "oracle"
    assert resolve_db_type("sqlserver") == "sqlserver"
    # Tolerante a maiúsculas e espaços: o valor vem digitado à mão no .env.
    assert resolve_db_type(" SqlServer ") == "sqlserver"


def test_dialeto_invalido_falha_alto():
    # Conectar no banco errado é pior que não subir.
    for valor in ["postgres", "mssql", "sql server"]:
        try:
            resolve_db_type(valor)
        except ValueError:
            continue
        raise AssertionError(f"deveria recusar: {valor!r}")


def test_dialetos_expoem_o_mesmo_conjunto_de_queries():
    # Query que exista só de um lado vira AttributeError em produção, no banco
    # que ninguém testou.
    assert set(QUERIES["oracle"]) == set(QUERIES["sqlserver"])


def test_cada_dialeto_usa_o_catalogo_do_seu_banco():
    assert "ALL_TAB_COLUMNS" in QUERIES["oracle"]["columns"]
    assert "INFORMATION_SCHEMA.COLUMNS" in QUERIES["sqlserver"]["columns"]
    assert "ALL_INDEXES" in QUERIES["oracle"]["indexes"]
    assert "sys.indexes" in QUERIES["sqlserver"]["indexes"]
    assert "ALL_CONSTRAINTS" in QUERIES["oracle"]["foreign_keys"]
    assert "sys.foreign_keys" in QUERIES["sqlserver"]["foreign_keys"]
    # TDDINS é tabela da aplicação: idêntica nos dois, não duplicada.
    for nome in ["resolve_table", "instances_by_table", "search_entities"]:
        assert "TDDINS" in QUERIES["oracle"][nome]
        assert QUERIES["oracle"][nome] == QUERIES["sqlserver"][nome]


def test_placeholder_de_bind_por_dialeto():
    with _dialeto("oracle"):
        assert ":1" in dialects.query("columns")
        assert "%s" not in dialects.query("columns")
    with _dialeto("sqlserver"):
        assert "%s" in dialects.query("columns")
        assert ":1" not in dialects.query("columns")


def test_placeholder_resolvido_tambem_no_filtro_opcional():
    # search_columns monta o filtro sem saber qual banco está ativo.
    with _dialeto("oracle"):
        sql = dialects.query("columns_search", filtro="AND c.TABLE_NAME LIKE {p2}")
        assert "LIKE :2" in sql
    with _dialeto("sqlserver"):
        sql = dialects.query("columns_search", filtro="AND c.TABLE_NAME LIKE {p2}")
        assert sql.count("%s") == 2


def test_amostra_usa_o_limitador_de_linhas_do_banco():
    with _dialeto("oracle"):
        assert dialects.query("table_sample", tabela="TGFCAB") == (
            "SELECT * FROM TGFCAB WHERE ROWNUM <= :1"
        )
    with _dialeto("sqlserver"):
        assert dialects.query("table_sample", tabela="TGFCAB") == (
            "SELECT TOP (%s) * FROM TGFCAB"
        )


def test_search_entities_tem_um_bind_por_ocorrencia():
    # `fetch_rows` manda dois parâmetros: o pymssql não reaproveita bind
    # posicional como o Oracle faz com `:1` repetido.
    with _dialeto("sqlserver"):
        assert dialects.query("search_entities", filtro="").count("%s") == 2
    with _dialeto("oracle"):
        sql = dialects.query("search_entities", filtro="")
        assert ":1" in sql and ":2" in sql


def test_begin_read_only_por_dialeto():
    assert BEGIN_READ_ONLY["oracle"] == "SET TRANSACTION READ ONLY"
    assert BEGIN_READ_ONLY["sqlserver"] == "BEGIN TRANSACTION"


# --- Agrupamento de módulos (list_modules) ---------------------------------


def test_agrupa_prefixo_de_tabela():
    # Contrato NOVO: prefixo de 3 caracteres, a convenção de nomenclatura do
    # Sankhya. O SQL antigo agrupava pela sequência de letras inicial, que em
    # `TGFCAB` casa o nome inteiro — então TGF, TSI e TCS, os módulos que a tool
    # existe para mostrar, caíam no HAVING e sumiam da saída.
    modulos = group_prefixes(["TGFCAB", "TGFITE", "TGFPAR", "TSIUSU", "TSIEMP"])
    assert modulos == [
        {"prefixo": "TGF", "qtd_tabelas": 3},
        {"prefixo": "TSI", "qtd_tabelas": 2},
    ]


def test_duas_tabelas_do_mesmo_prefixo_agrupam():
    assert group_prefixes(["TGFCAB", "TGFITE"]) == [{"prefixo": "TGF", "qtd_tabelas": 2}]


def test_agrupamento_descarta_prefixo_com_uma_tabela_so():
    # Mesma regra do HAVING COUNT(*) > 1 do SQL original: prefixo único é ruído.
    assert group_prefixes(["TGFCAB", "XYZUNICA"]) == []
    assert group_prefixes([]) == []


def test_agrupamento_com_nome_menor_que_o_prefixo_nao_quebra():
    # Nome curto demais não tem prefixo de módulo: fica de fora sem estourar.
    assert group_prefixes(["AB", "X", "", None, "TGFCAB", "TGFITE"]) == [
        {"prefixo": "TGF", "qtd_tabelas": 2},
    ]


def test_agrupamento_ignora_nome_sem_prefixo_alfabetico():
    assert group_prefixes(["123456", "1234", "TGFCAB", "TGFITE"]) == [
        {"prefixo": "TGF", "qtd_tabelas": 2},
    ]


def test_agrupamento_reconhece_tabela_customizada():
    # Customizadas do Sankhya são AD_*: o prefixo de 3 pega o underscore junto.
    assert group_prefixes(["AD_PEDIDO", "AD_CLIENTE"]) == [
        {"prefixo": "AD_", "qtd_tabelas": 2},
    ]


def test_agrupamento_desempata_por_ordem_alfabetica():
    # Empate na contagem precisa de ordem estável, senão a saída muda a cada run.
    assert group_prefixes(["ZZZA", "ZZZB", "AAAA", "AAAB"]) == [
        {"prefixo": "AAA", "qtd_tabelas": 2},
        {"prefixo": "ZZZ", "qtd_tabelas": 2},
    ]


def test_agrupamento_normaliza_caixa_do_prefixo():
    # No SQL Server um nome minúsculo é plausível e ficaria num grupo separado.
    assert group_prefixes(["tgfcab", "TGFITE"]) == [{"prefixo": "TGF", "qtd_tabelas": 2}]


# --- Allowlist: SELECT ... INTO e literais --------------------------------


def test_bloqueia_select_into():
    # `SELECT ... INTO nova FROM x` começa com SELECT e passaria a checagem de
    # prefixo, mas no SQL Server cria tabela — escrita, e lá não existe READ
    # ONLY de sessão para recusar. Bloqueado nos dois bancos.
    for sql in [
        "SELECT * INTO nova FROM TGFCAB",
        "select nunota into #tmp from TGFCAB",
        "WITH x AS (SELECT 1 c FROM T) SELECT * INTO t FROM x",
        "SELECT * /* disfarce */ INTO nova FROM TGFCAB",
    ]:
        assert assert_read_only_query(sql) is not None, sql


def test_literal_de_texto_nao_reprova_query_valida():
    # `;` e `INTO` dentro de aspas são dado, não comando. O caso do `;` era um
    # falso positivo que já existia antes do bloqueio de INTO.
    for sql in [
        "SELECT 'entrada into saida' AS obs FROM DUAL",
        "SELECT 'a;b' FROM DUAL",
        "SELECT 'aspa '' dobrada into x' FROM DUAL",
    ]:
        assert assert_read_only_query(sql) is None, sql


def test_bloqueio_de_into_nao_pega_palavra_composta():
    # Só a palavra inteira: coluna chamada INTOLERANCIA ou POINTO não é INTO.
    assert assert_read_only_query("SELECT INTOLERANCIA FROM T") is None
    assert assert_read_only_query("SELECT PONTO_INTOCADO FROM T") is None


# --- Schema das tabelas (SANKHYA_DB_SCHEMA) -------------------------------


def _com_schema(valor):
    """Roda schema_prefix() com SANKHYA_DB_SCHEMA temporariamente redefinido."""
    original = dialects.DB_CONFIG["schema"]
    dialects.DB_CONFIG["schema"] = valor
    try:
        return schema_prefix()
    finally:
        dialects.DB_CONFIG["schema"] = original


def test_schema_ausente_nao_qualifica_nada():
    # Sem a variável, nome de tabela sai cru: comportamento de sempre.
    assert resolve_schema(None) is None
    assert resolve_schema("") is None
    assert resolve_schema("   ") is None
    assert _com_schema(None) == ""


def test_schema_normalizado_para_maiusculas():
    assert resolve_schema(" sankhya ") == "SANKHYA"
    assert _com_schema("SANKHYA") == "SANKHYA."


def test_schema_invalido_falha_alto():
    # O nome é interpolado no texto da query e do ALTER SESSION — nenhum dos
    # dois aceita bind para identificador —, então precisa ser recusado antes.
    for ruim in ["SANKHYA; DROP TABLE X", "SANKHYA TESTE", "SANKHYA--", "DONO.TABELA", "1SCHEMA"]:
        try:
            resolve_schema(ruim)
        except ValueError:
            continue
        raise AssertionError(f"schema inválido aceito: {ruim!r}")


def test_schema_qualifica_amostra_e_tddins_nos_dois_bancos():
    # As quatro referências não qualificadas: a amostra e as três do TDDINS.
    original = dialects.DB_CONFIG["schema"]
    dialects.DB_CONFIG["schema"] = "SANKHYA"
    try:
        with _dialeto("oracle"):
            assert dialects.query("table_sample", tabela="TGFCAB") == (
                "SELECT * FROM SANKHYA.TGFCAB WHERE ROWNUM <= :1"
            )
            for nome in ["resolve_table", "instances_by_table", "search_entities"]:
                assert "FROM SANKHYA.TDDINS" in dialects.query(nome, filtro="")
        with _dialeto("sqlserver"):
            assert dialects.query("table_sample", tabela="TGFCAB") == (
                "SELECT TOP (%s) * FROM SANKHYA.TGFCAB"
            )
            assert "FROM SANKHYA.TDDINS" in dialects.query("resolve_table")
    finally:
        dialects.DB_CONFIG["schema"] = original


def test_alter_session_so_no_oracle():
    # No SQL Server o schema padrão vem do mapeamento do login: persistente e
    # com privilégio, não é papel deste servidor mexer. Lá vale o qualificador.
    cursor = _FakeCursor(0)
    original = dialects.DB_CONFIG["schema"]
    dialects.DB_CONFIG["schema"] = "SANKHYA"
    try:
        dialects._set_current_schema(_FakeConn(cursor), None)
    finally:
        dialects.DB_CONFIG["schema"] = original
    assert cursor.executado == ["ALTER SESSION SET CURRENT_SCHEMA = SANKHYA"]


# --- Nome que o dicionário não reconheceu ---------------------------------


def test_nome_resolvido_nao_gera_aviso():
    # Resolveu via TDDINS: o vazio é real, cada tool usa a própria mensagem.
    assert server.unresolved_name_note("CabecalhoNota", [{"nometab": "TGFCAB"}]) is None


def test_nome_nao_resolvido_aponta_search_entities():
    # "Nenhum índice encontrado" se lê como "a tabela não tem índice"; o que
    # houve foi um EntityName que o dicionário não reconhece.
    aviso = server.unresolved_name_note("CabeçalhoNota", [])
    assert "search_entities(\"CabeçalhoNota\")" in aviso
    assert "TDDINS" in aviso


def test_exemplos_das_docstrings_usam_entityname_sem_acento():
    # O EntityName de TGFCAB é `CabecalhoNota`, sem cedilha — `CabeçalhoNota`
    # não existe no dicionário. Docstring é o que o cliente MCP mostra ao
    # modelo: exemplo errado vira chamada errada.
    for tool in (server.describe_table, server.get_indexes, server.search_entities):
        doc = tool.__doc__ or ""
        assert "CabeçalhoNota" not in doc, tool.__name__
        assert "CabecalhoNota" in doc, tool.__name__


if __name__ == "__main__":
    testes = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for teste in testes:
        teste()
        print(f"[OK] {teste.__name__}")
    print(f"\n{len(testes)} teste(s) passaram.")
