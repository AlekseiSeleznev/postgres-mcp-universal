$ErrorActionPreference = "Stop"

$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if ($null -ne $pythonCmd) {
    $pythonExe = "python"
} else {
    $python3Cmd = Get-Command python3 -ErrorAction SilentlyContinue
    if ($null -ne $python3Cmd) {
        $pythonExe = "python3"
    } else {
        throw "python/python3 is unavailable; cannot run compileall smoke check"
    }
}

& $pythonExe -m compileall -q gateway

$rootGuide = "CL" + "AUDE.md"
$forbiddenBrand = "cl" + "aude"

$bashCmd = Get-Command bash -ErrorAction SilentlyContinue
if ($null -ne $bashCmd) {
    bash -n setup.sh
} else {
    Write-Host "bash is unavailable; skipping setup.sh syntax check"
}

if (-not (Test-Path "CODEX.md")) {
    throw "CODEX.md is missing"
}

if (-not (Test-Path "AGENTS.md")) {
    throw "AGENTS.md is missing"
}

if (-not (Test-Path "install.ps1")) {
    throw "install.ps1 is missing"
}

if (-not (Test-Path "gateway/requirements-dev.txt")) {
    throw "gateway/requirements-dev.txt is missing"
}

if (-not (Test-Path "install.cmd")) {
    throw "install.cmd is missing"
}

if (-not (Test-Path "uninstall.ps1")) {
    throw "uninstall.ps1 is missing"
}

if (-not (Test-Path "uninstall.cmd")) {
    throw "uninstall.cmd is missing"
}

if (-not (Test-Path $rootGuide)) {
    throw "$rootGuide is missing"
}

$setupText = Get-Content "setup.sh" -Raw
if ($setupText -notmatch "codex mcp add") {
    throw "setup.sh must register MCP via codex mcp add"
}

$installCmd = Get-Content "install.cmd" -Raw
if ($installCmd -notmatch "ExecutionPolicy Bypass") {
    throw "install.cmd must start install.ps1 with ExecutionPolicy Bypass"
}

$uninstallCmd = Get-Content "uninstall.cmd" -Raw
if ($uninstallCmd -notmatch "ExecutionPolicy Bypass") {
    throw "uninstall.cmd must start uninstall.ps1 with ExecutionPolicy Bypass"
}

$devRequirements = Get-Content "gateway/requirements-dev.txt" -Raw
if ($devRequirements -notmatch "pytest-asyncio") {
    throw "gateway/requirements-dev.txt must include pytest-asyncio"
}

$composeText = Get-Content "docker-compose.yml" -Raw
if ($composeText -match "network_mode\s*:\s*host" -or $composeText -match "network\s*:\s*host") {
    throw "docker-compose.yml must not use host networking"
}
if ($composeText -notmatch "ports:") {
    throw "docker-compose.yml must publish the MCP port explicitly"
}

$publishWorkflow = Get-Content ".github/workflows/docker-publish.yml" -Raw
if ($publishWorkflow -notmatch "platforms:\s*linux/amd64,linux/arm64") {
    throw "docker-publish workflow must build multi-arch images"
}

$trackedTexts = @(
    "README.md",
    "setup.sh",
    "gateway/gateway/web_ui_content.py",
    ".github/workflows/ci.yml",
    "CODEX.md",
    "AGENTS.md"
)

foreach ($file in $trackedTexts) {
    $text = Get-Content $file -Raw
    if ($text -match ("(?i)" + $forbiddenBrand)) {
        throw "Forbidden legacy client reference found in $file"
    }
}

if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
    } else {
        New-Item -Path ".env" -ItemType File -Force | Out-Null
    }
}

$dockerCmd = Get-Command docker -ErrorAction SilentlyContinue
if ($null -ne $dockerCmd) {
    & docker compose version *> $null
    if ($LASTEXITCODE -eq 0) {
        & docker compose -f docker-compose.yml config -q
        & docker compose -f docker-compose.yml -f docker-compose.windows.yml config -q
    } else {
        Write-Host "docker compose is unavailable on this runner; skipping compose config smoke checks"
    }
} else {
    Write-Host "docker is unavailable on this runner; skipping compose config smoke checks"
}
