"""
Versão do Sankhya Schema MCP — fonte única.

Lida pelo servidor (aviso de atualização e tool `check_updates`) e pelo
validador de publicação (`tools/release.sh`), que recusa criar a tag quando
este número diverge do topo do CHANGELOG.

Formato SemVer `MAJOR.MINOR.PATCH`, publicado como tag `vMAJOR.MINOR.PATCH`.
"""

__version__ = "1.3.0"
