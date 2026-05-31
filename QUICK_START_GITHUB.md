# 🚀 Quick Reference - GitHub Automation Setup

## 📋 What Was Set Up

### ✅ Documentation Files (Pushed to GitHub)
- **README.md** - Beautiful GitHub project overview
- **SETUP.md** - Step-by-step Windows setup guide  
- **GITHUB_ACTIONS_SETUP.md** - Complete workflows configuration guide
- **.github/WORKFLOWS_SETUP.md** - Technical workflow details

### ✅ GitHub Actions Workflows (3 Automated Workflows)

#### 1️⃣ Process AI News Emails
- **File**: `.github/workflows/process-emails-scheduled.yml`
- **Trigger**: Every 15 minutes automatically (or manual)
- **Function**: Processes emails → Generates reports → Creates Instagram posts
- **Output**: Auto-commits `latest.md` and Instagram assets to repo
- **Status**: Requires secrets to be configured

#### 2️⃣ Code Quality CI
- **File**: `.github/workflows/ci-tests.yml`
- **Trigger**: On every push/pull request to main or develop
- **Function**: Validates Python code, runs tests, checks formatting
- **Status**: Ready to use (no secrets needed)

#### 3️⃣ Documentation Validation
- **File**: `.github/workflows/validate-docs.yml`
- **Trigger**: On documentation changes
- **Function**: Validates README.md and SETUP.md structure
- **Status**: Ready to use (no secrets needed)

---

## 🔐 Next Step: Configure GitHub Secrets

### 🎯 Go to GitHub Repository Settings

1. Visit: **https://github.com/Rajeshponnapure/ai_news_instagram_publishing_agent**
2. Click **Settings** (top right)
3. Click **Secrets and variables** → **Actions** (left sidebar)
4. Click **New repository secret** (green button)

### ✏️ Add These Secrets (Copy & Paste)

Add each secret one at a time:

```
IMAP_HOST = imap.gmail.com
IMAP_PORT = 993
IMAP_USERNAME = your_email@gmail.com
IMAP_PASSWORD = [Gmail app password - 16 characters]
EMAIL_SENDER_FILTER = grdevelopers.co@gmail.com
EMAIL_FOLDER = INBOX
LOOKBACK_HOURS = 24
POLL_INTERVAL_MINUTES = 1
SUMMARY_PROVIDER = auto
PROCESS_ALL_MATCHING = false
MAX_EMAILS_PER_RUN = 20
CREATE_INSTAGRAM_POSTS = true
ENRICH_ARTICLES = true
AUTO_PUBLISH_INSTAGRAM = false
```

⚠️ **Important**: 
- Use **Gmail app password**, NOT your regular Gmail password
- Get app password from: https://myaccount.google.com/security → App passwords

### ✅ Verify All Secrets Are Added

1. Go to **Settings** → **Secrets and variables** → **Actions**
2. Count the secrets - should be 15 total
3. All secret values appear masked (●●●●●●●●)

---

## 🧪 Test the Setup

### Test 1: Manual Workflow Trigger

1. Go to your GitHub repo
2. Click **Actions** tab
3. Click **Process AI News Emails** (left sidebar)
4. Click **Run workflow** button
5. Select **main** branch
6. Click **Run workflow**
7. Watch the execution in real-time
8. ✅ Success = "Process AI News Emails" shows ✓ checkmark

### Test 2: Check Artifacts

After successful run:

1. Click the workflow run
2. Scroll down to **Artifacts**
3. Download `ai-news-reports.zip`
4. Check inside for:
   - `latest.md` - News digest
   - `instagram_posts/` - Generated carousels
   - `logs/` - Processing logs

### Test 3: Verify Auto-Commit

After successful run:

1. Go to **Code** tab on GitHub
2. Look in commit history
3. Find commit with message: `chore: update news reports and Instagram assets [skip ci]`
4. Click it to see what was updated
5. ✅ Should show `reports/latest.md` and Instagram posts updated

---

## 📊 View Workflow Status & Logs

### Check All Workflow Runs

1. Click **Actions** tab
2. See all recent runs
3. Green ✅ = Successful
4. Red ❌ = Failed
5. Yellow ⏳ = Running

### View Detailed Logs

