#!/usr/bin/env bash
#
# Validador de publicação do Sankhya Schema MCP.
#
# Cria a tag da versão em src/version.py, mas só depois de checar tudo que faria
# a tag mentir para o cliente. O aviso de atualização do servidor confia na tag
# publicada: uma tag criada com versão dessincronizada do CHANGELOG faz o
# `check_updates` anunciar mudança que ninguém consegue ler.
#
# Uso:
#   tools/release.sh           # valida e cria a tag localmente
#   tools/release.sh --push    # valida, cria a tag e publica no origin
#
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ"

PUSH=0
[ "${1:-}" = "--push" ] && PUSH=1

if [ -x ".venv/bin/python" ]; then
    PY=".venv/bin/python"
elif [ -x ".venv/Scripts/python.exe" ]; then
    PY=".venv/Scripts/python.exe"
else
    PY="python3"
fi

falhar() {
    echo "ERRO: $1" >&2
    exit 1
}

# 1. Working tree limpa. Tag aponta para um commit; arquivo não commitado não
#    entra nela e o cliente receberia algo diferente do que foi validado aqui.
[ -z "$(git status --porcelain)" ] || falhar "working tree suja. Faça commit ou stash antes de publicar."

# 2. Versão declarada no código.
VERSAO="$("$PY" -c "import sys; sys.path.insert(0, 'src'); import version; print(version.__version__)")"
[ -n "$VERSAO" ] || falhar "não consegui ler __version__ de src/version.py."
TAG="v$VERSAO"

# 3. Topo do CHANGELOG tem que ser a mesma versão. É o texto que o
#    `check_updates` mostra ao cliente.
[ -f CHANGELOG.md ] || falhar "CHANGELOG.md não existe."
TOPO="$(grep -m1 -oE '^## \[?v?[0-9]+(\.[0-9]+)*\]?' CHANGELOG.md | grep -oE '[0-9]+(\.[0-9]+)*' || true)"
[ -n "$TOPO" ] || falhar "não encontrei nenhuma seção de versão no CHANGELOG.md."
[ "$TOPO" = "$VERSAO" ] || falhar "src/version.py diz $VERSAO e o topo do CHANGELOG diz $TOPO. Sincronize os dois."

# 4. A seção precisa ter conteúdo, não só o cabeçalho. É o texto que vira as
#    notas do release no GitHub: release sem nota não diz ao cliente o que
#    mudou, que é justamente o problema que o versionamento veio resolver.
"$PY" tools/release_notes.py "$VERSAO" >/dev/null || falhar "a seção $VERSAO do CHANGELOG está vazia. Descreva o que mudou antes de publicar."

# 5. Tag ainda não pode existir, nem aqui nem no origin. Remarcar uma tag já
#    publicada faz o cliente que já atualizou nunca mais ver a diferença.
! git rev-parse -q --verify "refs/tags/$TAG" >/dev/null || falhar "a tag $TAG já existe localmente."
if git ls-remote --exit-code --tags origin "$TAG" >/dev/null 2>&1; then
    falhar "a tag $TAG já existe no origin."
fi

# 6. Testes. Última porta antes de a versão virar pública.
echo "Rodando os testes..."
"$PY" test_server.py || falhar "os testes falharam. Nada foi publicado."

git tag -a "$TAG" -m "$TAG"
echo "Tag $TAG criada localmente."
echo "As notas do release sairao do CHANGELOG quando a tag chegar ao origin."

if [ "$PUSH" = "1" ]; then
    git push origin "$TAG"
    echo "Tag $TAG publicada no origin."
else
    # Publicar é irreversível na prática: o cliente pode já ter feito fetch.
    # Exige o passo explícito.
    echo "Para publicar: git push origin $TAG   (ou rode com --push)"
fi
