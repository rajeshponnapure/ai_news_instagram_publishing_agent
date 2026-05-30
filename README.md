# 🤖 AI Instagram News Agent

[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Cost: $0](https://img.shields.io/badge/Cost-$0-green.svg)](#why-this-is-0)

> **Automated AI news summarization & Instagram content generation from email—fully local, completely free, zero paid APIs.**

## Zero-Budget Automation First

For a completely free no-billing production setup, use GitHub Actions plus GitHub Pages. GitHub Actions checks Gmail every 15 minutes, generates carousel assets, publishes those assets through GitHub Pages, and then posts the carousel through the Instagram API.

Transform AI news emails into beautifully formatted Instagram carousel posts. This intelligent agent reads emails from your inbox, intelligently summarizes article content locally using AI, generates professional markdown reports, and automatically creates image-rich social media content—all while keeping your data private and your costs at $0.

---

## ✨ Features

### 📧 Smart Email Processing
- **IMAP Integration**: Securely connects to Gmail (or any IMAP server)
- **Intelligent Filtering**: Automatically identifies and processes emails from specified AI news sources
- **Duplicate Detection**: Prevents reprocessing emails with built-in tracking
- **Batch Processing**: Handles multiple emails efficiently with configurable limits

### 🧠 Local AI Summarization
- **Zero External APIs**: All summarization happens locally on your machine
- **Dual-Engine Support**: 
  - **Ollama Integration** (Optional): Use powerful local LLMs for intelligent summaries
  - **Fallback NLP**: Built-in summarization engine requires no setup
- **Article Extraction**: Automatically fetches and parses real article content
- **Smart Enrichment**: Extracts key metadata, links, and insights from articles

### 📝 Professional Report Generation
- **Markdown Reports**: Beautifully formatted daily news digests
- **Automated Scheduling**: Generates timestamped reports automatically
- **Content Organization**: Organized directory structure for easy management
- **Latest Report**: Always-updated `latest.md` for quick reference

### 📱 Instagram Content Creation
- **Carousel Generation**: Multi-slide Instagram posts with images and text
- **Image Integration**: Beautifully formatted image-rich slides
- **Caption Optimization**: Engaging, social-media-friendly captions
- **Metadata Management**: Comprehensive publishing metadata included
- **Auto-Publishing** (Optional): Direct Instagram integration for seamless posting

### 💾 Local Data Management
- **SQLite Tracking**: Lightweight local database for email/article tracking
- **Asset Organization**: Structured folders for reports, images, and manifests
- **Full History**: Complete audit trail of all processed items
- **Privacy-First**: All data stays on your machine—no cloud required

---

## 🚀 Quick Start

### Prerequisites
- **Python 3.10+** (download from [python.org](https://www.python.org/downloads/))
- **Gmail Account** with IMAP enabled
- **Optional**: [Ollama](https://ollama.ai/) for local LLM summarization

### 1️⃣ Setup (.env Configuration)

```bash
# Copy the example configuration
cp .env.example .env

# Edit .env with your credentials:
IMAP_USERNAME=your_email@gmail.com
IMAP_PASSWORD=your_app_password  # Gmail App Password, not regular password
EMAIL_SENDER_FILTER=grdevelopers.co@gmail.com  # Your news email source
```

> 💡 **Gmail App Password**: Use [Google Account Security](https://myaccount.google.com/security) to create an app-specific password

### 2️⃣ Test with Sample Data

```bash
python -m email_summary_agent --sample
```

This validates your setup without email access. Check `reports/latest.md` for the sample output.

### 3️⃣ Run Your First Real Pass

```bash
python -m email_summary_agent --once --all
```

The agent will:
1. Connect to Gmail via IMAP
2. Fetch emails from your configured sender
3. Extract article links and fetch content
4. Summarize each article locally
5. Generate `reports/latest.md`
6. Create Instagram carousel assets in `reports/instagram_posts/`

---

## 🎮 Operating Modes

### Single Pass (Process Emails Once)
```powershell
# Process all unread emails from sender
python -m email_summary_agent --once --all

# Reprocess everything (rebuild reports and Instagram assets)
python -m email_summary_agent --once --all --reprocess
```

### Automated With GitHub Actions (Only Mode)

The agent is designed to run exclusively in GitHub Actions. Enable GitHub Pages from Actions and add the required repository secrets. The workflow checks for new sender email every 15 minutes and publishes generated carousel assets through GitHub Pages before posting to Instagram.

---

## 🏗️ Project Architecture

```
AI_Instagram_News_Agent/
├── email_summary_agent/          # Core application package
│   ├── agent.py                  # Main orchestration logic
│   ├── email_client.py           # IMAP email fetching
│   ├── article_enricher.py       # Web scraping & article extraction
│   ├── summarizer.py             # Local NLP/LLM summarization
│   ├── instagram.py              # Instagram carousel generation
│   ├── publisher.py              # Instagram API integration
│   ├── db.py                     # SQLite database operations
│   ├── config.py                 # Configuration management
│   ├── models.py                 # Data structures
│   └── report.py                 # Markdown report generation
│
├── data/
│   ├── agent.sqlite3             # Tracking database
│   └── article_assets/           # Cached article images
│
├── reports/                      # Generated output
│   ├── latest.md                 # Current news digest
│   ├── [timestamp]_ai_news_report.md
│   └── instagram_posts/          # Instagram carousel assets
│
├── scripts/                      # Utility scripts
│   ├── download_fonts.py
│   ├── generate_instagram_from_reports.py
│   └── publish_latest_instagram.py
│
├── logs/                         # Application logs
├── .env                          # Configuration (add your credentials here)
├── .env.example                  # Configuration template
├── requirements.txt              # Python dependencies
└── README.md                     # This file
```

---

## ⚙️ Configuration

### Essential Settings (.env)
```env
# Email Access (REQUIRED)
IMAP_HOST=imap.gmail.com
IMAP_PORT=993
IMAP_USERNAME=your_email@gmail.com
IMAP_PASSWORD=your_gmail_app_password

# Email Filtering
EMAIL_SENDER_FILTER=grdevelopers.co@gmail.com
EMAIL_FOLDER=INBOX
LOOKBACK_HOURS=24
MAX_EMAILS_PER_RUN=20

# Processing
POLL_INTERVAL_MINUTES=1
PROCESS_ALL_MATCHING=false
SUMMARY_PROVIDER=auto  # "auto" | "gemini" | "ollama" | "local"
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.5-flash

# Ollama (Optional, for local LLM)
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=mistral

# Output Generation
CREATE_INSTAGRAM_POSTS=true

# Instagram Publishing (Optional)
AUTO_PUBLISH_INSTAGRAM=false
IG_USER_ID=your_instagram_id
IG_ACCESS_TOKEN=your_token

# Facebook Page Publishing (Optional)
AUTO_PUBLISH_FACEBOOK=false
FB_PAGE_ID=your_facebook_page_id
FB_PAGE_ACCESS_TOKEN=your_page_access_token
```

### Advanced Settings
| Setting | Default | Description |
|---------|---------|-------------|
| `LOOKBACK_HOURS` | 24 | How far back to search for new emails |
| `MAX_EMAILS_PER_RUN` | 20 | Maximum emails to process per execution |
| `POLL_INTERVAL_MINUTES` | 1 | Interval between watch mode checks |
| `MAX_ARTICLE_LINKS_PER_EMAIL` | 0 | Article extraction limit per email; `0` means no cap |
| `ENRICH_ARTICLES` | true | Fetch and parse full article content |
| `AUTO_PUBLISH_INSTAGRAM` | false | Automatically post to Instagram |
| `AUTO_PUBLISH_FACEBOOK` | false | Also publish generated slide images to a Facebook Page |

---

## 📦 Dependencies

### Why Zero-Cost?
This project uses **only standard Python libraries** by default:
- No paid API calls
- No cloud storage fees
- No LLM service subscriptions

### Optional: Ollama for Local LLM
For better AI summarization, install **[Ollama](https://ollama.ai/)**:
```bash
# Download and run Ollama (free, open-source)
# Then pull a model:
ollama pull mistral
```

The agent auto-detects Ollama and uses it if available. Without Ollama, it falls back to built-in NLP.

### Python Requirements
- **Python 3.10+** (for modern language features)
- **One required pip package**: [Pillow](https://python-pillow.org/) for Instagram carousel image generation
- See [requirements.txt](requirements.txt) for the installed dependency list

---

## 📧 Gmail Setup Guide

### Step 1: Enable IMAP
1. Open [Gmail](https://mail.google.com/)
2. Click **Settings** (⚙️ icon)
3. Select **See all settings**
4. Go to **Forwarding and POP/IMAP**
5. Select **Enable IMAP**
6. **Save Changes**

### Step 2: Create Gmail App Password
1. Visit [Google Account Security](https://myaccount.google.com/security)
2. Enable **2-Step Verification** (if not already enabled)
3. Search for **App passwords**
4. Select **Mail** and **Windows Computer**
5. Google generates a 16-character password
6. Copy this password to `.env` as `IMAP_PASSWORD`

⚠️ **Never use your regular Gmail password!** Always use the app-specific password.

---

## 📊 Workflow Diagram

```
Gmail Inbox
    ↓
IMAP Connection
    ↓
Email Fetch & Filter
    ↓
Article Link Extraction
    ↓
Web Scraping & Content Extraction
    ↓
Local Summarization (Ollama or NLP)
    ↓
Markdown Report Generation
    ↓
Instagram Carousel Creation
    ↓
Optional: Auto-Publish to Instagram
    ↓
SQLite Database Updates (Tracking)
    ↓
Reports & Assets Output
```

---

## 🎯 Use Cases

### 📰 AI News Digest
Automatically summarize daily AI news emails and maintain an updated digest in `reports/latest.md`.

### 📱 Social Media Content
Generate ready-to-publish Instagram carousel posts with formatted text, images, and links without manual editing.

### 📊 Content Archive
Build a queryable SQLite database of summarized articles with metadata for later analysis.

### 🔄 Automated Publishing
Configure Instagram credentials for automatic carousel publishing to your social media feed.

### 📧 Team Newsletter
Set up multiple email senders in the configuration and generate team digest reports.

---

## 🧪 Testing

### Validate Setup (No Email Required)
```bash
python -m email_summary_agent --sample
```
Generates a sample report at `reports/latest.md` to verify the system works.

### Full Test with Gmail
```bash
python -m email_summary_agent --once --all
```
Connects to Gmail and processes all emails from your configured sender.

### Check Database
```bash
# View processed emails and articles in SQLite
sqlite3 data/agent.sqlite3
.tables
SELECT * FROM emails;
```

---

## 📁 Output Structure

### Generated Reports
```
reports/
├── latest.md                          # Always-updated current digest
├── 20260517-142725_ai_news_report.md # Timestamped reports
└── instagram_posts/
    ├── 20260517-142725/              # Batch folder (timestamp)
    │   ├── publish_manifest.json      # Publishing metadata
    │   ├── index.html                 # Preview HTML
    │   └── 01_article_slug/           # Individual post folder
    │       ├── caption.txt            # Instagram caption
    │       ├── metadata.json          # Content metadata
    │       └── [images...]            # Carousel images
```

---

## 🐛 Troubleshooting

### Issue: "IMAP Connection Failed"
- Verify Gmail IMAP is enabled
- Check if you're using an app password (not regular password)
- Ensure `IMAP_USERNAME` matches your Gmail address

### Issue: "No emails processed"
- Check `EMAIL_SENDER_FILTER` matches your sender
- Verify emails exist in inbox from that sender
- Review logs in `logs/` directory

### Issue: "Poor summary quality"
- Install Ollama and pull a model for better summarization
- Adjust `SUMMARY_PROVIDER` in `.env`
- Check internet connection for article fetching

### Issue: "Instagram posting failed"
- Verify `IG_ACCESS_TOKEN` is valid
- Ensure account permissions are correct
- Check logs for detailed error messages

---

## 🤝 Contributing

Found a bug or have an idea? Contributions welcome!
- Fork the repository
- Create a feature branch
- Submit a pull request

---

## 📄 License

This project is licensed under the MIT License—see [LICENSE](LICENSE) file for details.

---

## 🙋 Support & Questions

For detailed setup instructions, see [SETUP.md](SETUP.md).

For issues or questions:
1. Check the [Troubleshooting](#-troubleshooting) section
2. Review logs in `logs/` directory
3. Examine `.env` configuration
4. Test with `--sample` flag for diagnostics

---

## 🎉 Key Highlights

✅ **100% Local**: All processing happens on your machine  
✅ **Zero Cost**: No paid APIs or subscriptions required  
✅ **Privacy First**: Your email and data never leave your computer  
✅ **Easy Setup**: 5-minute configuration with Gmail credentials  
✅ **Powerful**: Local LLM support for intelligent summaries  
✅ **Automatic**: Runs continuously, processes emails as they arrive  
✅ **Production-Ready**: Professional report and carousel generation  

---

**Ready to automate your AI news workflow?** Start with:
- [CAROUSEL_QUALITY_GUIDE.md](CAROUSEL_QUALITY_GUIDE.md) ← Fix repeated slides, get beautiful content
- [GITHUB_ACTIONS_SETUP.md](GITHUB_ACTIONS_SETUP.md) ← GitHub Actions configuration guide

## GitHub Actions automation

The production workflow lives at `.github/workflows/instagram-auto-publish.yml`.

It runs every 15 minutes and:

1. Checks Gmail for new sender emails.
2. Opens every article link in the email.
3. Extracts article text and article images.
4. Writes reports and Instagram carousel PNGs.
5. Deploys the generated files to GitHub Pages.
6. Publishes the latest carousel using the GitHub Pages image URLs.

## Summary provider option

The default `SUMMARY_PROVIDER=auto` uses Gemini when `GEMINI_API_KEY` is present, then Ollama, then the built-in summarizer.

To force the no-model local summarizer:

```env
SUMMARY_PROVIDER=local
```

To require Ollama:

```env
SUMMARY_PROVIDER=ollama
OLLAMA_MODEL=llama3.2:3b
```

To require Gemini:

```env
SUMMARY_PROVIDER=gemini
GEMINI_API_KEY=your_google_ai_studio_key
GEMINI_MODEL=gemini-2.5-flash
```

## Next workflow stages

After this stage is stable, the next agents can consume `reports/latest.md`:

- voice script agent
- free/local TTS agent
- short-form video generator
- approval gate
- Instagram caption and hashtag generator
