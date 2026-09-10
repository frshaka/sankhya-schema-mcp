"""
Sankhya Schema MCP Server
Explora o schema do banco Sankhya — Oracle (via oracledb em modo thick com
Oracle Instant Client 21c) ou SQL Server (via pymssql).

O banco é escolhido por `SANKHYA_DB_TYPE` (`oracle` por padrão). Tudo que muda
de um banco para o outro — queries de catálogo, conexão, transação de leitura,
plano de execução — vive em `dialects.py`.
"""

import re
from typing import Optional

from mcp.server.fastmcp import FastMCP

from dialects import (
    BEGIN_READ_ONLY,
    DB_CONFIG,
    DB_TYPE,
    connect,
    explain_plan,
    group_prefixes,
    is_missing_object,
    is_plan_unavailable,
    query,
)
from updates import (
    PROJECT_ROOT,
    changelog_entries,
    format_version,
    latest_version,
    parse_version,
    update_notice,
)
from version import __version__

# Teto para buscas abertas (search_*), cujo resultado cresce com o schema inteiro
# e não com uma tabela específica. Metadados de uma única tabela usam limit=None.
DEFAULT_ROW_LIMIT = 200
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

    A transação é aberta em modo de leitura e sempre desfeita ao final. No Oracle
    isso significa `SET TRANSACTION READ ONLY`, e o próprio banco recusa DML que
    escape da validação de aplicação (ORA-01456). No SQL Server não existe
    equivalente: a transação explícita desfaz uma escrita, mas não a impede —
    ver a seção Segurança do README.
    """
    # `limit` chega do cliente MCP sem validação: 0 devolveria lista vazia com
    # truncado=True (resultado com linhas anunciado como vazio) e um negativo
    # cortaria o fim do resultado em `rows[:limit]`.
    if limit is not None:
        limit = max(1, limit)
    with connect() as conn:
        # Garante início de transação limpo antes de marcá-la como somente leitura
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute(BEGIN_READ_ONLY[DB_TYPE])
            cur.execute(sql, params or None)
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


# Tipos cujo tamanho em caracteres é informação útil. Fora deles o número é
# ruído: no Oracle um DATE tem DATA_LENGTH 7 e um NUMBER tem 22, nenhum dos
# dois diz nada a quem vai escrever a query.
_TIPOS_TEXTO = ("CHAR", "TEXT")
_TIPOS_DECIMAIS = ("NUMBER", "NUMERIC", "DECIMAL")


def compact_type(col: dict) -> str:
    """
    Colapsa tipo, tamanho, precisão e escala numa célula só (`NUMBER(15,2)`).

    Eram quatro colunas na saída, três delas vazias na maioria das linhas.
    Junta-las abre espaço para a descrição e as opções sem inchar a tabela.

    Vale nos dois bancos: `dialects.py` já apelida CHARACTER_MAXIMUM_LENGTH e
    NUMERIC_PRECISION do SQL Server com os nomes do Oracle. `-1` é o
    `varchar(max)` do SQL Server, que não tem equivalente Oracle.
    """
    tipo = (col.get("data_type") or "").strip()
    if not tipo:
        return ""
    nome = tipo.upper()
    tamanho, precisao, escala = (
        col.get("data_length"),
        col.get("data_precision"),
        col.get("data_scale"),
    )
    if any(marca in nome for marca in _TIPOS_TEXTO):
        if tamanho == -1:
            return f"{tipo}(max)"
        return f"{tipo}({tamanho})" if tamanho else tipo
    if nome in _TIPOS_DECIMAIS and precisao:
        return f"{tipo}({precisao},{escala})" if escala else f"{tipo}({precisao})"
    return tipo


def is_nullable(valor) -> str:
    """
    Normaliza o indicador de nulo: `Y`/`N` no Oracle, `YES`/`NO` no SQL Server.
    Sem isso a mesma tabela se descreve diferente conforme o banco.
    """
    return "S" if str(valor or "").strip().upper().startswith("Y") else "N"


def merge_field_dict(
    cols: list[dict], descricoes: list[dict], opcoes: list[dict]
) -> list[dict]:
    """
    Junta as colunas do catálogo com a descrição (TDDCAM) e o domínio (TDDOPC).

    A junção é em Python e não em SQL porque agregar as opções numa célula
    exigiria LISTAGG no Oracle e STRING_AGG no SQL Server — dois caminhos de
    código para o mesmo resultado. Mesma decisão de `group_prefixes`.

    As opções vêm inline, não como contagem. Um consumidor que lê apenas
    "23 opções" ao lado de TIPMOV precisa decidir buscá-las; se não buscar,
    escreve `TIPMOV = 'V'` (Venda) onde o pedido de venda é `P`. Valor válido,
    resultado errado, nenhum erro levantado. Com o par valor↔rótulo na mesma
    resposta não sobra o que adivinhar — é o motivo de esta tool existir.

    Descrição do dicionário tem precedência sobre o comentário de coluna do
    catálogo, que na base Sankhya vem vazio; a lista de dicionário ausente
    apenas deixa a coluna em branco.
    """
    por_campo = {r["nomecampo"]: r.get("descrcampo") for r in descricoes or []}
    dominios: dict[str, list[str]] = {}
    for r in opcoes or []:
        dominios.setdefault(r["nomecampo"], []).append(f"{r['valor']}={r['opcao']}")

    linhas = []
    for col in cols:
        nome = col["column_name"]
        linhas.append(
            {
                "campo": nome,
                "tipo": compact_type(col),
                "nulo": is_nullable(col.get("nullable")),
                "descricao": por_campo.get(nome) or col.get("comments") or "",
                "opcoes": "; ".join(dominios.get(nome, [])),
            }
        )
    return linhas


def decorate_options(rows: list[dict], opcoes: list[dict]) -> list[dict]:
    """
    Anexa o rótulo do dicionário ao valor de coluna enumerada: `L` → `L (Liberada)`.

    Amostra de tabela Sankhya é uma parede de códigos de uma letra — `tipmov`,
    `statusnota`, `ativo` — que não se lê sem consultar o domínio campo a campo.

    Só decora quando existe rótulo para aquele valor. Valor gravado fora do
    domínio declarado fica cru de propósito: é assim que ele se denuncia, em vez
    de passar por código conhecido. (Medido: TGFCAB.TIPMOV tem `Z` em 23 de 139
    linhas, e `Z` não está em TDDOPC.)

    O casamento é por nome de coluna em minúsculas — as chaves vêm assim de
    `fetch_rows` e o dicionário guarda em maiúsculas — e por valor convertido a
    texto, porque TDDOPC.VALOR é sempre string e a coluna pode ser numérica.
    """
    if not rows or not opcoes:
        return rows

    dominios: dict[str, dict[str, str]] = {}
    for r in opcoes:
        campo = (r.get("nomecampo") or "").lower()
        dominios.setdefault(campo, {})[str(r.get("valor")).strip()] = r.get("opcao")

    decoradas = []
    for row in rows:
        nova = {}
        for coluna, valor in row.items():
            rotulo = (
                dominios.get(coluna, {}).get(str(valor).strip())
                if valor is not None
                else None
            )
            # Sem rótulo o valor volta intacto — inclusive 0, False e Decimal,
            # que não podem virar texto por causa de uma decoração.
            nova[coluna] = f"{valor} ({rotulo})" if rotulo else valor
        decoradas.append(nova)
    return decoradas


def merge_table_descriptions(rows: list[dict], descricoes: list[dict]) -> list[dict]:
    """
    Troca a coluna `comments` do catálogo pelo verbete do dicionário (TDDTAB).

    `search_tables` é a primeira tool do fluxo e devolvia uma coluna vazia:
    nenhuma tabela da base Sankhya tem comentário de catálogo. Com o verbete,
    `TGFCAB` deixa de ser só um nome e vira "Entrada e Saída de Produto".

    Tabela fora do dicionário (31% do catálogo — temporárias, views de apoio)
    cai no comentário do catálogo e, faltando esse, fica em branco.
    """
    por_tabela = {r["nometab"]: r.get("descrtab") for r in descricoes or []}
    return [
        {
            "tabela": r["table_name"],
            "linhas": r.get("num_rows"),
            "descricao": por_tabela.get(r["table_name"]) or r.get("comments") or "",
        }
        for r in rows
    ]


def merge_column_descriptions(rows: list[dict], descricoes: list[dict]) -> list[dict]:
    """
    Mesma troca do `merge_table_descriptions`, para `search_columns`.

    A chave é o par tabela+campo, não o campo sozinho: o mesmo nome tem
    descrição diferente conforme a tabela, do mesmo jeito que tem domínio
    diferente (ver `merge_field_dict`).
    """
    por_par = {
        (r["nometab"], r["nomecampo"]): r.get("descrcampo") for r in descricoes or []
    }
    return [
        {
            "tabela": r["table_name"],
            "campo": r["column_name"],
            "tipo": r.get("data_type"),
            "nulo": is_nullable(r.get("nullable")),
            "descricao": por_par.get((r["table_name"], r["column_name"]))
            or r.get("comments")
            or "",
        }
        for r in rows
    ]


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

    Vale igual nos dois bancos — o OWNER do Oracle é o TABLE_SCHEMA do SQL
    Server, e na base `jiva` da Sankhya ele também é `SANKHYA`, convivendo com
    um punhado de tabelas em `dbo`.
    """
    conectado = (DB_CONFIG["user"] or "").upper()
    return conectado if conectado in owners else sorted(owners)[0]


