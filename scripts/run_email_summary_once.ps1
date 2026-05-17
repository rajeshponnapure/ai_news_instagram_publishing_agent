$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $Root "logs"
$LogFile = Join-Path $LogDir "email_summary_agent.log"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
Set-Location $Root
$Stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

# Force everything to use UTF-8 encoding so PowerShell and Python don't fight
"--------------------------------------------------" | Out-File -Append -FilePath $LogFile -Encoding utf8
"[$Stamp] Waking up to check for AI news..." | Out-File -Append -FilePath $LogFile -Encoding utf8

# Run Python and pipe all output directly into the log file safely
$env:PYTHONIOENCODING="utf-8"
$env:PYTHONUTF8="1"
python -u -m email_summary_agent --once --all 2>&1 | Out-File -Append -FilePath $LogFile -Encoding utf8
