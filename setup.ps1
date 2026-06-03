param(
    [string]$ConfigDir,
    [string]$Cli
)

# URL do repositorio e do instantclient no GitHub Releases
$RepoUrl          = "https://github.com/frshaka/sankhya-schema-mcp.git"
$InstantClientUrl = "https://github.com/frshaka/sankhya-schema-mcp/releases/download/v1.1/instantclient.zip"

Write-Host "=== Setup Sankhya Schema MCP ===" -ForegroundColor Cyan
Write-Host ""

# ---------------------------------------------------------------------------
# Selecao de CLIs para registro do MCP
# - Com -Cli claude|codex|both: usa o valor informado (nao interativo)
# - Sem -Cli: exibe menu interativo (default: Claude Code)
# ---------------------------------------------------------------------------
if ([string]::IsNullOrWhiteSpace($Cli)) {
    Write-Host "Em quais CLIs deseja registrar o MCP?" -ForegroundColor Cyan
    Write-Host "  [1] Claude Code"
    Write-Host "  [2] Codex CLI"
    Write-Host "  [3] Ambos"
    $cliChoice = Read-Host "Escolha [Enter para 1]"
    switch ($cliChoice.Trim()) {
        ""  { $Cli = "claude" }
        "1" { $Cli = "claude" }
        "2" { $Cli = "codex" }
        "3" { $Cli = "both" }
        default {
            Write-Error "Opcao invalida: '$cliChoice'. Use 1, 2 ou 3."
            exit 1
        }
    }
} else {
    $Cli = $Cli.Trim().ToLower()
    if ($Cli -notin @("claude", "codex", "both")) {
        Write-Error "Valor invalido para -Cli: '$Cli'. Use claude, codex ou both."
        exit 1
    }
}

$InstallClaude = $Cli -in @("claude", "both")
$InstallCodex  = $Cli -in @("codex", "both")

# ---------------------------------------------------------------------------
# Resolver caminhos de configuracao do Claude Code
# - Sem --config-dir: usa default ($HOME\.claude.json + $HOME\.claude\settings.json)
# - Com --config-dir: ambos arquivos ficam dentro do diretorio informado
# ---------------------------------------------------------------------------
if ($InstallClaude) {
    if ([string]::IsNullOrWhiteSpace($ConfigDir)) {
        $ClaudeJson   = Join-Path $env:USERPROFILE ".claude.json"
        $SettingsJson = Join-Path $env:USERPROFILE ".claude\settings.json"
        Write-Host "[INFO] Usando configuracao padrao do Claude Code." -ForegroundColor DarkGray
    } else {
        $ConfigDir    = $ConfigDir.Trim()
        $ClaudeJson   = Join-Path $ConfigDir ".claude.json"
        $SettingsJson = Join-Path $ConfigDir "settings.json"
        Write-Host "[INFO] Usando diretorio de configuracao: $ConfigDir" -ForegroundColor DarkGray
    }
}

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
        $invokeArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $clonedSetup, "-Cli", $Cli)
        if (-not [string]::IsNullOrWhiteSpace($ConfigDir)) {
            $invokeArgs += @("-ConfigDir", $ConfigDir)
        }
        & pwsh @invokeArgs
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

$StartScript = Join-Path $ProjectRoot "start.ps1"

# ---------------------------------------------------------------------------
# 4. Registrar MCP no Claude Code
# ---------------------------------------------------------------------------
if ($InstallClaude) {

Write-Host "[4/5] Registrando MCP no Claude Code..." -ForegroundColor Yellow

$McpEntry = [PSCustomObject]@{
    type    = "stdio"
    command = "pwsh"
    args    = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $StartScript)
    env     = [PSCustomObject]@{}
}

$ClaudeJsonDir = Split-Path $ClaudeJson -Parent
if (-not (Test-Path $ClaudeJsonDir)) {
    New-Item -ItemType Directory -Path $ClaudeJsonDir -Force | Out-Null
}

if (-not (Test-Path $ClaudeJson)) {
    $json = [PSCustomObject]@{ mcpServers = [PSCustomObject]@{} }
} else {
    $json = Get-Content $ClaudeJson -Raw | ConvertFrom-Json
}

if (-not ($json.PSObject.Properties.Name -contains "mcpServers")) {
    $json | Add-Member -MemberType NoteProperty -Name "mcpServers" -Value ([PSCustomObject]@{}) -Force
}

if ($json.mcpServers.PSObject.Properties.Name -contains "sankhya-schema") {
    Write-Host "  [OK] MCP ja registrado em $ClaudeJson." -ForegroundColor Green
} else {
    $json.mcpServers | Add-Member -MemberType NoteProperty -Name "sankhya-schema" -Value $McpEntry -Force
    $json | ConvertTo-Json -Depth 20 | Set-Content $ClaudeJson -Encoding UTF8
    Write-Host "  [OK] MCP registrado em $ClaudeJson." -ForegroundColor Green
}