1. Click on a workflow run
2. Click the job name
3. Expand each step
4. See full output and errors
5. Look for `✓` (success) or `✗` (error) indicators

### Download Logs

For any run:

1. Click on the run
2. Scroll to **Artifacts**
3. Download `processing-logs.zip`
4. Contains detailed execution logs

---

## 🎮 Automate Like a Pro

### Modify Execution Schedule

**Current**: Every 15 minutes  
**Location**: `.github/workflows/process-emails-scheduled.yml`

Change this line:
```yaml
- cron: '*/15 * * * *'  # 15 minutes
```

To:
```yaml
- cron: '*/5 * * * *'   # Every 5 minutes
- cron: '*/30 * * * *'  # Every 30 minutes
- cron: '0 * * * *'     # Every hour
- cron: '0 9 * * *'     # Daily at 9 AM UTC
```

Then commit and push the change.

### Disable/Enable Workflows

1. Go to **Actions** tab
2. Click workflow name
3. Click ⋯ menu (top right)
4. **Disable workflow** or **Enable workflow**

---

## 🐛 Troubleshooting

### ❌ Workflow says "Error: IMAP Connection Failed"

**Solution:**
1. Check secrets are correctly configured
2. Verify `IMAP_PASSWORD` is Gmail app password (not regular password)
3. Verify `IMAP_USERNAME` matches your Gmail address
4. Go to Gmail settings and enable IMAP

### ❌ Workflow runs but no reports generated

**Check:**
1. Download logs from artifacts
2. Look for error messages
3. Verify `EMAIL_SENDER_FILTER` matches sender
4. Check that emails from sender exist in inbox
5. Try running locally first: `python -m email_summary_agent --sample`

### ❌ Secrets not loading

**Solution:**
1. Verify secrets names are EXACT (case-sensitive)
2. Check no typos in secret names
3. Delete and re-add suspicious secrets
4. Wait 1-2 minutes for cache refresh

### ❌ Auto-commit fails

**Check:**
1. Verify `GITHUB_TOKEN` has write permissions
2. Check branch protection rules aren't blocking
3. Allow GitHub Actions to write to repo

---

## 📚 Documentation Links

- 📖 [README.md](README.md) - Project overview
- 🔧 [SETUP.md](SETUP.md) - Local setup guide
- ⚙️ [GITHUB_ACTIONS_SETUP.md](GITHUB_ACTIONS_SETUP.md) - Detailed workflow guide
- 🏃 [.github/WORKFLOWS_SETUP.md](.github/WORKFLOWS_SETUP.md) - Technical reference

---

## ✅ Checklist: You're Done When...

- [ ] README.md pushed to GitHub ✓
- [ ] SETUP.md pushed to GitHub ✓
- [ ] GitHub Actions workflows created ✓
- [ ] 15+ secrets configured in GitHub ✓
- [ ] Manual workflow test successful ✓
- [ ] Reports auto-commit to repo ✓
- [ ] Documentation validation passing ✓

---

## 🎉 What Happens Now

### 🕐 Automatic Processing (Runs Every 15 Minutes)

1. GitHub Actions triggers workflow
2. Connects to your Gmail inbox
3. Fetches new AI news emails
4. Extracts article links
5. Summarizes article content locally
6. Generates markdown report
7. Creates Instagram carousel assets
8. Commits `latest.md` and posts to repo
9. Uploads logs as artifacts

### 💬 GitHub Status Indicators

- ✅ Green checkmark = Success
- ❌ Red X = Error (check logs)
- ⏳ Yellow dot = Running now
- ⊝ Grey dash = Skipped

### 📊 Monitoring Dashboard

1. Go to **Actions** tab anytime
2. See all workflow history
3. Download any artifacts
4. View real-time logs
5. Manually trigger anytime

---

## 🚀 You're All Set!

Your AI Instagram News Agent is now:
- ✅ Documented on GitHub
- ✅ Automated with workflows
- ✅ Running every 15 minutes
- ✅ Committing updates automatically
- ✅ Fully integrated with GitHub

**No more manual runs needed!** The system is now autonomous and will process your AI news emails, generate reports, and create Instagram content automatically. 🎊

---

**Questions?** Check [GITHUB_ACTIONS_SETUP.md](GITHUB_ACTIONS_SETUP.md) for detailed help!
