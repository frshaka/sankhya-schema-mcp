# URL do repositorio e do instantclient no GitHub Releases
$RepoUrl          = "https://github.com/frshaka/sankhya-schema-mcp.git"
$InstantClientUrl = "https://github.com/frshaka/sankhya-schema-mcp/releases/download/v1.0/instantclient.zip"

Write-Host "=== Setup Sankhya Schema MCP ===" -ForegroundColor Cyan
Write-Host ""

# ---------------------------------------------------------------------------
# Determinar raiz do projeto
# ---------------------------------------------------------------------------
$HasProjectFiles = (Test-Path (Join-Path $PSScriptRoot "src\server.py")) -and
                   (Test-Path (Join-Path $PSScriptRoot "requirements.txt"))

if ($HasProjectFiles) {
    $ProjectRoot = $PSScriptRoot
    Write-Host "[OK] Projeto encontrado em: $ProjectRoot" -ForegroundColor Green
} else {
    Write-Host "Arquivos do projeto nao encontrados em: $PSScriptRoot" -ForegroundColor Yellow
    $default  = "C:\projetos\sankhya-mcp"
    $userInput = Read-Host "Informe o caminho de instalacao [Enter para $default]"
    $ProjectRoot = if ($userInput.Trim() -eq "") { $default } else { $userInput.Trim() }

    if (Test-Path (Join-Path $ProjectRoot "src\server.py")) {
        Write-Host "[OK] Projeto ja existe em: $ProjectRoot" -ForegroundColor Green
    } else {
        Write-Host "[0] Clonando repositorio em: $ProjectRoot ..." -ForegroundColor Yellow
        git clone $RepoUrl $ProjectRoot 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Falha ao clonar. Verifique se git esta instalado e o repositorio e acessivel."
            exit 1
        }
        Write-Host "[OK] Repositorio clonado." -ForegroundColor Green
    }

    # Se este setup.ps1 veio de fora do projeto, re-invocar o do repo clonado e sair
    $clonedSetup = Join-Path $ProjectRoot "setup.ps1"
    if ((Resolve-Path $PSCommandPath).Path -ne (Resolve-Path $clonedSetup -ErrorAction SilentlyContinue)?.Path) {
        Write-Host ""
        Write-Host "Continuando setup a partir do projeto clonado..." -ForegroundColor Cyan
        & pwsh -NoProfile -ExecutionPolicy Bypass -File $clonedSetup
        exit $LASTEXITCODE
    }
}

$InstantClientDir = Join-Path $ProjectRoot "instantclient"
$ZipPath          = Join-Path $ProjectRoot "instantclient.zip"
$VenvDir          = Join-Path $ProjectRoot ".venv"
$RequirementsFile = Join-Path $ProjectRoot "requirements.txt"

# ---------------------------------------------------------------------------
# 1. Oracle Instant Client
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# 2. Ambiente virtual Python
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# 3. Dependencias
# ---------------------------------------------------------------------------
Write-Host "[3/3] Instalando dependencias Python..." -ForegroundColor Yellow
& "$VenvDir\Scripts\pip" install -r $RequirementsFile --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Error "Falha ao instalar dependencias."
    exit 1
}
Write-Host "[OK] Dependencias instaladas." -ForegroundColor Green

# ---------------------------------------------------------------------------
# 4. Registrar MCP no Claude Code
# ---------------------------------------------------------------------------
Write-Host "[4/4] Registrando MCP no Claude Code..." -ForegroundColor Yellow

$StartScript = Join-Path $ProjectRoot "start.ps1"
$McpEntry = [PSCustomObject]@{
    type    = "stdio"
    command = "pwsh"
    args    = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $StartScript)
    env     = [PSCustomObject]@{}
}

$ClaudeJson = Join-Path $env:USERPROFILE ".claude\.claude.json"

if (-not (Test-Path $ClaudeJson)) {
    Write-Host "  [AVISO] $ClaudeJson nao encontrado — registre o MCP manualmente." -ForegroundColor Yellow
} else {
    $json = Get-Content $ClaudeJson -Raw | ConvertFrom-Json

    if (-not ($json.PSObject.Properties.Name -contains "mcpServers")) {
        $json | Add-Member -MemberType NoteProperty -Name "mcpServers" -Value ([PSCustomObject]@{}) -Force
    }

    if ($json.mcpServers.PSObject.Properties.Name -contains "sankhya-schema") {
        Write-Host "  [OK] MCP ja registrado." -ForegroundColor Green
    } else {
        $json.mcpServers | Add-Member -MemberType NoteProperty -Name "sankhya-schema" -Value $McpEntry -Force
        $json | ConvertTo-Json -Depth 20 | Set-Content $ClaudeJson -Encoding UTF8
        Write-Host "  [OK] MCP registrado com sucesso." -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "=== Instalacao concluida! ===" -ForegroundColor Cyan
Write-Host "Proximo passo: edite as credenciais em start.ps1, reinicie o Claude Code e rode /mcp para confirmar."
