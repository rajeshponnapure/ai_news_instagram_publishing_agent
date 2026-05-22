# Step-by-Step Setup (GitHub Actions)

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
4. Create an app password.
5. Copy the generated password.

## 3. Configure GitHub Secrets

In your GitHub repository, go to **Settings → Secrets and variables → Actions** and add:

```
IMAP_USERNAME     = your_email@gmail.com
IMAP_PASSWORD     = your_gmail_app_password
EMAIL_SENDER_FILTER = grdevelopers.co@gmail.com
```

Optional Instagram/Facebook secrets:

```
IG_USER_ID
IG_ACCESS_TOKEN
FB_PAGE_ID
FB_PAGE_ACCESS_TOKEN
```

## 4. Enable GitHub Pages

Go to repository **Settings → Pages** → Source: **GitHub Actions**.

## 5. Test the Workflow

1. Go to **Actions** tab
2. Click **Instagram Auto Publish**
3. Click **Run workflow** → Select **main** → **Run workflow**

The workflow will:
- Connect to Gmail via IMAP
- Fetch emails from the sender
- Extract and summarize article content
- Generate report and Instagram carousel assets
- Deploy media to GitHub Pages
- Publish to Instagram/Facebook (if configured)

## 6. What to check

- `reports/latest.md` has the newest summary report
- `reports/instagram_posts` has carousel folders with PNG slides
- `data/agent.sqlite3` remembers processed emails

## Notes

- The agent is designed for GitHub Actions only and will refuse to run locally
- All processing is fully automated with zero API costs
- The workflow uses the built-in NLP summarizer by default
