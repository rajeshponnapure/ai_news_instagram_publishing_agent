# GitHub Actions Setup Guide

> **Last updated**: Workflow redesigned — GitHub Pages removed, raw GitHub URLs used instead. Schedule changed to hourly.

## Architecture

```
[Gmail inbox]
      │  new email from grdevelopers.co@gmail.com
      ▼
┌─────────────────────────────────────────────────────┐
│  JOB 1 — generate  (runs every hour, ~50 min)       │
│                                                     │
│  1. Poll Gmail for new AI-news emails               │
│  2. Scrape article images (Playwright + Chromium)   │
│  3. Summarise → extract key points                  │
│  4. Render Instagram carousel PNGs (black bg,       │
│     neon-green headings, @graitech handle)          │
│  5. Write manifest with raw GitHub content URLs     │
│  6. Commit slides + manifest to repo                │
└───────────────────┬─────────────────────────────────┘
                    │  only runs when new slides were committed
                    ▼
┌─────────────────────────────────────────────────────┐
│  JOB 2 — publish  (runs ~5-10 min after generate)   │
│                                                     │
│  1. Pull the committed slides                       │
│  2. Wait 15 s for GitHub CDN propagation            │
│  3. POST to Instagram Graph API (carousel + Story)  │
│  4. POST to Facebook Page (if configured)           │
│  5. Commit publish status back to repo              │
└─────────────────────────────────────────────────────┘
```

Images are served from `raw.githubusercontent.com` — **no GitHub Pages required**.
The repository **must be public** for Instagram to reach the image URLs.

---

## One-Time Setup

### 1. Make the repository public
**Settings → Danger Zone → Change visibility → Public**

If the repo must stay private, you need an external image host (Cloudinary, S3, etc.).

### 2. Add GitHub Secrets
**Settings → Secrets and variables → Actions → New repository secret**

| Secret | Value | Required |
|---|---|---|
| `IMAP_USERNAME` | Your Gmail address | ✅ |
| `IMAP_PASSWORD` | Gmail **App Password** (not your login password) | ✅ |
| `EMAIL_SENDER_FILTER` | Sender to watch (e.g. `grdevelopers.co@gmail.com`) | ✅ |
| `IG_USER_ID` | Numeric Instagram Business/Creator user ID | ✅ |
| `IG_ACCESS_TOKEN` | Long-lived Instagram Graph API access token | ✅ |
| `FB_PAGE_ID` | Facebook Page numeric ID | ⬜ optional |
| `FB_PAGE_ACCESS_TOKEN` | Facebook Page access token | ⬜ optional |

**Gmail App Password**: myaccount.google.com → Security → App Passwords → Mail

**Instagram token**: Create a Meta Developer app, add Instagram Graph API, connect your Business/Creator account, generate a long-lived token with `instagram_basic` + `instagram_content_publish` permissions.

### 3. Enable workflow write permissions
**Settings → Actions → General → Workflow permissions → Read and write** ✅

---

## Schedule

Runs **every hour on the hour** (`0 * * * *`). Each run checks whether enough time has passed since the last email scan (`EMAIL_CHECK_INTERVAL_MINUTES=55`). If no new email, exits in seconds.

**Manual trigger**: Actions → Instagram Auto Publish → Run workflow

| Mode | What it does |
|---|---|
| `normal` | Same as scheduled — new mail only |
| `backfill_24h` | Reprocesses recent sender mail |
| `rebuild_all` | Reprocesses every matching inbox email |

---

## Instagram Caption Structure

Every post caption contains:
1. Hook line (punchy, <125 chars)
2. Swipe prompt (drives carousel engagement)
3. Lead paragraph (2–3 sentence summary)
4. Key-point bullets (3–5 takeaways with emojis)
5. Closing question (drives comments)
6. Save-bait line (boosts algorithm reach)
7. **ALL source article URLs** (from the original email)
8. 15–20 hashtags (niche + company + broad mix)
9. Disclaimer + attribution (always shown, with topic-specific warnings)

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| "No new content" every run | Check `IMAP_USERNAME`, `IMAP_PASSWORD`, `EMAIL_SENDER_FILTER` secrets |
| Instagram returns 404 for images | Repo must be **public** |
| "IG_ACCESS_TOKEN invalid/expired" | Refresh token — Instagram tokens expire every 60 days |
| Workflow takes >50 min | Reduce `MAX_ARTICLE_LINKS_PER_EMAIL` to 20 |
| CI tests fail | CI runs with `--sample` (no real email/Instagram calls needed) |

---

## Output File Layout

```
reports/instagram_posts/
  20260522-140000/               ← batch (one per hourly run)
    01_20260522-1400_ai-news/    ← carousel (one per email)
      slide_01.png               ← cover: full title + article image
      slide_02.png               ← key-point slide
      ...
      caption.txt                ← full caption with ALL source links
      metadata.json
    publish_manifest.json        ← publish status

data/agent.sqlite3               ← processed emails + used images
```

---

