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

$NgrokExe = "$env:APPDATA\npm\node_modules\ngrok\bin\ngrok.exe"
if (Test-Path $NgrokExe) {
    Write-Host "==> Starting ngrok tunnel to :7860..." -ForegroundColor Cyan
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "& '$NgrokExe' http 7860"
    Start-Sleep -Seconds 3
    try {
        $tunnels = Invoke-RestMethod http://localhost:4040/api/tunnels
        $url = $tunnels.tunnels[0].public_url
        Write-Host ""
        Write-Host "Ngrok URL: $url" -ForegroundColor Green
        Write-Host "Update NGROK_URL in .env if you want Plivo callbacks on this tunnel." -ForegroundColor Yellow
    } catch {
        Write-Host "Ngrok started — check http://localhost:4040 for the public URL" -ForegroundColor Yellow
    }
} else {
    Write-Host "Ngrok not found — install with: npm install -g ngrok" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Ready:" -ForegroundColor Green
Write-Host "  Backend:  http://localhost:7860/docs"
Write-Host "  Frontend: http://localhost:5173"
Write-Host "  Admin:    http://localhost:5173/admin/login  (key: dev-admin-key-123)"
Write-Host "  Client:   http://localhost:5173/login       (key: aakashvani_dev_key_change_me)"
