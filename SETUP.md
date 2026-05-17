# 🔧 Complete Setup Guide

Step-by-step instructions to get the AI Instagram News Agent up and running on your Windows machine.

---

## 📋 Prerequisites Checklist

- [ ] Windows 10 / Windows 11
- [ ] Python 3.10 or higher ([Download here](https://www.python.org/downloads/))
- [ ] Gmail account with IMAP enabled
- [ ] Your Gmail app password (we'll create this)
- [ ] Text editor or IDE (VS Code recommended)

---

## 🚀 Installation Steps

### Step 1: Verify Python Installation

Open **PowerShell** and run:

```powershell
python --version
```

Expected output: `Python 3.10.x` or higher

If Python is not installed:
1. Download from [python.org](https://www.python.org/downloads/)
2. Run the installer
3. ✅ **Check**: "Add Python to PATH"
4. Complete installation
5. Restart PowerShell and verify again

---

### Step 2: Navigate to Project Directory

Open **PowerShell** and navigate to the project:

```powershell
cd "C:\Users\saimo\OneDrive\Desktop\projects\AI_Instagram_News_Agent"
```

Verify the directory contents:

```powershell
ls
```

You should see: `email_summary_agent/`, `data/`, `reports/`, `scripts/`, `.env.example`, `requirements.txt`, etc.

---

### Step 3: Configure Gmail Access

#### Part A: Enable IMAP in Gmail

1. Open **Gmail** in your browser: https://mail.google.com/
2. Click **Settings** (⚙️ icon in the top-right)
3. Select **See all settings**
4. Navigate to **Forwarding and POP/IMAP** tab
5. Under "IMAP Access":
   - Select **Enable IMAP**
6. Scroll down and click **Save Changes**

✅ IMAP is now enabled for your Gmail account.

#### Part B: Create Gmail App Password

1. Open **Google Account Security**: https://myaccount.google.com/security
2. Look for "How you sign in to Google"
3. **If 2-Step Verification is OFF:**
   - Click "2-Step Verification"
   - Follow the prompts to enable it
   - **Wait 24 hours** (Google's requirement)

4. Once 2-Step Verification is enabled:
   - Go back to Security settings
   - Scroll to "Your passwords"
   - Click **App passwords**
   - Select **Mail** from the dropdown
   - Select **Windows Computer** from the second dropdown
   - Click **Generate**
   - ✅ Google creates a **16-character password**
   - **Copy this password** (you'll need it in Step 4)

---

### Step 4: Create and Configure .env File

#### Copy the Template

In PowerShell, run:

```powershell
Copy-Item .env.example .env
```

This creates a new `.env` file in your project directory.

#### Edit the .env File

Open `.env` in a text editor (VS Code, Notepad, etc.):

```powershell
# Open with Notepad
notepad .env

# Or open with VS Code (if installed)
code .env
```

#### Configure Your Credentials

Find and update these lines:

```env
# Your Gmail address
IMAP_USERNAME=your_email@gmail.com

# The 16-character app password from Part B (NOT your regular Gmail password!)
IMAP_PASSWORD=xxxx xxxx xxxx xxxx

# Keep this as the news source email
EMAIL_SENDER_FILTER=grdevelopers.co@gmail.com
```

#### Example (Do NOT use these values):

```env
IMAP_USERNAME=john.doe@gmail.com
IMAP_PASSWORD=abcd efgh ijkl mnop
EMAIL_SENDER_FILTER=grdevelopers.co@gmail.com
```

#### Keep These Unchanged

These values should remain as default:

```env
IMAP_HOST=imap.gmail.com
IMAP_PORT=993
EMAIL_FOLDER=INBOX
LOOKBACK_HOURS=24
POLL_INTERVAL_MINUTES=1
SUMMARY_PROVIDER=auto
PROCESS_ALL_MATCHING=false
MAX_EMAILS_PER_RUN=20
CREATE_INSTAGRAM_POSTS=true
```

#### Save the File

- Click **Save** or press `Ctrl+S`
- Close the editor

✅ Your `.env` file is now configured.

---

### Step 5: Test the Setup (No Email Required)

Open PowerShell in the project directory:

```powershell
cd "C:\Users\saimo\OneDrive\Desktop\projects\AI_Instagram_News_Agent"
```

Run the sample mode to validate everything works:

```powershell
python -m email_summary_agent --sample
```

**Expected output:**
```
✓ Generating sample data...
✓ Creating reports...
✓ Report written to: reports/latest.md
```

#### Verify the Report

Check that the report was generated:

```powershell
cat reports/latest.md
```

If you see a formatted markdown report with sample news articles, ✅ **setup is working!**

---

### Step 6: Test with Real Gmail Data

Now test connecting to your actual Gmail inbox:

```powershell
python -m email_summary_agent --once --all
```

**What the agent does:**
1. Connects to Gmail via IMAP
2. Fetches emails from `EMAIL_SENDER_FILTER` (grdevelopers.co@gmail.com)
3. Extracts article links from emails
4. Summarizes article content locally
5. Generates `reports/latest.md`
6. Creates Instagram carousel assets in `reports/instagram_posts/`
7. Logs activity to `logs/` directory

**Expected output:**
```
Connecting to IMAP...
Fetching emails...
Processing: email@sender.com - Article Title
Summarizing article...
Creating report...
Creating Instagram posts...
✓ Complete! Results in: reports/
```

#### Troubleshooting

If connection fails:
1. Double-check `IMAP_USERNAME` and `IMAP_PASSWORD` in `.env`
2. Verify IMAP is enabled in Gmail settings
3. Confirm you used the **app password**, not your regular Gmail password
4. Check Gmail security alerts at https://myaccount.google.com/security
5. Review logs in `logs/` directory

---

## 🎮 Running the Agent

### Option 1: Single Pass (Process Once)

```powershell
# Process unread emails from the configured sender
python -m email_summary_agent --once --all
```

### Option 2: Continuous Watch Mode

```powershell
# Run continuously - processes new emails as they arrive
python -m email_summary_agent --watch-new
```

To stop: Press `Ctrl+C`

### Option 3: Rebuild Everything

Reprocess all emails and regenerate reports and Instagram assets:

```powershell
python -m email_summary_agent --once --all --reprocess
```

### Option 4: Reset Generated Content

Delete all generated reports and Instagram assets, keeping email tracking:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\reset_generated_outputs.ps1
```

---

## 📅 Automate with Windows Task Scheduler

### Setup Automatic Runs Every 15 Minutes

#### Create the Task

1. Open **Task Scheduler**:
   - Press `Win + R`
   - Type `taskschd.msc`
   - Press Enter

2. In Task Scheduler, click **Create Basic Task** (right panel)

3. **General Tab:**
   - Name: `AI News Agent - Every 15 Minutes`
   - Description: `Automatically process AI news emails`

4. **Trigger Tab:**
   - Click **New**
   - Select "On a schedule"
   - Choose **Recurring**
   - Set to repeat every **15 minutes**
   - Set start date/time
   - Click **OK**

5. **Action Tab:**
   - Click **New**
   - Action: **Start a program**
   - Program: `C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe`
   - Arguments:
     ```
     -ExecutionPolicy Bypass -File "C:\Users\saimo\OneDrive\Desktop\projects\AI_Instagram_News_Agent\scripts\run_email_summary_watch.ps1"
     ```
   - Click **OK**

6. **Conditions Tab:**
   - Leave defaults or customize:
     - ☑ Start task only if computer is on AC power (uncheck to run on battery)
     - ☑ Wake the computer if the system is sleeping

7. **Settings Tab:**
   - ☑ Allow task to be run on demand
   - ☑ If the task fails, restart every: 10 minutes
   - ☑ Stop task if it runs longer than: 1 hour

8. **Finish & Test:**
   - Click **OK**
   - The task appears in the list
   - Right-click it → **Run** to test immediately

✅ Your agent will now run automatically every 15 minutes!

#### View Logs

All activity is logged to `logs/` directory. Check the latest log:

```powershell
# View most recent log
Get-ChildItem logs\ | Sort-Object LastWriteTime -Descending | Select-Object -First 1 | Get-Content
```

---

## 📝 Understanding Output Files

### Reports Directory

```
reports/
├── latest.md
│   └── Always-updated current digest
│
├── 20260517-142725_ai_news_report.md
│   └── Timestamped report from specific run
│
└── instagram_posts/
    ├── 20260517-142725/
    │   └── Batch processed at this timestamp
    │
    └── 01_20260517-1810_article-slug/
        ├── caption.txt          # Instagram caption
        ├── metadata.json        # Article metadata
        └── image_001.jpg        # Carousel images
```

### Data Directory

```
data/
├── agent.sqlite3        # Tracking database
└── article_assets/      # Downloaded article images
```

### Logs Directory

```
logs/
└── [timestamps].log     # Detailed execution logs
```

---

## 🔧 Configuration Reference

### Essential Settings

| Variable | Value | Notes |
|----------|-------|-------|
| `IMAP_USERNAME` | your_email@gmail.com | Your Gmail address |
| `IMAP_PASSWORD` | [app password] | 16-char app password, NOT regular password |
| `EMAIL_SENDER_FILTER` | grdevelopers.co@gmail.com | News source email |
| `IMAP_HOST` | imap.gmail.com | Gmail's IMAP server |
| `IMAP_PORT` | 993 | Gmail's secure IMAP port |

### Processing Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `LOOKBACK_HOURS` | 24 | How far back to search for new emails |
| `POLL_INTERVAL_MINUTES` | 1 | Interval between checks in watch mode |
| `MAX_EMAILS_PER_RUN` | 20 | Max emails processed per execution |
| `PROCESS_ALL_MATCHING` | false | Process all matching emails or just new |
| `EMAIL_FOLDER` | INBOX | Gmail folder to monitor |

### Content Generation Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `SUMMARY_PROVIDER` | auto | "auto" (LLM if available), "ollama", or "builtin" |
| `CREATE_INSTAGRAM_POSTS` | true | Generate Instagram carousel assets |
| `ENRICH_ARTICLES` | true | Fetch and parse full article content |
| `MAX_ARTICLE_LINKS_PER_EMAIL` | 5 | Articles extracted per email |

### Optional: Ollama Configuration

For better AI summarization (optional), install [Ollama](https://ollama.ai/):

```env
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=mistral
```

Then in PowerShell:
```powershell
# Download and run Ollama model
ollama pull mistral
```

The agent automatically uses Ollama if available; falls back to built-in NLP otherwise.

### Optional: Instagram Auto-Publishing

To automatically publish to Instagram (requires Meta app setup):

```env
AUTO_PUBLISH_INSTAGRAM=true
IG_USER_ID=your_instagram_user_id
IG_ACCESS_TOKEN=your_meta_access_token
IG_API_VERSION=v18.0
```

---

## 🐛 Troubleshooting

### Problem: "IMAP Authentication Failed"

**Solution:**
1. Verify `.env` has correct `IMAP_USERNAME` and `IMAP_PASSWORD`
2. Confirm you're using an **app password** (not regular Gmail password)
3. Check that IMAP is enabled in Gmail settings
4. Look for security alerts in Google Account: https://myaccount.google.com/security

### Problem: "No emails processed"

**Solution:**
1. Verify `EMAIL_SENDER_FILTER` matches the sender
2. Check that emails from this sender exist in your inbox
3. Review logs: `Get-Content logs/[latest].log`
4. Run with `--sample` to verify system works

### Problem: Python Command Not Found

**Solution:**
1. Verify Python is installed: `python --version`
2. If not found, install Python from https://www.python.org/downloads/
3. **Important:** Check "Add Python to PATH" during installation
4. Restart PowerShell after installation

### Problem: "Access Denied" Error

**Solution:**
1. Right-click PowerShell → "Run as Administrator"
2. Or use: `powershell -ExecutionPolicy Bypass` to bypass restrictions

### Problem: Poor Summarization Quality

**Solution:**
1. Install Ollama for better LLM-based summarization: https://ollama.ai/
2. Pull a model: `ollama pull mistral`
3. Set `SUMMARY_PROVIDER=ollama` in `.env`
4. Or set `SUMMARY_PROVIDER=auto` to auto-detect

### Problem: Instagram Publishing Fails

**Solution:**
1. Verify `IG_ACCESS_TOKEN` is valid
2. Check Instagram API permissions are correct
3. Review logs for detailed error: `Get-Content logs/[latest].log | Select-Object -Last 50`

### Problem: "Command takes too long"

**Solution:**
1. Reduce `MAX_EMAILS_PER_RUN` in `.env`
2. Increase `POLL_INTERVAL_MINUTES` if running in watch mode
3. Check internet connection (article fetching may be slow)
4. Reduce `MAX_ARTICLE_LINKS_PER_EMAIL`

---

## ✅ Verification Checklist

Run through this checklist to verify your setup is complete:

- [ ] Python 3.10+ installed and working
- [ ] Project directory accessible from PowerShell
- [ ] `.env` file created with your credentials
- [ ] IMAP enabled in Gmail settings
- [ ] Gmail app password generated and entered in `.env`
- [ ] Sample mode works: `python -m email_summary_agent --sample`
- [ ] Real mode works: `python -m email_summary_agent --once --all`
- [ ] Reports generated in `reports/` directory
- [ ] Instagram assets created in `reports/instagram_posts/`
- [ ] No errors in `logs/` directory
- [ ] (Optional) Task Scheduler automated task created

✅ **If all checkmarks are complete, you're ready to go!**

---

## 📚 Next Steps

1. **Review Generated Output:**
   ```powershell
   cat reports/latest.md
   ```

2. **Check Logs:**
   ```powershell
   Get-ChildItem logs\ | Sort-Object LastWriteTime -Descending | Select-Object -First 1
   ```

3. **Set Up Automation:**
   - Follow the Task Scheduler section above to automate runs
   - Or run in continuous watch mode: `python -m email_summary_agent --watch-new`

4. **Customize (Optional):**
   - Modify `EMAIL_SENDER_FILTER` for different news sources
   - Adjust `MAX_EMAILS_PER_RUN` for batch size
   - Enable Ollama for better AI summaries
   - Set up Instagram auto-publishing

---

## 🎯 Usage Examples

### Daily Digest
```powershell
# Run once per day to process new emails
python -m email_summary_agent --once --all

# Check latest report
cat reports/latest.md
```

### Continuous Monitoring
```powershell
# Keep running and process new emails automatically
python -m email_summary_agent --watch-new
```

### Rebuild Everything
```powershell
# Reprocess all emails and regenerate all reports
python -m email_summary_agent --once --all --reprocess
```

### Archive Management
```powershell
# Delete old reports and Instagram assets, start fresh
powershell -ExecutionPolicy Bypass -File .\scripts\reset_generated_outputs.ps1

# Then run to regenerate
python -m email_summary_agent --once --all
```

---

## 💡 Pro Tips

1. **Multiple News Sources**: Modify scripts to run multiple agent instances with different `EMAIL_SENDER_FILTER` values

2. **Custom Summaries**: Edit `email_summary_agent/summarizer.py` to customize how articles are summarized

3. **Report Templates**: Modify `email_summary_agent/report.py` to change report formatting

4. **Instagram Automation**: Set up Meta app credentials for automatic posting without manual upload

5. **Monitoring**: Check `logs/` regularly to catch errors or performance issues

6. **Database Queries**: Query `data/agent.sqlite3` to analyze processed emails and articles:
   ```powershell
   sqlite3 data\agent.sqlite3 ".headers on" "SELECT * FROM emails LIMIT 10;"
   ```

---

## 🆘 Getting Help

1. Check the README.md for feature overview
2. Review logs in `logs/` directory for detailed errors
3. Try `--sample` mode to isolate issues
4. Verify `.env` configuration is correct
5. Test IMAP connection manually with Gmail settings

---

**You're all set! Start processing AI news automatically! 🚀**
