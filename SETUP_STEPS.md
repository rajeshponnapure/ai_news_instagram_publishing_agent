# Step-by-Step Setup

Project folder:

```text
C:\Users\saimo\OneDrive\Desktop\projects\AI_Instagram_News_Agent
```

## Zero-budget cloud automation

Use GitHub Actions plus GitHub Pages for the no-billing production pipeline. GitHub Actions runs every 15 minutes, checks Gmail, generates carousel assets, publishes them to GitHub Pages, and posts the latest carousel to Instagram.

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

## 6. Set Up GitHub Actions Automation

In GitHub, open the repository settings and add these Actions secrets:

```text
IMAP_USERNAME
IMAP_PASSWORD
EMAIL_SENDER_FILTER
IG_USER_ID
IG_ACCESS_TOKEN
FB_PAGE_ID                 # optional, enables Facebook Page publishing
FB_PAGE_ACCESS_TOKEN       # optional; use the Page token with pages_manage_posts
```

Then open Settings -> Pages and enable GitHub Pages for GitHub Actions. The workflow `.github/workflows/instagram-auto-publish.yml` will run every 15 minutes.
To rebuild all posts once after a reset, run the workflow manually and set `rebuild_all=true`.

### Manual Testing Before Automation

If you want to test manually first:

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

## 8. Cloud automation (removed)

This repository previously contained GitHub Actions workflows for cloud-based automation. Those workflows have been removed: this project now targets local, Windows-based automation via Task Scheduler.

If you still want cloud automation in the future, you can reintroduce a workflow that mirrors the local flow: install dependencies, run `python -m email_summary_agent --once --all`, and publish generated assets to a public host. For now, follow the Task Scheduler steps earlier to run everything locally.