def dictionary_rows(nome_query: str, *params, **fmt) -> list[dict]:
    """
    Consulta o dicionário Sankhya devolvendo lista vazia quando ele não existe
    no schema conectado.

    O enriquecimento vindo de TDDINS/TDDCAM/TDDOPC/TDDLIG é opcional por
    definição: uma base sem o dicionário ainda descreve colunas pelo catálogo.
    Erro que não seja "objeto não existe" sobe — falha de permissão ou de rede
    não pode virar resposta incompleta silenciosa.
    """
    try:
        return execute_query(query(nome_query, **fmt), list(params), limit=None)
    except Exception as exc:
        if is_missing_object(exc):
            return []
        raise


def resolve_table_name(name: str) -> tuple[str, list[dict]]:
    """
    Resolve EntityName (NOMEINSTANCIA) para nome de tabela via TDDINS.
    Retorna (table_name, entity_rows).
    Se não encontrar em TDDINS, devolve o nome original em maiúsculas e lista vazia.

    Enriquecimento opcional: quando o dicionário Sankhya (TDDINS) não existe no
    schema conectado, degrada silenciosamente e devolve o nome cru, para não
    inviabilizar quem só quer descrever colunas de uma tabela qualquer.
    """
    rows = dictionary_rows("resolve_table", name)
    if rows:
        # O banco é case-insensitive para identificador sem aspas, mas
        # `assert_safe_identifier` só aceita maiúsculas: sem o .upper() um
        # NOMETAB minúsculo no TDDINS reprovaria uma tabela válida.
        return rows[0]["nometab"].upper(), rows
    return name.upper(), []