## Previous Overview (original content below)

1. **Process AI News Emails** (`process-emails-scheduled.yml`) - Runs every 15 minutes
2. **CI Code Quality** (`ci-tests.yml`) - Validates code on push/PR
3. **Validate Documentation** (`validate-docs.yml`) - Checks documentation

---

## 🔐 Configure Secrets (REQUIRED)

For the automated email processing workflow to work, you must configure GitHub secrets with your email credentials.

### Step 1: Navigate to Repository Secrets

1. Go to your GitHub repository: **https://github.com/Rajeshponnapure/ai_news_instagram_publishing_agent**
2. Click **Settings** (top right)
3. In the left sidebar, click **Secrets and variables** → **Actions**
4. You'll see any existing secrets

### Step 2: Add Required Secrets

Click **New repository secret** and add these:

#### ✅ Email Configuration (MUST HAVE)

| Secret Name | Value | Example |
|------------|-------|---------|
| `IMAP_HOST` | Gmail IMAP server | `imap.gmail.com` |
| `IMAP_PORT` | Port number | `993` |
| `IMAP_USERNAME` | Your Gmail address | `your_email@gmail.com` |
| `IMAP_PASSWORD` | Gmail app password | `xxxx xxxx xxxx xxxx` |
| `EMAIL_SENDER_FILTER` | News sender email | `grdevelopers.co@gmail.com` |

#### 📧 Email Processing Options (Optional)

| Secret Name | Default | Description |
|------------|---------|-------------|
| `EMAIL_FOLDER` | `INBOX` | Gmail folder to monitor |
| `LOOKBACK_HOURS` | `24` | Hours to search back |
| `POLL_INTERVAL_MINUTES` | `1` | Minutes between checks |
| `PROCESS_ALL_MATCHING` | `false` | Process all or just new |
| `MAX_EMAILS_PER_RUN` | `20` | Max emails per execution |

#### 📝 Content Generation (Optional)

| Secret Name | Default | Description |
|------------|---------|-------------|
| `SUMMARY_PROVIDER` | `auto` | Use `auto`, `ollama`, or `builtin` |
| `CREATE_INSTAGRAM_POSTS` | `true` | Generate Instagram carousels |
| `ENRICH_ARTICLES` | `true` | Fetch full article content |

#### 🤖 Ollama (Optional - for better AI)

