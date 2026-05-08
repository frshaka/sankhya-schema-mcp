$envFile = Join-Path $PSScriptRoot ".env"
Get-Content $envFile | ForEach-Object {
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

& "$PSScriptRoot\.venv\Scripts\python.exe" "$PSScriptRoot\src\server.py"