def unresolved_name_note(table_name: str, entity_rows: list[dict]) -> Optional[str]:
    """
    Mensagem para quando a consulta não devolveu nada e o nome também não veio
    do dicionário. Retorna None quando o nome resolveu (aí o vazio é real).

    Sem isso, um EntityName errado devolve "Nenhum índice encontrado" ou
    "Tabela não encontrada ou sem colunas" — respostas que se leem como "essa
    tabela não tem índice" e "essa tabela não existe", quando o que houve foi
    um nome que o dicionário não reconheceu.
    """
    if entity_rows:
        return None
    return (
        f"Nada encontrado para `{table_name}`, e o nome não corresponde a nenhum "
        f'EntityName ativo no dicionário (TDDINS). Use `search_entities("{table_name}")` '
        "para descobrir o nome correto."
    )


def assert_read_only_query(sql: str) -> Optional[str]:
    """
    Valida que `sql` é uma única consulta de leitura (SELECT ou WITH ... SELECT).
    Retorna a mensagem de erro se reprovar, ou None se aprovar.

    Usa allowlist (mais seguro que blocklist):
    - remove comentários (-- de linha e /* de bloco */) para impedir disfarce;
    - exige que o comando comece com SELECT ou WITH;
    - rejeita múltiplos comandos (;) e PL/SQL inline (WITH FUNCTION/PROCEDURE),
      que poderiam contornar a transação READ ONLY via transação autônoma;
    - rejeita `INTO`, porque `SELECT ... INTO nova FROM x` começa com SELECT,
      passa a checagem de prefixo e **cria tabela** no SQL Server. É escrita, e
      lá não existe READ ONLY de sessão para recusá-la. Bloqueado nos dois
      bancos: no Oracle, `INTO` em SQL puro não é sintaxe válida, então o
      bloqueio não custa nenhuma query legítima.

    Literais de texto são removidos antes das checagens, para que um `;` ou um
    `INTO` dentro de aspas não reprove uma query legítima.
    """
    no_block = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    no_comments = re.sub(r"--[^\n]*", " ", no_block)
    # Literal de texto vira '' antes das checagens: `;` e `INTO` dentro de aspas
    # são dado, não comando. Aspa simples dobrada é o escape nos dois bancos.
    no_literals = re.sub(r"'(?:[^']|'')*'", "''", no_comments)
    core = no_literals.strip().rstrip(";").strip()

    if not core:
        return "Query vazia."
    if ";" in core:
        return "Múltiplos comandos não são permitidos (apenas um SELECT por chamada)."

    upper = core.upper()
    if not re.match(r"^(SELECT|WITH)\b", upper):
        return "Apenas comandos SELECT (ou WITH ... SELECT) são permitidos."
    if re.match(r"^WITH\s+(FUNCTION|PROCEDURE)\b", upper):
        return "WITH FUNCTION/PROCEDURE não é permitido."
    if re.search(r"\bINTO\b", upper):
        return (
            "`SELECT ... INTO` não é permitido: no SQL Server ele cria tabela, "
            "que é escrita disfarçada de leitura."
        )

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

