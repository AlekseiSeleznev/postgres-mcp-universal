$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

$Name = "postgres-universal"

Write-Host "[*] Stopping and removing project Docker artifacts..."
& docker compose down -v --rmi local
if ($LASTEXITCODE -ne 0) {
    Write-Host "[i] docker compose down returned non-zero; continuing cleanup"
}

$legacyOverride = Join-Path $repoRoot "docker-compose.override.yml"
if (Test-Path $legacyOverride) {
    Remove-Item $legacyOverride -Force
    Write-Host "[+] Removed docker-compose.override.yml"
}

if (Test-Path ".env") {
    Remove-Item ".env" -Force
    Write-Host "[+] Removed .env"
}

$codexCmd = Get-Command codex -ErrorAction SilentlyContinue
if ($null -ne $codexCmd) {
    Write-Host "[*] Removing Codex MCP registration..."
    & codex mcp remove $Name
}

Write-Host ""
Write-Host "Cleanup complete."
Write-Host "If you also want to delete the repository directory, close shells inside it and remove:"
Write-Host "  $repoRoot"
