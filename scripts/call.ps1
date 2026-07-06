# Trigger an outbound test call via ngrok /start
# Usage: .\scripts\call.ps1 +919876543210 "Test Lead" "Pune"

param(
    [Parameter(Mandatory = $true)][string]$Phone,
    [string]$Name = "Sir/Madam",
    [string]$City = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

# Load NGROK_URL from .env
$ngrokUrl = $null
Get-Content .env | ForEach-Object {
    if ($_ -match '^NGROK_URL=(.+)$') { $ngrokUrl = $matches[1].Trim() }
}
if (-not $ngrokUrl) { throw "NGROK_URL not set in .env" }

$body = @{
    phone_number = $Phone
    body = @{
        lead_name = $Name
        city = $City
    }
} | ConvertTo-Json -Depth 3

Write-Host "Calling $Phone via $ngrokUrl/start ..." -ForegroundColor Cyan
$response = Invoke-RestMethod -Method POST -Uri "$ngrokUrl/start" `
    -ContentType "application/json" `
    -Body $body `
    -Headers @{ "ngrok-skip-browser-warning" = "true" }

$response | ConvertTo-Json -Depth 5