# ---------------------------------------------------------------------------
# 5. Liberar permissoes das tools MCP no Claude Code
# ---------------------------------------------------------------------------
Write-Host "[5/5] Liberando permissoes das tools MCP..." -ForegroundColor Yellow

if (-not (Test-Path $SettingsJson)) {
    # Criar settings.json com permissoes minimas
    $settings = [PSCustomObject]@{
        permissions = [PSCustomObject]@{
            allow = @("mcp__sankhya-schema__*")
        }
    }
    New-Item -ItemType Directory -Path (Split-Path $SettingsJson) -Force | Out-Null
    $settings | ConvertTo-Json -Depth 10 | Set-Content $SettingsJson -Encoding UTF8
    Write-Host "  [OK] Permissoes configuradas (settings.json criado)." -ForegroundColor Green
} else {
    $settings = Get-Content $SettingsJson -Raw | ConvertFrom-Json

    if (-not ($settings.PSObject.Properties.Name -contains "permissions")) {
        $settings | Add-Member -MemberType NoteProperty -Name "permissions" -Value ([PSCustomObject]@{
            allow = @("mcp__sankhya-schema__*")
        }) -Force
        $settings | ConvertTo-Json -Depth 10 | Set-Content $SettingsJson -Encoding UTF8
        Write-Host "  [OK] Permissoes configuradas." -ForegroundColor Green
    } elseif (-not ($settings.permissions.PSObject.Properties.Name -contains "allow")) {
        $settings.permissions | Add-Member -MemberType NoteProperty -Name "allow" -Value @("mcp__sankhya-schema__*") -Force
        $settings | ConvertTo-Json -Depth 10 | Set-Content $SettingsJson -Encoding UTF8
        Write-Host "  [OK] Permissoes configuradas." -ForegroundColor Green
    } else {
        $allowList = @($settings.permissions.allow)
        if ($allowList -contains "mcp__sankhya-schema__*") {
            Write-Host "  [OK] Permissoes ja configuradas." -ForegroundColor Green
        } else {
            $allowList += "mcp__sankhya-schema__*"
            $settings.permissions.allow = $allowList
            $settings | ConvertTo-Json -Depth 10 | Set-Content $SettingsJson -Encoding UTF8
            Write-Host "  [OK] Permissoes adicionadas." -ForegroundColor Green
        }
    }
}

} # fim if ($InstallClaude)

# ---------------------------------------------------------------------------
# 6. Registrar MCP no Codex CLI
# - Config: $CODEX_HOME/config.toml (default: ~/.codex/config.toml)
# - Codex nao tem allow-list por tool; aprovacao segue a approval policy global
# ---------------------------------------------------------------------------
if ($InstallCodex) {
    Write-Host "[Codex] Registrando MCP no Codex CLI..." -ForegroundColor Yellow

    $CodexHome = if ([string]::IsNullOrWhiteSpace($env:CODEX_HOME)) {
        Join-Path $env:USERPROFILE ".codex"
    } else {
        $env:CODEX_HOME
    }
    $CodexConfig = Join-Path $CodexHome "config.toml"

    # TOML: usar barras normais evita escape de backslash em strings basicas
    $StartScriptToml = $StartScript -replace '\\', '/'

    if ((Test-Path $CodexConfig) -and
        (Select-String -Path $CodexConfig -Pattern '^\s*\[mcp_servers\.sankhya-schema\]' -Quiet)) {
        Write-Host "  [OK] MCP ja registrado em $CodexConfig." -ForegroundColor Green
    } else {
        if (-not (Test-Path $CodexHome)) {
            New-Item -ItemType Directory -Path $CodexHome -Force | Out-Null
        }

        # Garantir newline final no arquivo existente antes do append
        if (Test-Path $CodexConfig) {
            $codexRaw = Get-Content $CodexConfig -Raw
            if ($codexRaw -and -not $codexRaw.EndsWith("`n")) {
                Add-Content -Path $CodexConfig -Value "" -Encoding UTF8
            }
        }

        $codexEntry = @"

[mcp_servers.sankhya-schema]
command = "pwsh"
args = ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "$StartScriptToml"]
"@

        Add-Content -Path $CodexConfig -Value $codexEntry -Encoding UTF8
        Write-Host "  [OK] MCP registrado em $CodexConfig." -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "=== Instalacao concluida! ===" -ForegroundColor Cyan
Write-Host "Proximo passo: edite as credenciais em .env (use .env.example como modelo)."
if ($InstallClaude) {
    Write-Host "Claude Code: reinicie e rode /mcp para confirmar. As tools foram liberadas automaticamente."
}
if ($InstallCodex) {
    Write-Host "Codex CLI: reinicie e rode 'codex mcp list' para confirmar. Aprove as tools na primeira chamada ou ajuste a approval policy."
}
