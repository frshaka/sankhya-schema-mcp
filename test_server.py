r"""
Autoteste das funções puras do servidor MCP (não requer banco Oracle).

Execute:
    Windows: .\.venv\Scripts\python.exe test_server.py
    Linux:   .venv/bin/python test_server.py
"""

import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import server  # noqa: E402
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


def _fetch_com_banco_falso(total, limit):
    """Roda fetch_rows contra um cursor falso e devolve (linhas, truncado, cursor)."""
    cursor = _FakeCursor(total)
    original = server.get_pool
    server.get_pool = lambda: type("P", (), {"acquire": lambda _s: _FakeConn(cursor)})()
    try:
        rows, truncated = server.fetch_rows("SELECT 1 FROM DUAL", limit=limit)
    finally:
        server.get_pool = original
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


if __name__ == "__main__":
    testes = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for teste in testes:
        teste()
        print(f"[OK] {teste.__name__}")
    print(f"\n{len(testes)} teste(s) passaram.")
