param(
    [string]$Email,
    [string]$FamilyName = 'Ma famille'
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
New-Item -ItemType Directory -Force -Path 'data/archive' | Out-Null
$localDatabase = (Join-Path $projectRoot 'data/dev.db').Replace('\', '/')
$env:CLAIRE_DATABASE_URL = "sqlite:///$localDatabase"
Remove-Item Env:CLAIRE_DATABASE_URL_FILE -ErrorAction SilentlyContinue
$env:CLAIRE_ORIGIN = 'http://localhost:8000'
$env:CLAIRE_SECURE_COOKIES = 'false'
$env:CLAIRE_DATA_DIR = Join-Path $projectRoot 'data/archive'
$env:CLAIRE_STATIC_DIR = Join-Path $projectRoot 'apps/frontend/dist'

uv run --frozen alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw 'Database migration failed.' }
Push-Location 'apps/frontend'
try {
    npm.cmd ci
    if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
    npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
} finally { Pop-Location }

if ($Email) {
    uv run --frozen python -m claire.cli $Email --family-name $FamilyName --role family_admin
    if ($LASTEXITCODE -ne 0) { throw 'Account creation failed. Omit -Email if your account already exists.' }
}
Write-Host 'CLAIRE: http://localhost:8000 — local evaluation, SQLite database preserved in data/dev.db'
uv run --frozen uvicorn claire.main:create_app --factory --host 127.0.0.1 --port 8000
