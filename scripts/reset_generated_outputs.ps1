$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "This will delete generated reports, Instagram post assets, article images, and processed-email history."
$Confirm = Read-Host "Type RESET to continue"
if ($Confirm -ne "RESET") {
    Write-Host "Cancelled."
    exit 0
}

$Targets = @(
    (Join-Path $Root "reports"),
    (Join-Path $Root "data\article_assets"),
    (Join-Path $Root "data\article_assets_test")
)

foreach ($Target in $Targets) {
    if (Test-Path -LiteralPath $Target) {
        Remove-Item -LiteralPath $Target -Recurse -Force
    }
}

New-Item -ItemType Directory -Force -Path (Join-Path $Root "reports") | Out-Null

@'
import sqlite3
from pathlib import Path

db_path = Path("data/agent.sqlite3")
if db_path.exists():
    con = sqlite3.connect(db_path)
    con.execute("DELETE FROM processed_emails")
    con.execute("UPDATE runs SET status='abandoned', finished_at=datetime('now'), message='Reset from scripts/reset_generated_outputs.ps1' WHERE status='running'")
    con.commit()
    con.close()
print("Generated outputs and processed-email history reset.")
'@ | python -
