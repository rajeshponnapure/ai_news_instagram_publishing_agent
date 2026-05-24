# push_graitech_update.ps1
# Right-click this file and choose "Run with PowerShell"

Set-Location $PSScriptRoot

Write-Host "Graitech Design System - Push All Changes" -ForegroundColor Cyan

# Remove stale git lock if present
$lock = ".git\index.lock"
if (Test-Path $lock) {
    Remove-Item $lock -Force
    Write-Host "Removed stale git lock." -ForegroundColor Yellow
}

# Core agent files
git add "email_summary_agent\instagram.py"
git add "email_summary_agent\agent.py"
git add "email_summary_agent\publisher.py"
git add "email_summary_agent\email_client.py"
git add "email_summary_agent\article_enricher.py"

# New Playwright renderer
git add "email_summary_agent\renderer.py"

# Graitech Design System assets (fonts + texture + logo)
git add "email_summary_agent\assets\graitech\"

# Publish script + workflow
git add "scripts\publish_latest_instagram.py"
git add ".github\workflows\instagram-auto-publish.yml"

git status --short

git commit -m "feat: Playwright HTML renderer, graitech assets, fix skip logging"

Write-Host "Pushing to origin/main..." -ForegroundColor Cyan
git push origin main

if ($LASTEXITCODE -eq 0) {
    Write-Host "SUCCESS - changes pushed. GitHub Actions will use the new design." -ForegroundColor Green
} else {
    Write-Host "Push failed. Try running: git push origin main" -ForegroundColor Red
}

Read-Host "Press Enter to exit"
