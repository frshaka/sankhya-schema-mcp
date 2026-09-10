"""
Imprime as notas de release de uma versão, lidas do CHANGELOG.md.

Fonte única das notas: o CHANGELOG já é escrito a cada mudança e é o mesmo
texto que a tool `check_updates` mostra ao cliente. Gerar as notas do release
do GitHub a partir de outro lugar abriria a chance de os dois divergirem.

Consumidores:
  - .github/workflows/release.yml — corpo do release publicado no GitHub
  - tools/release.sh / release.ps1 — recusam a tag quando a seção está vazia

Uso:
    python tools/release_notes.py 1.2.1
    python tools/release_notes.py v1.2.1

Sai com código 1 quando a versão não tem seção no CHANGELOG ou a seção está
vazia. O código de saída é o que reprova a publicação.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from updates import changelog_section, parse_version  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"uso: {Path(argv[0]).name} <versão>", file=sys.stderr)
        return 2

    versao = parse_version(argv[1])
    if not versao:
        print(f"versão inválida: {argv[1]!r}", file=sys.stderr)
        return 2

    notas = changelog_section(versao)
    if not notas:
        print(
            f"CHANGELOG.md não tem seção com conteúdo para a versão {argv[1]}. "
            "Toda release precisa explicar o que mudou.",
            file=sys.stderr,
        )
        return 1

    print(notas)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
