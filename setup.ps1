# URL do instantclient hospedado no GitHub Releases
$InstantClientUrl = "https://github.com/frshaka/sankhya-schema-mcp/releases/download/v1.0/instantclient.zip"

$ProjectRoot = $PSScriptRoot
$InstantClientDir = Join-Path $ProjectRoot "instantclient"
$ZipPath = Join-Path $ProjectRoot "instantclient.zip"
$VenvDir = Join-Path $ProjectRoot ".venv"
$RequirementsFile = Join-Path $ProjectRoot "requirements.txt"

Write-Host "=== Setup Sankhya Schema MCP ===" -ForegroundColor Cyan

# 1. Baixar e extrair o Oracle Instant Client
if (Test-Path $InstantClientDir) {
    Write-Host "[OK] instantclient/ ja existe — pulando download." -ForegroundColor Green
} else {
    Write-Host "[1/3] Baixando Oracle Instant Client..." -ForegroundColor Yellow
    try {
        Invoke-WebRequest -Uri $InstantClientUrl -OutFile $ZipPath -UseBasicParsing
    } catch {
        Write-Error "Falha no download: $_"
        Write-Host "Baixe manualmente de: $InstantClientUrl" -ForegroundColor Red
        exit 1
    }

    Write-Host "[1/3] Extraindo instantclient.zip..." -ForegroundColor Yellow
    Expand-Archive -Path $ZipPath -DestinationPath $ProjectRoot -Force
    Remove-Item $ZipPath -Force

    if (-not (Test-Path (Join-Path $InstantClientDir "oci.dll"))) {
        Write-Error "Extracao falhou: oci.dll nao encontrado em instantclient/"
        exit 1
    }
    Write-Host "[OK] instantclient/ extraido com sucesso." -ForegroundColor Green
}

# 2. Criar o ambiente virtual Python
if (Test-Path (Join-Path $VenvDir "Scripts\python.exe")) {
    Write-Host "[OK] Ambiente virtual ja existe — pulando criacao." -ForegroundColor Green
} else {
    Write-Host "[2/3] Criando ambiente virtual Python..." -ForegroundColor Yellow
    python -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Falha ao criar venv. Verifique se o Python 3.10+ esta instalado e no PATH."
        exit 1
    }
    Write-Host "[OK] Ambiente virtual criado." -ForegroundColor Green
}

# 3. Instalar dependencias
Write-Host "[3/3] Instalando dependencias Python..." -ForegroundColor Yellow
& "$VenvDir\Scripts\pip" install -r $RequirementsFile --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Error "Falha ao instalar dependencias."
    exit 1
}
Write-Host "[OK] Dependencias instaladas." -ForegroundColor Green

Write-Host ""
Write-Host "=== Instalacao concluida! ===" -ForegroundColor Cyan
Write-Host "Proximo passo: edite as credenciais em start.ps1 e registre o MCP no Claude Code."
Write-Host "Consulte INSTALACAO.md para instrucoes detalhadas."
