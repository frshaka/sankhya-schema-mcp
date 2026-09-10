"""
Aviso de atualização do Sankhya Schema MCP.

O cliente instala este servidor por `git clone` (ver `setup.sh`/`setup.ps1`), o
que faz do próprio git a fonte de verdade sobre o que existe publicado. Daí
`git ls-remote --tags`: sem API do GitHub, sem token, sem dependência HTTP nova
e funcionando igual em repositório privado, onde a credencial do clone já vale.

Nada aqui pode derrubar o servidor nem atrasar o handshake MCP: a consulta tem
timeout curto, o resultado é cacheado em disco e qualquer falha — offline, git
ausente, remote inacessível — degrada em silêncio para "sem aviso".
"""

import json
import re
import subprocess
import time
from pathlib import Path
from typing import Optional

from version import __version__

# Raiz do repositório (exposta: a tool check_updates mostra o caminho ao usuário): `git ls-remote` precisa rodar dentro dele, e o CHANGELOG
# e o cache moram lá.
PROJECT_ROOT = Path(__file__).parent.parent
_CACHE = PROJECT_ROOT / ".update-check.json"
_CHANGELOG = PROJECT_ROOT / "CHANGELOG.md"

# Teto de espera pela rede. O boot do MCP fica parado nisso na primeira vez do
# dia; acima de poucos segundos o cliente MCP começa a reclamar do handshake.
_TIMEOUT_S = 2.0

# Validade do cache. Release deste projeto é evento raro — consultar o remote a
# cada start seria pagar rede para ouvir a mesma resposta.
_TTL_S = 24 * 60 * 60

_TAG_RE = re.compile(r"refs/tags/v?(\d+(?:\.\d+)*)$")
_VERSAO_RE = re.compile(r"^\d+(?:\.\d+)*$")


def parse_version(texto: str) -> Optional[tuple]:
    """
    Converte `1.2.0` (ou `v1.2`) em tupla comparável de 3 posições.

    Tag antiga deste repositório tem duas posições (`v1.1`); completar com zero
    faz `1.1` e `1.1.0` compararem iguais, que é o que se espera. Texto que não
    for número separado por ponto devolve None em vez de levantar — a lista de
    tags de um repositório qualquer pode conter nome que não é versão.
    """
    texto = (texto or "").strip().lstrip("vV")
    if not _VERSAO_RE.match(texto):
        return None
    partes = [int(p) for p in texto.split(".")][:3]
    return tuple(partes + [0] * (3 - len(partes)))


def format_version(versao: tuple) -> str:
    """Tupla de volta para `1.2.0`."""
    return ".".join(str(p) for p in versao)


def pick_latest(refs: list[str]) -> Optional[tuple]:
    """
    Maior versão entre as linhas de `git ls-remote --tags`.

    Descarta o sufixo `^{}` das tags anotadas (o git lista a tag e o objeto que
    ela aponta) e qualquer ref que não seja versão. Sem tag válida, None.
    """
    versoes = []
    for linha in refs:
        m = _TAG_RE.search(linha.strip().replace("^{}", ""))
        if m:
            v = parse_version(m.group(1))
            if v:
                versoes.append(v)
    return max(versoes) if versoes else None


def _consulta_remote() -> Optional[tuple]:
    """Maior tag publicada no remote, ou None se a consulta não completar."""
    try:
        proc = subprocess.run(
            ["git", "ls-remote", "--tags", "origin"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError):
        # git ausente, sem rede, ou estourou o timeout: sem aviso, sem ruído.
        return None
    if proc.returncode != 0:
        return None
    return pick_latest(proc.stdout.splitlines())


def _le_cache() -> Optional[tuple]:
    try:
        dados = json.loads(_CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if time.time() - dados.get("checked_at", 0) > _TTL_S:
        return None
    return parse_version(dados.get("latest") or "")


def _grava_cache(versao: Optional[tuple]) -> None:
    try:
        _CACHE.write_text(
            json.dumps(
                {
                    "checked_at": time.time(),
                    "latest": format_version(versao) if versao else None,
                }
            ),
            encoding="utf-8",
        )
    except OSError:
        # Instalação em diretório somente-leitura: perde o cache, não o servidor.
        pass


def latest_version(use_cache: bool = True) -> Optional[tuple]:
    """
    Maior versão publicada. Com `use_cache`, responde do disco enquanto o TTL
    valer; a tool `check_updates` passa False para forçar a consulta.
    """
    if use_cache:
        em_cache = _le_cache()
        if em_cache:
            return em_cache
    remota = _consulta_remote()
    if remota:
        _grava_cache(remota)
    return remota


def changelog_entries(de: tuple, ate: tuple) -> str:
    """
    Trecho do CHANGELOG entre duas versões, `de` exclusivo e `ate` inclusivo.

    Serve para o aviso dizer *o que* mudou, não só que mudou. CHANGELOG ausente
    ou sem seção no intervalo devolve string vazia — o aviso continua válido.
    """
    try:
        texto = _CHANGELOG.read_text(encoding="utf-8")
    except OSError:
        return ""

    blocos, atual, versao_atual = [], [], None
    for linha in texto.splitlines():
        cabecalho = re.match(r"^##\s+\[?v?(\d+(?:\.\d+)*)\]?", linha)
        if cabecalho:
            if versao_atual and de < versao_atual <= ate:
                blocos.append("\n".join(atual).rstrip())
            versao_atual = parse_version(cabecalho.group(1))
            atual = [linha]
        elif versao_atual:
            atual.append(linha)
    if versao_atual and de < versao_atual <= ate:
        blocos.append("\n".join(atual).rstrip())

    return "\n\n".join(blocos).strip()


def update_notice(use_cache: bool = True) -> Optional[str]:
    """
    Aviso pronto quando há versão mais nova publicada, ou None.

    Vai para as `instructions` do servidor no boot: é o único canal que alcança
    o usuário sem depender de alguém lembrar de perguntar. Nunca levanta —
    falha de rede ou de disco resulta em None.
    """
    try:
        local = parse_version(__version__)
        remota = latest_version(use_cache=use_cache)
        if not local or not remota or remota <= local:
            return None
        return (
            f"Este servidor está na versão {format_version(local)} e a "
            f"{format_version(remota)} já foi publicada. Avise o usuário na "
            "primeira resposta e diga que a tool `check_updates` mostra o que "
            "mudou e como atualizar."
        )
    except Exception:
        return None
