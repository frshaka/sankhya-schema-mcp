$env:SANKHYA_DB_HOST = "localhost"
$env:SANKHYA_DB_PORT = "1521"
$env:SANKHYA_DB_SERVICE = "XE"
$env:SANKHYA_DB_USER = "SANKHYA"
$env:SANKHYA_DB_PASSWORD = "developer"

& "$PSScriptRoot\.venv\Scripts\python.exe" "$PSScriptRoot\src\server.py"
