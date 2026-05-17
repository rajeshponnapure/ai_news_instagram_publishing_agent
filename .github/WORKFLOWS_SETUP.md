# GitHub Actions Secrets Configuration Guide

This file documents the secrets needed for the GitHub Actions workflows to function properly.

## Required Secrets for Email Processing Workflow

To enable the `process-emails-scheduled.yml` workflow to work, you must configure the following secrets in your GitHub repository:

### Email Configuration (REQUIRED)
- `IMAP_HOST` - IMAP server hostname (default: `imap.gmail.com`)
- `IMAP_PORT` - IMAP port (default: `993`)
- `IMAP_USERNAME` - Your Gmail email address
- `IMAP_PASSWORD` - Gmail app password (NOT your regular password)
- `EMAIL_SENDER_FILTER` - Email address to filter (e.g., `grdevelopers.co@gmail.com`)

### Email Processing Options
- `EMAIL_FOLDER` - Gmail folder to monitor (default: `INBOX`)
- `LOOKBACK_HOURS` - Hours to look back for new emails (default: `24`)
- `POLL_INTERVAL_MINUTES` - Minutes between polls (default: `1`)
- `PROCESS_ALL_MATCHING` - Process all matching or just new (default: `false`)
- `MAX_EMAILS_PER_RUN` - Max emails per run (default: `20`)

### Content Generation Options
- `SUMMARY_PROVIDER` - Summarizer to use: `auto`, `ollama`, or `builtin` (default: `auto`)
- `CREATE_INSTAGRAM_POSTS` - Generate Instagram posts (default: `true`)
- `ENRICH_ARTICLES` - Fetch full article content (default: `true`)

### Optional: Ollama Configuration
- `OLLAMA_URL` - Ollama server URL (default: `http://localhost:11434`)
- `OLLAMA_MODEL` - Model to use with Ollama (default: `mistral`)

### Optional: Instagram Auto-Publishing
- `AUTO_PUBLISH_INSTAGRAM` - Enable auto-publishing (default: `false`)
- `IG_USER_ID` - Instagram Business/Creator account ID
- `IG_ACCESS_TOKEN` - Meta API access token
- `PUBLIC_MEDIA_BASE_URL` - Public URL for hosting images

## How to Add Secrets to GitHub

1. Go to your GitHub repository
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Enter the name (e.g., `IMAP_USERNAME`) and value
5. Click **Add secret**
6. Repeat for all required secrets

## Example Secret Values

```
IMAP_HOST=imap.gmail.com
IMAP_PORT=993
IMAP_USERNAME=your_email@gmail.com
IMAP_PASSWORD=xxxx xxxx xxxx xxxx
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

## Workflow Descriptions

### process-emails-scheduled.yml
- **Trigger**: Scheduled every 15 minutes (or manually triggered)
- **Function**: Processes AI news emails, generates reports, creates Instagram posts
- **Artifacts**: Generated reports and logs available for download
- **Auto-Commit**: Pushes updated `latest.md` and Instagram assets back to repository

### ci-tests.yml
- **Trigger**: On push/pull request to main or develop branches
- **Function**: Validates Python code quality, runs linting, tests sample mode
- **Checks**: Syntax, flake8, black formatting, isort imports

### validate-docs.yml
- **Trigger**: On documentation changes or manual trigger
- **Function**: Validates README.md and SETUP.md structure and content
- **Checks**: Required sections, markdown formatting

## Important Notes

⚠️ **Security**: 
- Never commit `.env` files with real credentials
- Secrets are encrypted and never logged
- Use a Gmail app password, NOT your regular password
- Rotate credentials periodically

🔐 **Best Practices**:
- Use different credentials for automated workflows
- Enable workflow approval for sensitive operations
- Monitor workflow logs for errors
- Review the `[skip ci]` commits that auto-push reports

## Troubleshooting Workflow Runs

1. **View workflow logs**: Go to **Actions** tab → select workflow → click on run
2. **Check artifact downloads**: Failed artifacts are available for download
3. **Review error messages**: Logs show detailed error information
4. **Verify secrets**: Ensure all required secrets are configured
5. **Test locally first**: Run `python -m email_summary_agent --sample` to verify setup

## Disabling Workflows

To disable a workflow:
1. Go to **Actions** tab
2. Click the workflow name
3. Click **Disable workflow** (⋯ menu)

## More Information

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Managing Secrets](https://docs.github.com/en/actions/security-guides/encrypted-secrets)
- [Scheduling Workflows](https://docs.github.com/en/actions/using-workflows/events-that-trigger-workflows#schedule)
