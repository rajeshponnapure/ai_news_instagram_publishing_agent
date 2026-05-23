# push_graitech_update.ps1
# Right-click this file and choose "Run with PowerShell"

Set-Location $PSScriptRoot

Write-Host "Graitech Design System - Push Changes" -ForegroundColor Cyan

# Remove stale git lock if present
$lock = ".git\index.lock"
if (Test-Path $lock) {
    Remove-Item $lock -Force
    Write-Host "Removed stale git lock." -ForegroundColor Yellow
}

# Stage changed files
git add "email_summary_agent\instagram.py"
git add "email_summary_agent\assets\"
git add "scripts\publish_latest_instagram.py"

git status --short

# Commit
git commit -m "feat: apply graitech design system, fix duplicates, add article scraping"

# Push
Write-Host "Pushing to origin/main..." -ForegroundColor Cyan
git push origin main

if ($LASTEXITCODE -eq 0) {
    Write-Host "SUCCESS - changes pushed. GitHub Actions will run the new design." -ForegroundColor Green
} else {
    Write-Host "Push failed. Try running: git push origin main" -ForegroundColor Red
}

Read-Host "Press Enter to exit"
