# 🔧 GitHub Actions Setup Guide

Step-by-step instructions to get the AI Instagram News Agent running on GitHub Actions — zero-cost, fully automated.

---

## 📋 Prerequisites Checklist

- [ ] GitHub repository with this code pushed
- [ ] Gmail account with IMAP enabled
- [ ] Gmail app password (we'll create this)
- [ ] GitHub Pages enabled (for Instagram image hosting)

---

## 🚀 Setup Steps

### Step 1: Enable Gmail IMAP

1. Open **Gmail** in your browser: https://mail.google.com/
2. Click **Settings** (⚙️ icon in the top-right)
3. Select **See all settings**
4. Navigate to **Forwarding and POP/IMAP** tab
5. Under "IMAP Access": Select **Enable IMAP**
6. Scroll down and click **Save Changes**

### Step 2: Create Gmail App Password

1. Open **Google Account Security**: https://myaccount.google.com/security
2. Enable **2-Step Verification** if not already enabled
3. Go to **App passwords**
4. Select **Mail** → **Other (Windows Computer)**
5. Google generates a **16-character password**
6. **Copy this password** (you'll need it in Step 3)

### Step 3: Configure GitHub Secrets

Go to your repository → **Settings** → **Secrets and variables** → **Actions**

Add these secrets:

| Secret Name | Value |
|-------------|-------|
| `IMAP_USERNAME` | Your Gmail address |
| `IMAP_PASSWORD` | 16-character Gmail app password |
| `EMAIL_SENDER_FILTER` | `grdevelopers.co@gmail.com` |

**Optional (for Instagram publishing):**

| Secret Name | Value |
|-------------|-------|
| `IG_USER_ID` | Instagram Business/Creator account ID |
| `IG_ACCESS_TOKEN` | Meta API access token |
| `FB_PAGE_ID` | Facebook Page ID |
| `FB_PAGE_ACCESS_TOKEN` | Facebook Page access token |

### Step 4: Enable GitHub Pages

1. Go to repository **Settings** → **Pages**
2. Source: **GitHub Actions**
3. Save

### Step 5: Test the Workflow

1. Go to **Actions** tab
2. Click **Instagram Auto Publish** (left sidebar)
3. Click **Run workflow** → Select **main** → **Run workflow**
4. Watch the execution in real-time

---

## 🎮 How It Works

The workflow `.github/workflows/instagram-auto-publish.yml` runs **every 15 minutes** and:

1. **Checks Gmail** for new emails from the configured sender
2. **Opens article links** and extracts text + images
3. **Summarizes content** using the built-in NLP engine
4. **Generates reports** and Instagram carousel PNGs
5. **Deploys to GitHub Pages** for public image URLs
6. **Publishes to Instagram/Facebook** (if configured)

### Available CLI Modes

The agent runs inside the GitHub Actions environment:

- `--poll-once` — Check for new emails only (used by the 15-min schedule)
- `--recent-all` — Backfill all emails from the lookback window
- `--once --all --reprocess` — Rebuild everything from scratch
- `--sample` — Generate a sample report (no email needed)

---

## 📁 Output Files

After each run, these files are auto-committed:

```
reports/
├── latest.md                      # Current news digest
└── instagram_posts/               # Instagram carousel assets
    └── [batch_timestamp]/
        ├── publish_manifest.json  # Publishing metadata
        └── [article_slug]/
            ├── caption.txt        # Instagram caption
            ├── metadata.json      # Content metadata
            └── [images...]        # Carousel PNG slides
```

---

## 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| "IMAP Connection Failed" | Verify app password, enable IMAP in Gmail settings |
| "No emails processed" | Check `EMAIL_SENDER_FILTER` matches your sender |
| "Auto-commit failed" | Check GitHub token has write permissions |
| "Instagram publishing failed" | Verify `IG_ACCESS_TOKEN` is valid |

---

## 📚 More Documentation

- [QUICK_START_GITHUB.md](QUICK_START_GITHUB.md) — Quick reference
- [GITHUB_ACTIONS_SETUP.md](GITHUB_ACTIONS_SETUP.md) — Detailed automation guide
- [CAROUSEL_QUALITY_GUIDE.md](CAROUSEL_QUALITY_GUIDE.md) — Improve slide quality
