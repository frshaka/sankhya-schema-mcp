# Atualiza o Sankhya Schema MCP: baixa a versao publicada e reinstala as dependencias.
#
# Pode rodar com o cliente MCP aberto: o pip substitui ate os binarios que o
# servidor em execucao mantem carregados. A versao nova so vale depois de
# reiniciar o cliente.

$ErrorActionPreference = "Stop"
$Python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    Write-Error "Ambiente virtual nao encontrado em $PSScriptRoot\.venv. Rode o setup.ps1."
    exit 1
}

Write-Host "[1/3] Baixando a versao publicada..." -ForegroundColor Yellow
# --ff-only: com alteracao local no clone, falha em vez de criar um merge.
git -C $PSScriptRoot pull --ff-only
if ($LASTEXITCODE -ne 0) {
    Write-Error "git pull falhou. Verifique alteracoes locais em $PSScriptRoot (git status)."
    exit 1
}

Write-Host "[2/3] Reinstalando dependencias..." -ForegroundColor Yellow
& $Python -m pip install -r (Join-Path $PSScriptRoot "requirements.txt") --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Error "Falha ao instalar dependencias."
    exit 1
}

# O driver do SQL Server e opcional: so atualiza quem ja o tem instalado.
& $Python -c "import pymssql" 2>$null
if ($LASTEXITCODE -eq 0) {
    & $Python -m pip install -r (Join-Path $PSScriptRoot "requirements-sqlserver.txt") --quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Falha ao instalar o driver do SQL Server."
        exit 1
    }
}

Write-Host "[3/3] Conferindo o SDK MCP..." -ForegroundColor Yellow
& $Python -c "import mcp.server.mcpserver"
if ($LASTEXITCODE -ne 0) {
    Write-Error "O SDK MCP 2.x nao ficou disponivel no ambiente virtual."
    exit 1
}

Write-Host "[OK] Atualizado. Reinicie o cliente MCP (Claude Code / Codex) para carregar a nova versao." -ForegroundColor Green
