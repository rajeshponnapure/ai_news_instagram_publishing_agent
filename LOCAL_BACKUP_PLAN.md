# Local Backup Plan

If GitHub Actions does not run reliably, use this local backup path. It does not depend on GitHub scheduling and works directly on your Windows machine.

## What this backup plan does

- Checks Gmail/IMAP locally
- Processes new emails from the sender
- Generates reports in `reports/`
- Builds Instagram carousel assets locally
- Writes logs to `logs/`
- Can run once, on a schedule, or at startup

## Recommended fallback mode

Use local watch mode if you want the agent to keep checking for new mail automatically.

### Option 1: Run once manually

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_email_summary_once.ps1
```

Use this if you only want a single check right now.

### Option 2: Keep checking every minute

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_email_summary_watch.ps1
```

This keeps the agent running and checks for new emails every 1 minute by default.

### Option 3: Start automatically on login

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\register_ai_instagram_tasks.ps1 -IncludeWatcherOnly
```

This registers a startup task so the watcher starts when Windows logs in.

## Important local settings

If Instagram auto-publishing is not fully configured, keep this disabled:

```env
AUTO_PUBLISH_INSTAGRAM=false
```

If you do want Instagram auto-publishing later, make sure these are valid:

```env
PUBLIC_MEDIA_BASE_URL=https://your-public-host.example.com
IG_USER_ID=your_instagram_business_id
IG_ACCESS_TOKEN=your_meta_access_token
```

## When GitHub Actions fails

Use this order:

1. Run the one-time local script to confirm email processing still works.
2. If that works, use the watcher script for continuous polling.
3. If you want it automatic after reboot, register the startup task.
4. Keep checking `logs/` for errors.

## What to check if local runs fail

- Gmail IMAP is enabled
- `IMAP_USERNAME` is correct
- `IMAP_PASSWORD` is a Gmail app password
- `EMAIL_SENDER_FILTER` matches the sender exactly
- `AUTO_PUBLISH_INSTAGRAM` is set correctly
- Pillow is installed in the virtual environment

## Quick recovery commands

```powershell
# Run one full pass
powershell -ExecutionPolicy Bypass -File .\scripts\run_email_summary_once.ps1

# Run continuous watcher
powershell -ExecutionPolicy Bypass -File .\scripts\run_email_summary_watch.ps1

# Register startup tasks
powershell -ExecutionPolicy Bypass -File .\scripts\register_ai_instagram_tasks.ps1 -IncludeWatcherOnly
```

## Best practical backup

The safest setup is:

- GitHub Actions for automation when it works
- Local watcher as the fallback
- `AUTO_PUBLISH_INSTAGRAM=false` until your public media URL is fully ready

That way, even if GitHub Actions is delayed or broken, the agent still processes email locally.
