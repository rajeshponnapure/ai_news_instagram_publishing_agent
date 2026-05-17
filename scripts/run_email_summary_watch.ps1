$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $Root "logs"
$LogFile = Join-Path $LogDir "email_summary_agent_watch.log"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
Set-Location $Root
$Stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

"--------------------------------------------------" | Out-File -Append -FilePath $LogFile -Encoding utf8
"[$Stamp] Starting live AI inbox watcher..." | Out-File -Append -FilePath $LogFile -Encoding utf8

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$env:POLL_INTERVAL_MINUTES = "1"
python -u -m email_summary_agent --watch-new 2>&1 | Out-File -Append -FilePath $LogFile -Encoding utf8