# Consulta de atualização no boot. É o único canal que alcança o usuário sem
# depender de alguém lembrar de perguntar: uma tool só é chamada se o cliente
# decidir chamá-la, e ninguém pede update check espontaneamente.
#
# Custo: uma vez por dia (cache de 24h) o start espera até 2s pela rede. Falha
# devolve None e o servidor sobe igual — ver `updates.py`.
_AVISO_UPDATE = update_notice()

mcp = FastMCP(
    name="sankhya-schema",
    instructions=(
        f"Servidor de exploração do schema do banco do Sankhya ERP "
        f"(Oracle ou SQL Server, conforme SANKHYA_DB_TYPE). Versão {__version__}.\n\n"
        + (f"⚠️ ATUALIZAÇÃO DISPONÍVEL: {_AVISO_UPDATE}\n\n" if _AVISO_UPDATE else "")
        +
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
        "LITERAIS EM WHERE — REGRA ABSOLUTA:\n"
        "Antes de escrever qualquer filtro com valor literal (`WHERE TIPMOV = 'P'`, "
        "`STATUSNOTA = 'L'`, `ATIVO = 'S'`), chame describe_table na tabela e use "
        "exatamente um dos valores listados na coluna `opcoes` daquele campo. "
        "Os códigos do Sankhya são de uma letra e enganosamente parecidos: em "
        "TGFCAB.TIPMOV, `V` é Venda e `P` é Pedido de venda; escolher pelo nome do "
        "campo ou pelo português do pedido do usuário devolve o documento errado "
        "sem levantar erro de SQL. O mesmo campo tem domínio DIFERENTE em tabelas "
        "diferentes (TIPMOV existe em 17 tabelas), então consulte a tabela que a "
        "sua query realmente usa. Se o campo não estiver em `opcoes`, ele não é "
        "enumerado e o valor vem do dado.\n"
        "A lista de `opcoes` é o que o dicionário declara, e NÃO garante esgotar "
        "o que está gravado: há base com valor em uso fora da lista. Para filtro "
        "por igualdade, use a lista. Para filtro exaustivo (`IN`, `NOT IN`) ou "
        "para agrupar por esse campo, confirme antes com `table_sample` ou um "
        "`SELECT campo, COUNT(*) ... GROUP BY campo`.\n\n"
        "PROIBIÇÕES:\n"
        "- Só delegue tarefas que dependem deste MCP para subagents cuja definição inclua "
        "as tools `mcp__sankhya-schema__*`. Na dúvida, resolva no agente principal.\n"
        "- NUNCA tente conexão direta ao banco.\n"
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
    Retorna todas as colunas de uma tabela Sankhya com a descrição em português
    do dicionário e, para os campos enumerados, TODOS os valores aceitos com o
    respectivo rótulo (ex.: TIPMOV → `P=Pedido de venda; V=Venda; C=Compra`).
    Aceita tanto o nome da tabela no banco quanto o EntityName (NOMEINSTANCIA).

    Chame esta tool ANTES de escrever qualquer WHERE com literal: os códigos do
    Sankhya não são adivinháveis pelo nome do campo e vários são parecidos entre
    si. Em TIPMOV, `V` (Venda) e `P` (Pedido de venda) são ambos válidos — usar
    um pelo outro devolve o documento errado, sem nenhum erro de SQL.

    Exemplos:
      describe_table("TGFCAB")
      describe_table("CabecalhoNota")
    """
    resolved, entity_rows = resolve_table_name(table_name)

    # limit=None: toda coluna da tabela precisa aparecer, sem exceção.
    rows = execute_query(query("columns"), [resolved], limit=None)
    if not rows:
        return unresolved_name_note(table_name, entity_rows) or (
            f"Tabela `{resolved}` não encontrada ou sem colunas."
        )

    # A mesma tabela pode existir em vários schemas visíveis. Sem fixar um owner,
    # as colunas viriam duplicadas e o total no rodapé seria falso. Preferimos o
    # schema do usuário conectado; senão, o primeiro em ordem alfabética.
    owners = {r["owner"] for r in rows}
    owner = pick_owner(owners)
    rows = [r for r in rows if r["owner"] == owner]

    header = f"## {resolved}"
    if len(owners) > 1:
        outros = ", ".join(f"`{o}`" for o in sorted(owners) if o != owner)
        header += (
            f"\n**Schema:** `{owner}` — atenção: esta tabela também existe em {outros}."
        )
    if entity_rows:
        e = entity_rows[0]
        header += f"\n**EntityName:** `{e['nomeinstancia']}` — {e['descrinstancia']}"

    campos = merge_field_dict(
        rows,
        dictionary_rows("field_dict", resolved),
        dictionary_rows("field_options", resolved),
    )
    enumerados = sum(1 for c in campos if c["opcoes"])
    rodape = f"_{len(campos)} coluna(s)"
    if enumerados:
        # "domínio fechado" seria mentira: o dicionário declara o que a
        # aplicação oferece, não esgota o que está gravado. Na base medida,
        # TGFCAB.TIPMOV tem `Z` em 23 de 139 linhas sem estar em TDDOPC — quem
        # montasse um `IN (...)` com a lista declarada perderia essas linhas em
        # silêncio, que é justamente o erro que estas opções vêm evitar.
        rodape += (
            f", {enumerados} com valores declarados em `opcoes` — use esses "
            "valores em vez de deduzir pelo nome do campo, e confirme com "
            "`table_sample` antes de montar filtro exaustivo (`IN`, `NOT IN`), "
            "porque o dado pode conter valor fora da lista"
        )
    rodape += "._"

    result = f"{header}\n\n{rows_to_markdown(campos)}\n\n{rodape}"

    inst_rows = dictionary_rows("instances_by_table", resolved)
    if inst_rows:
        result += f"\n\n## Instâncias (EntityNames) — {resolved}\n\n{rows_to_markdown(inst_rows)}"

    return result


@mcp.tool()
def search_tables(keyword: str) -> str:
    """
    Busca tabelas cujo nome contenha o termo informado.
    Útil para descobrir tabelas relacionadas a um módulo.

    Traz a descrição da tabela em português vinda do dicionário Sankhya, para
    você saber qual das candidatas é a certa sem abrir uma por uma.

    Exemplos:
      search_tables("TGF")   → todas as tabelas de movimento
      search_tables("PARC")  → tabelas relacionadas a parceiros
      search_tables("FIN")   → tabelas financeiras
    """
    padrao = f"%{keyword.upper()}%"
    rows, truncated = fetch_rows(query("tables"), [padrao])
    descricoes = dictionary_rows("table_descriptions", padrao)
    return (
        rows_to_markdown(merge_table_descriptions(rows, descricoes))
        + truncation_note(truncated)
    )


@mcp.tool()
def search_columns(column_keyword: str, table_keyword: str = "") -> str:
    """
    Busca em quais tabelas existe um campo com o nome informado.
    Permite filtrar por prefixo de tabela.

    Traz a descrição de cada campo em português vinda do dicionário Sankhya.
    A mesma coluna pode significar coisas diferentes em tabelas diferentes, e é
    a descrição que separa uma da outra.

    Exemplos:
      search_columns("CODPARC")           → onde CODPARC aparece
      search_columns("CODPARC", "TGF")    → apenas em tabelas TGF*
      search_columns("DTFATUR")           → onde está o campo de faturamento
    """
    filtro = "AND c.TABLE_NAME LIKE {p2}" if table_keyword else ""
    params = [f"%{column_keyword.upper()}%"]
    if table_keyword:
        params.append(f"{table_keyword.upper()}%")
    rows, truncated = fetch_rows(query("columns_search", filtro=filtro), params)

    # O dicionário não tem alias de tabela: o filtro opcional usa a coluna crua.
    filtro_dic = "AND NOMETAB LIKE {p2}" if table_keyword else ""
    descricoes = dictionary_rows("column_descriptions", *params, filtro=filtro_dic)
    return (
        rows_to_markdown(merge_column_descriptions(rows, descricoes))
        + truncation_note(truncated)
    )


@mcp.tool()
def get_foreign_keys(table_name: str) -> str:
    """
    Retorna as foreign keys de uma tabela: qual coluna local aponta
    para qual tabela/coluna de destino.
    Aceita tanto o nome da tabela no banco quanto o EntityName (NOMEINSTANCIA).

    Exemplos:
      get_foreign_keys("TGFITE")
      get_foreign_keys("ItemNota")
    """
    resolved, entity_rows = resolve_table_name(table_name)
    rows = execute_query(query("foreign_keys"), [resolved], limit=None)
    ligacoes = dictionary_rows("links", resolved)

    if not rows and not ligacoes:
        return unresolved_name_note(table_name, entity_rows) or (
            f"Nenhuma FK encontrada para `{resolved}`."
        )

    partes = []
    if rows:
        partes.append(
            f"## Foreign Keys (banco) — {resolved}\n\n{rows_to_markdown(rows)}"
        )
    if ligacoes:
        partes.append(
            f"## Ligações do dicionário — {resolved}\n\n{rows_to_markdown(ligacoes)}\n\n"
            "_Ligação do dicionário é o relacionamento que o JAPE enxerga — o nome "
            "usado no código é o da entidade de destino. A FK acima é a restrição "
            "física do banco. As duas listas não coincidem: há ligação sem FK e "
            "FK sem ligação._"
        )
    return "\n\n".join(partes)


@mcp.tool()
def get_indexes(table_name: str) -> str:
    """
    Lista os índices de uma tabela e suas colunas.
    Útil para otimizar queries e entender chaves de busca.
    Aceita tanto o nome da tabela no banco quanto o EntityName (NOMEINSTANCIA).

    Exemplos:
      get_indexes("TGFCAB")
      get_indexes("CabecalhoNota")
    """
    resolved, entity_rows = resolve_table_name(table_name)
    rows = execute_query(query("indexes"), [resolved], limit=None)
    if not rows:
        return unresolved_name_note(table_name, entity_rows) or (
            f"Nenhum índice encontrado para `{resolved}`."
        )
    return f"## Índices — {resolved}\n\n{rows_to_markdown(rows)}"


@mcp.tool()
def run_query(sql: str, limit: int = 50) -> str:
    """
    Executa uma query SELECT na base Sankhya local e retorna até
    `limit` linhas formatadas como tabela Markdown.

    ATENÇÃO: Apenas SELECT é permitido. Queries de escrita serão bloqueadas.

    Antes de filtrar por um valor literal (`WHERE TIPMOV = 'P'`), chame
    `describe_table` na tabela e copie o valor da coluna `opcoes`. Os códigos do
    Sankhya são de uma letra e parecidos entre si — `V` é Venda e `P` é Pedido
    de venda —, e usar um pelo outro devolve o documento errado sem erro de SQL.

    A sintaxe é a do banco configurado — no Oracle use `ROWNUM <= 5`,
    no SQL Server use `SELECT TOP (5) ...`.
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
    Checa erros de sintaxe, tabelas inexistentes e colunas inválidas pelo
    plano estimado do banco (EXPLAIN PLAN no Oracle, SHOWPLAN_ALL no SQL Server).

    Exemplo: validate_query("SELECT NUNOTA, CODPARC FROM TGFCAB WHERE CODTIPOPER = 1")
    """
    erro = assert_read_only_query(sql)
    if erro:
        return f"❌ {erro}"

    try:
        rows = explain_plan(sql)
        if not rows:
            return "✅ Query válida (sem plano retornado)."
        return f"✅ Query válida.\n\n## Plano de Execução\n\n{rows_to_markdown(rows)}"
    except Exception as e:
        # PLAN_TABLE ausente/sem acesso é falha de ambiente, não da query:
        # reprovar a query aqui seria um veredito falso.
        if is_plan_unavailable(e):
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
    Aceita tanto o nome da tabela no banco quanto o EntityName (NOMEINSTANCIA).

    Colunas enumeradas vêm com o rótulo do dicionário ao lado do código
    (`L (Liberada)`), então a amostra também serve para conferir quais valores
    a tabela realmente usa — inclusive valor gravado fora do domínio declarado,
    que aparece sem rótulo.

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
        rows = execute_query(
            query("table_sample", tabela=resolved), [limit], limit=limit
        )
        if not rows:
            return f"Tabela `{resolved}` está vazia ou não existe."

        total_colunas = len(rows[0])
        amostra, ausentes, cortadas = select_columns(rows, columns)
        # Decora depois de projetar: só paga rótulo pelo que vai ser exibido.
        amostra = decorate_options(
            amostra, dictionary_rows("field_options", resolved)
        )
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
      search_entities("CabecalhoNota") → busca direta por EntityName
    """
    filtro = "AND RAIZ = 'S'" if only_root else ""
    termo = f"%{keyword}%"
    try:
        # Um parâmetro por placeholder: o pymssql não reaproveita bind posicional.
        rows, truncated = fetch_rows(
            query("search_entities", filtro=filtro), [termo, termo]
        )
    except Exception as exc:
        # Único lugar que dependia de TDDINS sem tratar a ausência: as outras duas
        # consultas ao dicionário degradam, aqui o erro cru vazava para o cliente
        # MCP. Sem TDDINS esta tool não tem o que responder, mas o motivo precisa
        # ser legível.
        if not is_missing_object(exc):
            raise
        return (
            "❌ O dicionário Sankhya (TDDINS) não está acessível neste schema, "
            "então não há entidades a buscar. Verifique `SANKHYA_DB_SCHEMA` ou as "
            "permissões do usuário conectado."
        )
    if not rows:
        return f"_Nenhuma entidade encontrada para `{keyword}`._"
    note = truncation_note(truncated)
    return f"## Entidades — '{keyword}'\n\n{rows_to_markdown(rows)}{note}"


@mcp.tool()
def list_modules() -> str:
    """
    Lista os módulos do Sankhya agrupando as tabelas pelo prefixo de
    3 caracteres do nome (TGFCAB, TGFITE e TGFPAR contam para TGF), com a
    contagem de tabelas de cada módulo.

    Retorna uma visão geral dos módulos disponíveis no schema. Prefixo com uma
    tabela só fica de fora. Tabelas customizadas aparecem sob `AD_`.
    """
    rows = execute_query(query("table_names"), limit=None)
    modulos = group_prefixes([r["table_name"] for r in rows])
    return f"## Módulos do Schema Sankhya\n\n{rows_to_markdown(modulos)}"


@mcp.tool()
def check_updates() -> str:
    """
    Informa se há versão mais nova deste servidor MCP publicada e o que mudou.

    Compara a versão instalada com a maior tag do repositório de origem e,
    havendo diferença, lista as entradas do CHANGELOG no intervalo e o comando
    de atualização. Ignora o cache: a resposta é sempre a consulta de agora.
    """
    local = parse_version(__version__)
    remota = latest_version(use_cache=False)

    if not remota:
        return (
            f"Versão instalada: **{__version__}**.\n\n"
            "⚠️ Não foi possível consultar as versões publicadas. Verifique se o "
            "`git` está no PATH, se este diretório é um clone com `origin` "
            "configurado e se há acesso à rede."
        )
    if remota <= local:
        return f"✅ Você está na versão mais recente (**{__version__}**)."

    mudancas = changelog_entries(local, remota)
    corpo = (
        f"## Atualização disponível\n\n"
        f"Instalada: **{__version__}** — Publicada: **{format_version(remota)}**\n\n"
    )
    if mudancas:
        corpo += f"{mudancas}\n\n"
    return corpo + (
        "### Como atualizar\n\n"
        "```bash\n"
        f"cd {PROJECT_ROOT}\n"
        "git pull\n"
        "```\n\n"
        "Depois reinicie o cliente MCP. Se o `CHANGELOG` mencionar dependência "
        "nova, rode também a instalação de dependências do `README`."
    )


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
