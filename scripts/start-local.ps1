# One-command local startup for Aakashvani (Windows)
# Usage: .\scripts\start-local.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

Write-Host "==> Starting Postgres + Redis..." -ForegroundColor Cyan
docker compose up -d postgres redis

Write-Host "==> Waiting for Postgres..." -ForegroundColor Cyan
for ($i = 1; $i -le 60; $i++) {
    docker exec aakashvani-postgres pg_isready -U aakashvani -d aakashvani 2>$null
    if ($LASTEXITCODE -eq 0) { break }
    Start-Sleep -Seconds 1
}

Write-Host "==> Running migrations..." -ForegroundColor Cyan
uv run alembic upgrade head

Write-Host "==> Seeding dev tenant (idempotent)..." -ForegroundColor Cyan
Get-Content db\seed\dev_tenant.sql -Raw | docker exec -i aakashvani-postgres psql -U aakashvani -d aakashvani -v ON_ERROR_STOP=1 | Out-Null

Write-Host "==> Starting backend on :7860..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$Root'; uv run uvicorn server:app --host 0.0.0.0 --port 7860 --reload"

Write-Host "==> Starting frontend on :5173..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$Root\frontend'; npm run dev"



Write-Host ""
Write-Host "Ready:" -ForegroundColor Green
Write-Host "  Backend:  http://localhost:7860/docs"
Write-Host "  Frontend: http://localhost:5173"
Write-Host "  Admin:    http://localhost:5173/admin/login  (key: dev-admin-key-123)"
Write-Host "  Client:   http://localhost:5173/login       (key: aakashvani_dev_key_change_me)"
Write-Host "All services started successfully!" -ForegroundColor Cyan