| Secret Name | Default | Description |
|------------|---------|-------------|
| `OLLAMA_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `mistral` | Model name |

#### 📱 Instagram Auto-Publishing (Optional)

| Secret Name | Description |
|------------|-------------|
| `AUTO_PUBLISH_INSTAGRAM` | `true` or `false` to enable auto-publishing |
| `IG_USER_ID` | Your Instagram Business/Creator account ID |
| `IG_ACCESS_TOKEN` | Meta API access token |
| `PUBLIC_MEDIA_BASE_URL` | Public URL hosting the media files |

### Step 3: Complete Example

Here's a **complete minimal setup** with just required secrets:

```
IMAP_HOST=imap.gmail.com
IMAP_PORT=993
IMAP_USERNAME=your_email@gmail.com
IMAP_PASSWORD=abcd efgh ijkl mnop
EMAIL_SENDER_FILTER=grdevelopers.co@gmail.com
EMAIL_FOLDER=INBOX
LOOKBACK_HOURS=24
POLL_INTERVAL_MINUTES=1
SUMMARY_PROVIDER=auto
PROCESS_ALL_MATCHING=false
MAX_EMAILS_PER_RUN=20
CREATE_INSTAGRAM_POSTS=true
ENRICH_ARTICLES=true
AUTO_PUBLISH_INSTAGRAM=false
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=mistral
```

---

## ✅ Verify Secrets Are Configured

Once you've added all secrets:

1. Go to **Settings** → **Secrets and variables** → **Actions**
2. You should see a list of all configured secrets
3. Secrets appear masked with `●●●●●●●●` for security

---

## 🚀 Enable and Test Workflows

### Check Workflow Status

1. Go to your repository
2. Click **Actions** tab
3. You'll see all workflows listed

### Manual Workflow Trigger

To manually test the email processing workflow:

1. Click **Actions** tab
2. Click **Process AI News Emails** (left sidebar)
3. Click **Run workflow** (top right)
4. Select **main** branch
5. Click **Run workflow**
6. Monitor the execution in real-time

### View Workflow Logs

1. Go to **Actions** tab
2. Click on the workflow run
3. Click on the job name
4. Expand each step to see logs
5. Check for errors or issues

---

## 📊 Workflow Details

### Process AI News Emails (`process-emails-scheduled.yml`)

**When it runs:**
- ⏰ Every 15 minutes automatically
- 🎮 Any time you manually trigger it

**What it does:**
1. Checks out latest code
2. Sets up Python 3.10
3. Installs dependencies
4. Creates `.env` from your secrets
5. Runs `python -m email_summary_agent --once --all`
6. Uploads generated reports as artifacts
7. Uploads logs as artifacts
8. **Auto-commits** new reports to repository

**Success indicators:**
- ✅ Workflow completes without errors
- ✅ Reports uploaded to artifacts
- ✅ New commit appears with `[skip ci]` tag
- ✅ `reports/latest.md` updated on main branch

**Output:**
- 📄 Latest report at `reports/latest.md`
- 📱 Instagram carousels at `reports/instagram_posts/`
- 📊 Tracking database at `data/agent.sqlite3`
- 📝 Logs available for download

---

### CI Code Quality (`ci-tests.yml`)

**When it runs:**
- 🔀 On every push to `main` or `develop` branches
- 📋 On every pull request

**What it does:**
1. Checks Python syntax
2. Runs flake8 linting
3. Checks black code formatting
4. Verifies import sorting
5. Tests `--sample` mode
6. Verifies sample report generation

**Success indicators:**
- ✅ All checks pass
- ✅ No syntax errors
- ✅ Sample report generated

---

### Validate Documentation (`validate-docs.yml`)

**When it runs:**
- 📝 On documentation changes
- 🔀 On pull requests to main

**What it does:**
1. Lints README.md and SETUP.md
2. Validates required sections
3. Checks markdown formatting

**Success indicators:**
- ✅ All documentation sections present
- ✅ Markdown is valid

---

## 🆘 Troubleshooting

### ❌ "Workflow failed with error"

1. Click the failed workflow run
2. Expand failed steps to see error details
3. Common issues:
   - **Wrong credentials**: Check secrets match your `.env`
   - **IMAP not enabled**: Enable in Gmail settings
   - **App password incorrect**: Use Gmail app password, not regular password
   - **Network issues**: Try manual trigger again

### ❌ "Secrets not recognized"

1. Go to **Settings** → **Secrets and variables** → **Actions**
2. Verify secrets are there
3. Verify secret names match exactly (case-sensitive)
4. Delete and re-add any questionable secrets

### ❌ "Repository push failed"

1. The workflow uses the automatically available `GITHUB_TOKEN`
2. Verify the token has write access
3. Check branch protection rules aren't blocking commits

### ❌ "Emails not being processed"

1. Verify `IMAP_USERNAME` is correct
2. Confirm `IMAP_PASSWORD` is Gmail app password
3. Check `EMAIL_SENDER_FILTER` matches sender
4. Try manual trigger of workflow
5. Check logs for IMAP connection errors

### ✅ How to Debug

1. Click **Actions** → workflow run
2. Look at each step's output
3. The step will show `✓` if successful or `✗` if failed
4. Expand failed step to see full error
5. Common section: "Create .env file from secrets" - shows if secrets are being loaded

---

## 📊 Monitoring Workflow Execution

### View All Workflow Runs

1. Go to **Actions** tab
2. See list of all workflow runs
3. Filter by workflow name
4. Click on any run to see details

### Download Artifacts

After a successful run:

1. Click on the workflow run
2. Scroll down to "Artifacts" section
3. Click to download:
   - `ai-news-reports.zip` - Generated reports and posts
   - `processing-logs.zip` - Execution logs

### Check Commit History

GitHub automatically commits updated reports:

1. Go to **Code** tab
2. Look for commits with message `chore: update news reports and Instagram assets [skip ci]`
3. These are auto-generated by the workflow
4. Click to see exactly what was updated

---

## 🎯 Next Steps

1. **Configure all required secrets** in GitHub Settings
2. **Test manually** by triggering workflow in Actions tab
3. **Verify reports** are generated and committed
4. **Check logs** for any errors
5. **Monitor** in the Actions tab as workflows run
6. **Adjust timing** if needed (edit cron schedule in YAML file)

---

## 📚 Useful Links

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Managing Secrets](https://docs.github.com/en/actions/security-guides/encrypted-secrets)
- [Workflow Syntax](https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions)
- [Schedule Workflows](https://docs.github.com/en/actions/using-workflows/events-that-trigger-workflows#schedule)

---

## 💡 Pro Tips

### Modify Workflow Schedule

To change the 15-minute schedule:

1. Edit `.github/workflows/process-emails-scheduled.yml`
2. Find the `cron:` line: `- cron: '*/15 * * * *'`
3. Change `15` to desired minutes:
   - `*/5` - Every 5 minutes
   - `*/30` - Every 30 minutes
   - `0 * * * *` - Every hour
   - `0 9 * * *` - Daily at 9 AM
4. Commit and push the change

### Disable a Workflow

To temporarily disable the email processing:

1. Go to **Actions** tab
2. Click **Process AI News Emails**
3. Click ⋯ menu → **Disable workflow**
4. To re-enable: Click ⋯ menu → **Enable workflow**

### View Raw Logs

For detailed debugging:

1. Click failed workflow run
2. Click job name
3. Scroll to bottom
4. Click **View raw logs** link
5. See complete unfiltered output

---

**Ready to automate? Configure your secrets and let the workflows do the work!** 🚀
