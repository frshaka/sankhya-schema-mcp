function Import-EnvFile($path) {
    if (-not (Test-Path $path)) { return $false }
    Get-Content $path | ForEach-Object {
        $line = $_.Trim()
        if ($line -and !$line.StartsWith("#")) {
            $parts = $line -split "=", 2
            if ($parts.Length -eq 2) {
                $key = $parts[0].Trim()
                $value = $parts[1].Trim()
                Set-Item -Path "env:$key" -Value $value
            }
        }
    }
    return $true
}

# Caminhos dos arquivos de configuracao
$generalEnv = Join-Path $PSScriptRoot ".env"           # geral (base/defaults)
$projectEnv = Join-Path $PWD ".sankhya-mcp.env"        # por projeto (override)

# 1. Carrega o .env geral primeiro (base)
Import-EnvFile $generalEnv | Out-Null
# 2. Carrega o .env do projeto por cima (sobrescreve o que diferir)
Import-EnvFile $projectEnv | Out-Null

& "$PSScriptRoot\.venv\Scripts\python.exe" "$PSScriptRoot\src\server.py"
