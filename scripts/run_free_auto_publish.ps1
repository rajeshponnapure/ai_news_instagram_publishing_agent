param(
    [switch]$Once
    , [switch]$PollOnce
)

$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $PSScriptRoot
$ReportsRoot = Join-Path $Root 'reports\instagram_posts'
$LogDir = Join-Path $Root 'logs'
$ServerLog = Join-Path $LogDir 'public_media_server.log'
$ServerErr = Join-Path $LogDir 'public_media_server.err.log'
$TunnelLog = Join-Path $LogDir 'cloudflared_tunnel.log'
$TunnelErr = Join-Path $LogDir 'cloudflared_tunnel.err.log'
$AgentLog = Join-Path $LogDir 'instagram_auto_publish.log'

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
New-Item -ItemType Directory -Force -Path $ReportsRoot | Out-Null
Set-Location $Root

Write-Host "[auto-publish] Starting in $Root"

$cloudflared = Get-Command cloudflared -ErrorAction SilentlyContinue
if (-not $cloudflared) {
    $machinePath = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    if ($machinePath) {
        $env:Path = $machinePath + ';' + $env:Path
        $cloudflared = Get-Command cloudflared -ErrorAction SilentlyContinue
    }
}

if (-not $cloudflared) {
    $candidatePaths = @(
        'C:\Program Files\Cloudflare\Cloudflared\cloudflared.exe',
        'C:\Program Files (x86)\Cloudflare\Cloudflared\cloudflared.exe',
        "$env:LOCALAPPDATA\Microsoft\WinGet\Links\cloudflared.exe"
    )
    foreach ($candidate in $candidatePaths) {
        if (Test-Path $candidate) {
            $cloudflared = [pscustomobject]@{ Source = $candidate }
            break
        }
    }
}

if (-not $cloudflared) {
    throw 'cloudflared is not installed or not visible yet. Reopen PowerShell after winget install Cloudflare.cloudflared, or use the common install path if it exists.'
}

Write-Host "[auto-publish] cloudflared: $($cloudflared.Source)"

$pythonServerArgs = @(
    '-m', 'http.server', '8088',
    '--bind', '127.0.0.1',
    '--directory', $ReportsRoot
)
$serverProcess = Start-Process -FilePath 'python' -ArgumentList $pythonServerArgs -PassThru -WindowStyle Hidden -RedirectStandardOutput $ServerLog -RedirectStandardError $ServerErr
Write-Host "[auto-publish] Local media server PID: $($serverProcess.Id)"

$tunnelArgs = @('tunnel', '--url', 'http://127.0.0.1:8088')
$tunnelProcess = Start-Process -FilePath $cloudflared.Source -ArgumentList $tunnelArgs -PassThru -WindowStyle Hidden -RedirectStandardOutput $TunnelLog -RedirectStandardError $TunnelErr
Write-Host "[auto-publish] Tunnel process PID: $($tunnelProcess.Id)"

try {
    $publicRoot = $null
    $deadline = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $deadline -and -not $publicRoot) {
        if (Test-Path $TunnelErr) {
            $tunnelText = Get-Content -Path $TunnelErr -Raw -ErrorAction SilentlyContinue
            if ($tunnelText) {
                $match = [regex]::Match($tunnelText, 'https://[a-zA-Z0-9-]+\.trycloudflare\.com')
                if ($match.Success) {
                    $publicRoot = $match.Value
                }
            }
        }
        if (-not $publicRoot) { Start-Sleep -Milliseconds 500 }
    }

    if (-not $publicRoot) {
        throw "Could not detect the Cloudflare Tunnel URL within timeout. Check $TunnelErr"
    }

    Write-Host "[auto-publish] Public media root: $publicRoot"

    $env:PUBLIC_MEDIA_BASE_URL = $publicRoot
    $env:AUTO_PUBLISH_INSTAGRAM = 'true'
    $env:PYTHONIOENCODING = 'utf-8'
    $env:PYTHONUTF8 = '1'

    $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    "[$stamp] Public media root: $publicRoot" | Out-File -Append -FilePath $AgentLog -Encoding utf8
    "[$stamp] Starting watch-new with auto-publish enabled." | Out-File -Append -FilePath $AgentLog -Encoding utf8

    $agentArgs = if ($PollOnce) { @('-u', '-m', 'email_summary_agent', '--poll-once') } elseif ($Once) { @('-u', '-m', 'email_summary_agent', '--test-latest') } else { @('-u', '-m', 'email_summary_agent', '--watch-new') }
    $modeLabel = if ($PollOnce) { 'poll-once' } elseif ($Once) { 'test-latest' } else { 'watch-new' }
    Write-Host "[auto-publish] Running agent mode: $modeLabel"
    python @agentArgs 2>&1 | Tee-Object -FilePath $AgentLog -Append
    $agentExit = $LASTEXITCODE
    Write-Host "[auto-publish] Agent exit code: $agentExit"
    if ($agentExit -ne 0) {
        throw "Agent exited with code $agentExit. See $AgentLog"
    }
}
finally {
    if ($tunnelProcess -and -not $tunnelProcess.HasExited) {
        Stop-Process -Id $tunnelProcess.Id -Force -ErrorAction SilentlyContinue
    }
    if ($serverProcess -and -not $serverProcess.HasExited) {
        Stop-Process -Id $serverProcess.Id -Force -ErrorAction SilentlyContinue
    }
    Write-Host "[auto-publish] Cleaned up tunnel/server processes."
}
