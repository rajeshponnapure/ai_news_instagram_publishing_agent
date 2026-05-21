# ðŸ–¥ï¸ Local Automation Setup Guide

Complete guide to setting up the AI Instagram News Agent with **zero cloud services**, using only Windows Task Scheduler.

---

## Free GitHub Publishing

The no-billing production setup now uses GitHub Actions and GitHub Pages. The repository workflow checks Gmail every 15 minutes, generates carousel images, deploys those images to GitHub Pages, and publishes the latest carousel to Instagram using stable public Pages URLs.
---

## ðŸ” Security Considerations

### Email Credentials (.env)
- âœ… Store credentials in `.env` (not in code)
- âœ… Use Gmail App Passwords (not your main password)
- âœ… Keep `.env` file in `.gitignore`
- âœ… Never commit credentials to Git

### Task Scheduler
- Tasks run with "LIMITED" privilege by default
- Can't access system-wide resources
- Can access your user files (reports, .env)
- Consider using a dedicated non-admin service account for production

### Data Privacy
- All processing happens locally
- No data sent to external APIs (except Instagram if publishing)
- No analytics, no tracking, no third-party servers
- Full audit trail in SQLite database

---

## ðŸ› Troubleshooting

### Tasks Don't Run at Scheduled Time

```powershell
# 1. Check if task is enabled
Get-ScheduledTask -TaskName "AI Instagram*"

# 2. Check task history (look for errors)
Get-WinEvent -LogName "Microsoft-Windows-TaskScheduler/Operational" | Where-Object {$_.Message -like "*AI Instagram*"} | Format-Table TimeCreated, Message -Wrap

# 3. Verify .env file exists and is readable
Test-Path .env

# 4. Check Python path in task (should be absolute path to .venv)
Get-ScheduledTask -TaskName "AI Instagram Agent - Daily Processing" | Select-Object -ExpandProperty Actions
```

### Emails Not Being Processed

```powershell
# 1. Test email connection manually
python -c "from email_summary_agent.db import get_unprocessed_emails; import os; print(get_unprocessed_emails(os.environ))"

# 2. Check if emails are already marked as processed
sqlite3 data/agent.sqlite3 "SELECT COUNT(*) as processed FROM email_items WHERE processed_at IS NOT NULL"

# 3. Verify sender filter is correct
Get-Content .env | Select-String "EMAIL_SENDER_FILTER"
```

### Instagram Carousel Quality Issues

See [CAROUSEL_QUALITY_GUIDE.md](CAROUSEL_QUALITY_GUIDE.md) for:
- Why slides show repeated text
- How to write better email content
- Best practices for rich carousel slides

---

## âœ… Verification Checklist

After setup, verify everything works:

- [ ] `.env` file created with Gmail credentials
- [ ] Task Scheduler tasks appear in `taskschd.msc`
- [ ] Sample carousel generates: `python -m email_summary_agent --sample`
- [ ] PNG slides are created and look good
- [ ] Latest report appears in `reports/latest.md`
- [ ] Watch email feature runs without errors: `python -m email_summary_agent --watch-new` (press Ctrl+C after 30 seconds)

---

## ðŸš€ Next Steps

1. **Send yourself a test email** from the filtered sender
2. **Wait for next task trigger** (or manually run the task)
3. **Check `reports/latest.md`** for summary
4. **Check `reports/instagram_posts/`** for carousel images
5. **Verify slide quality** using [CAROUSEL_QUALITY_GUIDE.md](CAROUSEL_QUALITY_GUIDE.md)
6. **Manually post to Instagram** or enable `AUTO_PUBLISH_INSTAGRAM=true`

---

## ðŸ“ž Quick Commands Reference

```powershell
# Test email fetch
python -m email_summary_agent --once --all

# Generate sample
python -m email_summary_agent --sample

# Watch for new emails (live mode)
python -m email_summary_agent --watch-new

# Check database
sqlite3 data/agent.sqlite3 "SELECT COUNT(*) FROM email_items"

# View latest report
Get-Content reports/latest.md

# Run scheduled task now
Start-ScheduledTask -TaskName "AI Instagram Agent - Daily Processing"

# Uninstall all tasks
powershell -ExecutionPolicy Bypass -File .\scripts/reset_generated_outputs.ps1
```

---

**That's it! Your local AI Instagram News Agent is ready to roll.** ðŸš€

