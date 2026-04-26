#requires -Version 7.0
[CmdletBinding()]
param(
    [int]$Port = [int]($env:PG_MCP_SMOKE_PORT ?? "18091"),
    [string]$McpPath = "/mcp",
    [int]$StartupTimeoutSeconds = 20
)

$ErrorActionPreference = "Stop"

function Resolve-RepoRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot ".." "..")).Path
}

function Resolve-Python {
    $candidates = @()
    if ($env:PYTHON) {
        $candidates += $env:PYTHON
    }
    $candidates += @("python", "python3", "py")

    foreach ($candidate in $candidates) {
        $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($null -ne $cmd) {
            return $cmd.Source
        }
    }

    throw "Python runtime not found. Set PYTHON to a Python executable with project dependencies installed."
}

function ConvertFrom-McpHttpBody {
    param([Parameter(Mandatory = $true)][string]$Body)

    $trimmed = $Body.Trim()
    if ($trimmed.StartsWith("{") -or $trimmed.StartsWith("[")) {
        return $trimmed | ConvertFrom-Json
    }

    $jsonLines = New-Object System.Collections.Generic.List[string]
    foreach ($line in ($Body -split "`r?`n")) {
        if ($line.StartsWith("data:")) {
            $payload = $line.Substring(5).Trim()
            if ($payload -and $payload -ne "[DONE]") {
                $jsonLines.Add($payload)
            }
        }
    }

    if ($jsonLines.Count -eq 0) {
        throw "MCP HTTP response did not contain JSON or SSE data. Body: $Body"
    }

    return ($jsonLines[$jsonLines.Count - 1] | ConvertFrom-Json)
}

function Invoke-McpJsonRpc {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][hashtable]$Payload,
        [hashtable]$ExtraHeaders = @{},
        [switch]$AllowEmptyResponse
    )

    $headers = @{
        "Accept" = "application/json, text/event-stream"
    }
    foreach ($key in $ExtraHeaders.Keys) {
        $headers[$key] = $ExtraHeaders[$key]
    }

    $json = $Payload | ConvertTo-Json -Depth 20 -Compress
    $response = Invoke-WebRequest `
        -Uri $Url `
        -Method Post `
        -Body $json `
        -ContentType "application/json" `
        -Headers $headers `
        -TimeoutSec 15

    $json = $null
    if ($response.Content) {
        $json = ConvertFrom-McpHttpBody -Body $response.Content
    } elseif (-not $AllowEmptyResponse) {
        throw "MCP HTTP response body is empty."
    }

    return @{
        Response = $response
        Json = $json
    }
}

function Wait-Health {
    param(
        [Parameter(Mandatory = $true)][string]$HealthUrl,
        [Parameter(Mandatory = $true)][int]$TimeoutSeconds
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        try {
            $response = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200) {
                return
            }
        } catch {
            Start-Sleep -Milliseconds 250
        }
    } while ((Get-Date) -lt $deadline)

    throw "Gateway did not become healthy at $HealthUrl within $TimeoutSeconds seconds."
}

function Start-SmokeGateway {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [Parameter(Mandatory = $true)][int]$Port
    )

    $python = Resolve-Python
    $gatewayDir = Join-Path $RepoRoot "gateway"
    $statePath = Join-Path ([System.IO.Path]::GetTempPath()) "postgres-mcp-universal-pwsh-smoke-state.json"

    Remove-Item -LiteralPath $statePath -Force -ErrorAction SilentlyContinue

    $psi = [System.Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = $python
    if ([System.IO.Path]::GetFileNameWithoutExtension($python) -eq "py") {
        $psi.ArgumentList.Add("-3")
    }
    $psi.ArgumentList.Add("-m")
    $psi.ArgumentList.Add("gateway")
    $psi.WorkingDirectory = $gatewayDir
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.Environment["PG_MCP_PORT"] = [string]$Port
    $psi.Environment["PG_MCP_STATE_FILE"] = $statePath
    $psi.Environment["PG_MCP_DATABASE_URI"] = ""
    $psi.Environment["PG_MCP_API_KEY"] = ""
    $psi.Environment["PG_MCP_RATE_LIMIT_ENABLED"] = "false"
    $psi.Environment["PYTHONUNBUFFERED"] = "1"

    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $psi
    [void]$process.Start()

    return @{
        Process = $process
        StatePath = $statePath
    }
}

$repoRoot = Resolve-RepoRoot
$baseUrl = "http://127.0.0.1:$Port"
$healthUrl = "$baseUrl/health"
$mcpUrl = "$baseUrl$McpPath"
$gateway = $null

try {
    Write-Host "Starting safe postgres-mcp-universal smoke gateway on $baseUrl"
    $gateway = Start-SmokeGateway -RepoRoot $repoRoot -Port $Port

    try {
        Wait-Health -HealthUrl $healthUrl -TimeoutSeconds $StartupTimeoutSeconds
    } catch {
        if ($gateway.Process.HasExited) {
            $stdout = $gateway.Process.StandardOutput.ReadToEnd()
            $stderr = $gateway.Process.StandardError.ReadToEnd()
            throw "Gateway exited early. STDOUT: $stdout STDERR: $stderr"
        }
        throw
    }

    Write-Host "Health check passed"

    $initialize = @{
        jsonrpc = "2.0"
        id = 1
        method = "initialize"
        params = @{
            protocolVersion = "2025-06-18"
            capabilities = @{}
            clientInfo = @{
                name = "postgres-mcp-universal-pwsh-smoke"
                version = "1.0.0"
            }
        }
    }
    $initResult = Invoke-McpJsonRpc -Url $mcpUrl -Payload $initialize
    if ($initResult.Json.result.serverInfo.name -ne "postgres-mcp-universal") {
        throw "Unexpected server name in initialize response: $($initResult.Json.result.serverInfo.name)"
    }

    $sessionId = $initResult.Response.Headers["Mcp-Session-Id"]
    if (-not $sessionId) {
        $sessionId = $initResult.Response.Headers["mcp-session-id"]
    }
    if (-not $sessionId) {
        throw "MCP initialize response did not include Mcp-Session-Id header."
    }

    Write-Host "MCP initialize passed"

    $initialized = @{
        jsonrpc = "2.0"
        method = "notifications/initialized"
        params = @{}
    }
    [void](Invoke-McpJsonRpc -Url $mcpUrl -Payload $initialized -ExtraHeaders @{"Mcp-Session-Id" = $sessionId} -AllowEmptyResponse)

    $toolsList = @{
        jsonrpc = "2.0"
        id = 2
        method = "tools/list"
        params = @{}
    }
    $toolsResult = Invoke-McpJsonRpc -Url $mcpUrl -Payload $toolsList -ExtraHeaders @{"Mcp-Session-Id" = $sessionId}
    $tools = @($toolsResult.Json.result.tools)
    if ($tools.Count -ne 23) {
        throw "Expected 23 tools, got $($tools.Count)."
    }

    $toolNames = @($tools | ForEach-Object { $_.name })
    foreach ($required in @("list_databases", "get_server_status", "list_schemas", "execute_sql")) {
        if ($toolNames -notcontains $required) {
            throw "Required tool '$required' not found in tools/list response."
        }
    }

    Write-Host "MCP tools/list passed with $($tools.Count) tools"
    Write-Host "PowerShell MCP smoke passed"
} finally {
    if ($null -ne $gateway) {
        if (-not $gateway.Process.HasExited) {
            $gateway.Process.Kill($true)
        }
        $gateway.Process.Dispose()
        Remove-Item -LiteralPath $gateway.StatePath -Force -ErrorAction SilentlyContinue
    }
}
