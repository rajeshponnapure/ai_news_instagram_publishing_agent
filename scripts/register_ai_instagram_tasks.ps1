[CmdletBinding()]
param(
    [switch]$Force,
    [switch]$IncludeWatcherOnly
)

$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $PSScriptRoot
$PowerShellExe = (Get-Command powershell.exe).Source
$WatcherScript = Join-Path $Root 'scripts\run_email_summary_watch.ps1'
$AutoPublishScript = Join-Path $Root 'scripts\run_free_auto_publish.ps1'
$StartupFolder = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Startup'

function Register-StartupLauncher {
    param(
        [Parameter(Mandatory = $true)][string]$TaskName,
        [Parameter(Mandatory = $true)][string]$ScriptPath,
        [Parameter(Mandatory = $true)][string]$Description
    )

    if (-not (Test-Path $StartupFolder)) {
        New-Item -ItemType Directory -Path $StartupFolder -Force | Out-Null
    }

    $launcherPath = Join-Path $StartupFolder (($TaskName -replace '[^A-Za-z0-9_-]', '_') + '.cmd')
    $launcherText = @"
@echo off
cd /d "$Root"
"$PowerShellExe" -NoProfile -ExecutionPolicy Bypass -File "$ScriptPath"
"@

    [System.IO.File]::WriteAllText($launcherPath, $launcherText, [System.Text.Encoding]::ASCII)
    Write-Host "Task Scheduler access is blocked, so added a Startup folder launcher instead: $launcherPath"
    Write-Host $Description
}

function Register-StartupTask {
    param(
        [Parameter(Mandatory = $true)][string]$TaskName,
        [Parameter(Mandatory = $true)][string]$ScriptPath,
        [Parameter(Mandatory = $true)][string]$Description
    )

    $taskCommand = "$PowerShellExe -NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`""
    & schtasks.exe /Create /SC ONLOGON /TN $TaskName /TR $taskCommand /RL LIMITED /F | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Register-StartupLauncher -TaskName $TaskName -ScriptPath $ScriptPath -Description $Description
        return
    }

    Write-Host "Registered scheduled task: $TaskName"
}

if (-not (Test-Path $AutoPublishScript)) {
    throw "Missing script: $AutoPublishScript"
}

Register-StartupTask -TaskName 'AI News Instagram Auto Publish' -ScriptPath $AutoPublishScript -Description 'Starts the free Cloudflare Tunnel, serves public media, and auto-publishes new Instagram carousels.'

if ($IncludeWatcherOnly) {
    if (-not (Test-Path $WatcherScript)) {
        throw "Missing script: $WatcherScript"
    }
    Register-StartupTask -TaskName 'AI News Email Watcher' -ScriptPath $WatcherScript -Description 'Watches the inbox and generates reports for new AI news mail.'
}

Write-Host 'Scheduled task(s) registered successfully.'
Write-Host 'Open Task Scheduler to verify they are enabled and set to run at logon.'
