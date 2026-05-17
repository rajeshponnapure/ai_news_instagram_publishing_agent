# Step-by-Step Setup

Project folder:

```text
C:\Users\saimo\OneDrive\Desktop\projects\AI_Instagram_News_Agent
```

## Zero-budget cloud automation

If you want the agent to publish to Instagram with no paid hosting, use the free Cloudflare Tunnel path first.

```powershell
winget install Cloudflare.cloudflared
powershell -ExecutionPolicy Bypass -File .\scripts\run_free_auto_publish.ps1
```

This exposes the generated carousel images through a temporary public HTTPS URL so Instagram can fetch them automatically.

## 1. Enable Gmail IMAP

1. Open Gmail in your browser.
2. Go to Settings.
3. Open "See all settings".
4. Open "Forwarding and POP/IMAP".
5. Enable IMAP.
6. Save changes.

## 2. Create a Gmail App Password

1. Open your Google Account security page.
2. Turn on 2-Step Verification if it is not enabled.
3. Search for "App passwords".
4. Create an app password for this local agent.
5. Copy the generated password.

Use the app password only in `.env`. Do not use your normal Gmail password.

## 3. Fill the `.env` file

Open:

```text
C:\Users\saimo\OneDrive\Desktop\projects\AI_Instagram_News_Agent\.env
```

Fill these lines:

```env
IMAP_USERNAME=your_email@gmail.com
IMAP_PASSWORD=your_gmail_app_password
EMAIL_SENDER_FILTER=grdevelopers.co@gmail.com
```

Keep these values:

```env
IMAP_HOST=imap.gmail.com
IMAP_PORT=993
POLL_INTERVAL_MINUTES=1
SUMMARY_PROVIDER=auto
PROCESS_ALL_MATCHING=false
MAX_EMAILS_PER_RUN=20
CREATE_INSTAGRAM_POSTS=true
```

## 4. Test without Gmail

Open PowerShell inside the project folder:

```powershell
cd "C:\Users\saimo\OneDrive\Desktop\projects\AI_Instagram_News_Agent"
python -m email_summary_agent --sample
```

Check:

```text
reports\latest.md
```

## 5. Test with Gmail

After `.env` is filled:

```powershell
python -m email_summary_agent --once --all
```

If it works, the agent will read emails from `grdevelopers.co@gmail.com`, summarize unprocessed emails, write `reports\latest.md`, and create Instagram carousel assets under `reports\instagram_posts`.

To rebuild everything from the sender again:

```powershell
python -m email_summary_agent --once --all --reprocess
```

## 6. Run every 15 minutes

Simple terminal mode:

```powershell
python -m email_summary_agent --watch-new
```

Windows Task Scheduler mode:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_email_summary_watch.ps1
```

Create a Task Scheduler task that runs that command at startup or on logon.

One-time registration shortcut:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\register_ai_instagram_tasks.ps1 -IncludeWatcherOnly
```

If you are using the free auto-publish flow, leave only the auto-publish task enabled. Do not enable both tasks unless you want a separate reports-only watcher.

## 7. What to check

- `reports\latest.md` has the newest summary report.
- `reports\instagram_posts` has carousel folders with PNG slides and captions.
- `data\agent.sqlite3` remembers processed emails.
- `logs\email_summary_agent.log` stores Task Scheduler runs.
- Running the same Gmail pass twice should skip already processed emails.

## 8. GitHub Actions option

If you want the automation to run in the cloud instead of only on your PC, add the repository secrets below in GitHub:

- `IMAP_USERNAME`
- `IMAP_PASSWORD`
- `IG_USER_ID`
- `IG_ACCESS_TOKEN`

Then enable the workflow at `.github/workflows/instagram-auto-publish.yml`.

The workflow:

1. Runs every 5 minutes.
2. Reads new email from Gmail.
3. Generates the report and Instagram carousel.
4. Publishes through a temporary tunnel.
5. Commits `data/agent.sqlite3` and `reports/latest.md` back to the repo so the same mail is not processed twice.

This is the recommended cloud version if you want the system to keep working even when your own PC is off.
