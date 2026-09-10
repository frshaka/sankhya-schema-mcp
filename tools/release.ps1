# Validador de publicacao do Sankhya Schema MCP (Windows).
#
# Espelho de tools/release.sh. Cria a tag da versao em src/version.py, mas so
# depois de checar tudo que faria a tag mentir para o cliente: o aviso de
# atualizacao do servidor confia na tag publicada.
#
# Uso:
#   pwsh tools/release.ps1           # valida e cria a tag localmente
#   pwsh tools/release.ps1 -Push     # valida, cria a tag e publica no origin

[CmdletBinding()]
param([switch]$Push)

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

function Falhar($mensagem) {
    Write-Error "ERRO: $mensagem"
    exit 1
}

$py = Join-Path $raiz ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = Join-Path $raiz ".venv/bin/python" }
if (-not (Test-Path $py)) { $py = "python" }

# 1. Working tree limpa: arquivo nao commitado nao entra na tag.
if (git status --porcelain) {
    Falhar "working tree suja. Faca commit ou stash antes de publicar."
}

# 2. Versao declarada no codigo.
$versao = & $py -c "import sys; sys.path.insert(0, 'src'); import version; print(version.__version__)"
if (-not $versao) { Falhar "nao consegui ler __version__ de src/version.py." }
$versao = $versao.Trim()
$tag = "v$versao"

# 3. Topo do CHANGELOG tem que ser a mesma versao — e o texto que o
#    check_updates mostra ao cliente.
if (-not (Test-Path "CHANGELOG.md")) { Falhar "CHANGELOG.md nao existe." }
$cabecalho = Select-String -Path "CHANGELOG.md" -Pattern '^##\s+\[?v?(\d+(\.\d+)*)\]?' | Select-Object -First 1
if (-not $cabecalho) { Falhar "nao encontrei nenhuma secao de versao no CHANGELOG.md." }
$topo = $cabecalho.Matches[0].Groups[1].Value
if ($topo -ne $versao) {
    Falhar "src/version.py diz $versao e o topo do CHANGELOG diz $topo. Sincronize os dois."
}

# 4. A secao precisa ter conteudo, nao so o cabecalho. E o texto que vira as
#    notas do release no GitHub: release sem nota nao diz ao cliente o que
#    mudou, que e justamente o problema que o versionamento veio resolver.
& $py tools/release_notes.py $versao *> $null
if ($LASTEXITCODE -ne 0) {
    Falhar "a secao $versao do CHANGELOG esta vazia. Descreva o que mudou antes de publicar."
}

# 5. Tag nao pode existir, nem aqui nem no origin: remarcar tag publicada faz
#    quem ja atualizou nunca mais ver a diferenca.
git rev-parse -q --verify "refs/tags/$tag" *> $null
if ($LASTEXITCODE -eq 0) { Falhar "a tag $tag ja existe localmente." }
git ls-remote --exit-code --tags origin $tag *> $null
if ($LASTEXITCODE -eq 0) { Falhar "a tag $tag ja existe no origin." }

# 6. Testes. Ultima porta antes de a versao virar publica.
Write-Host "Rodando os testes..."
& $py test_server.py
if ($LASTEXITCODE -ne 0) { Falhar "os testes falharam. Nada foi publicado." }

git tag -a $tag -m $tag
Write-Host "Tag $tag criada localmente."
Write-Host "As notas do release sairao do CHANGELOG quando a tag chegar ao origin."

if ($Push) {
    git push origin $tag
    Write-Host "Tag $tag publicada no origin."
} else {
    # Publicar e irreversivel na pratica: o cliente pode ja ter feito fetch.
    Write-Host "Para publicar: git push origin $tag   (ou rode com -Push)"
}
