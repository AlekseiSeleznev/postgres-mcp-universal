$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

$DefaultPort = 8090
$Name = "postgres-universal"
$EnvPortKey = "PG_MCP_PORT"
$Container = "pg-mcp-gateway"
$CiMode = $env:MCP_SETUP_CI -eq "1"

function Get-EnvValue {
    param([string]$Key, [string]$Path)
    if (-not (Test-Path $Path)) { return $null }
    $line = Get-Content $Path | Where-Object { $_ -match "^$([regex]::Escape($Key))=" } | Select-Object -First 1
    if ($null -eq $line) { return $null }
    return $line.Substring($Key.Length + 1)
}

function Set-EnvValue {
    param([string]$Key, [string]$Value, [string]$Path)
    $lines = @()
    if (Test-Path $Path) {
        $lines = Get-Content $Path
    }
    $updated = $false
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match "^$([regex]::Escape($Key))=") {
            $lines[$i] = "$Key=$Value"
            $updated = $true
        }
    }
    if (-not $updated) {
        $lines += "$Key=$Value"
    }
    Set-Content -Path $Path -Value $lines -Encoding UTF8
}

Write-Host "── Checking prerequisites ──────────────────────────────────"

$dockerCmd = Get-Command docker -ErrorAction SilentlyContinue
if ($null -eq $dockerCmd) {
    throw "docker not found. Install Docker Desktop and retry."
}
Write-Host "  ✓ docker found"

& docker compose version *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Docker Compose V2 not found. Install Docker Desktop / Compose V2 and retry."
}
Write-Host "  ✓ docker compose found"

& docker info *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Docker daemon is not running. Start Docker Desktop and retry."
}
Write-Host "  ✓ Docker daemon is running"

$codexCmd = Get-Command codex -ErrorAction SilentlyContinue
$codexFound = $null -ne $codexCmd
if ($codexFound) {
    Write-Host "  ✓ codex CLI found"
} else {
    Write-Host "  ✗ codex CLI not found — MCP will not be registered automatically"
}

$legacyOverride = Join-Path $repoRoot "docker-compose.override.yml"
if (Test-Path $legacyOverride) {
    $legacyText = Get-Content $legacyOverride -Raw
    if ($legacyText -match "Auto-generated for .*host mode unsupported") {
        Remove-Item $legacyOverride -Force
        Write-Host "[i] Removed legacy docker-compose.override.yml from older install flow"
    }
}

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "[+] Created .env from .env.example"
} else {
    Write-Host "[i] .env already exists, keeping it"
}
Set-EnvValue -Key "PG_MCP_API_KEY" -Value "" -Path ".env"
Write-Host "[+] Disabled dashboard/API bearer auth (PG_MCP_API_KEY is empty)"

$port = Get-EnvValue -Key $EnvPortKey -Path ".env"
if ([string]::IsNullOrWhiteSpace($port)) {
    $port = "$DefaultPort"
}

$exactContainerId = (& docker ps -aq --filter "name=^/$Container$" 2>$null)
if (-not [string]::IsNullOrWhiteSpace($exactContainerId)) {
    Write-Host "[i] Removing stale container with exact name $Container before compose up"
    & docker rm -f $Container *> $null
}

Write-Host "[*] Building and starting container (restart: always — survives reboots)..."
& docker compose up -d --build --remove-orphans
if ($LASTEXITCODE -ne 0) {
    throw "docker compose up failed"
}

Write-Host "[*] Waiting for gateway to be healthy..."
$healthy = $false
for ($i = 0; $i -lt 30; $i++) {
    try {
        $resp = Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 -Uri "http://localhost:$port/health"
        if ($resp.StatusCode -eq 200) {
            $healthy = $true
            break
        }
    } catch {
        Start-Sleep -Seconds 1
    }
}

if (-not $healthy) {
    try {
        $status = & docker inspect --format='{{.State.Health.Status}}' $Container 2>$null
        if ($status -eq "healthy") {
            $healthy = $true
        }
    } catch {
    }
}

if (-not $healthy) {
    throw "Gateway not healthy after 30s. Check: docker logs $Container"
}
Write-Host "[+] Gateway is healthy on port $port"

if ($CiMode) {
    Write-Host "[i] MCP_SETUP_CI=1: skipping Codex MCP registration"
} elseif ($codexFound) {
    & codex mcp remove $Name *> $null
    & codex mcp add $Name --url "http://localhost:$port/mcp"
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to register MCP server in Codex"
    }
    Write-Host "[+] Registered '$Name' in Codex"
} else {
    Write-Host "[i] Codex CLI not found. Register manually after installing Codex:"
    Write-Host "    codex mcp add $Name --url http://localhost:$port/mcp"
}

Write-Host ""
Write-Host "── Final verification ──────────────────────────────────────"
try {
    $health = Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 -Uri "http://localhost:$port/health"
    Write-Host "  /health → $($health.Content)"
} catch {
    Write-Host "  /health → UNREACHABLE"
}

if ($codexFound -and -not $CiMode) {
    & codex mcp get $Name *> $null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  ✓ '$Name' is registered in Codex"
    } else {
        Write-Host "  ✗ '$Name' NOT found in Codex MCP config — something went wrong"
    }
}

Write-Host ""
Write-Host "════════════════════════════════════════════════════════════"
Write-Host "  Setup complete!"
Write-Host ""
if ($CiMode) {
    Write-Host "  1. Open Dashboard: http://localhost:$port/dashboard"
    Write-Host "  2. MCP registration was skipped because MCP_SETUP_CI=1"
    Write-Host "  3. Add a PostgreSQL connection via Dashboard or via MCP tool:"
} else {
    Write-Host "  1. Verify MCP registration: codex mcp get $Name"
    Write-Host "  2. Open Dashboard: http://localhost:$port/dashboard"
    Write-Host "  3. Connect any MCP client to http://localhost:$port/mcp"
    Write-Host "  4. Start Codex in your working project and use MCP server '$Name'"
    Write-Host "  5. Add a PostgreSQL connection via Dashboard or via MCP tool:"
}
Write-Host "     connect_database(name=""mydb"","
Write-Host "       connection_string=""postgresql://user:pass@host:5432/dbname"")"
Write-Host ""
Write-Host "  After reboot: container auto-starts (restart: always)."
Write-Host "  Codex registration remains in the local Codex MCP configuration."
Write-Host "════════════════════════════════════════════════════════════"
