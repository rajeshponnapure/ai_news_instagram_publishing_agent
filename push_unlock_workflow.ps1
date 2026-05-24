# push_unlock_workflow.ps1
# Fixes the concurrency lock that blocks cron runs.
# Right-click → Run with PowerShell

Set-Location $PSScriptRoot

$lock = ".git\index.lock"
if (Test-Path $lock) { Remove-Item $lock -Force }

git add ".github\workflows\instagram-auto-publish.yml"
git status --short
git commit -m "fix: cancel-in-progress true to prevent cron blocking"
git push origin main

if ($LASTEXITCODE -eq 0) {
    Write-Host "Pushed. Now go to GitHub Actions and CANCEL any stuck run manually." -ForegroundColor Green
    Write-Host "After that, cron will resume every 15 minutes automatically." -ForegroundColor Cyan
} else {
    Write-Host "Push failed. Run: git push origin main" -ForegroundColor Red
}

Read-Host "Press Enter to exit"
