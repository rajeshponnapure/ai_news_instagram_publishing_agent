# 📱 Instagram Carousel Quality Guide

## The Secret to Great Slides: Email Body Content

The quality of your Instagram carousel slides depends **entirely** on the email body content. This guide explains why and how to optimize.

---

## ❌ Problem: Repeated Text in Slides

**Symptom**: Slides show the same text repeated multiple times
```
Slide 1: "OpenAI releases new reasoning tools for developers"
Slide 2: "OpenAI releases new reasoning tools for developers" (repeated)
Slide 3: (empty or more repetition)
```

**Cause**: Short email body (< 250 characters) with minimal detail
- Agent can't split short text into two meaningful parts
- Slide generator fills available space by repeating what's there
- Result: boring carousel with redundant content

---

## ✅ Solution: Rich Email Body Content

Write emails with **substantial, detailed content** instead of short summaries.

### Good Email (Creates Great Slides)
```
Subject: OpenAI releases new reasoning tools for developers

Body:
OpenAI just released groundbreaking new reasoning tools that enable developers 
to build smarter AI applications.

Key highlights:
- The new o1 model includes advanced reasoning capabilities that improve 
  problem-solving on complex tasks
- Developers can now leverage chain-of-thought reasoning for better accuracy
- The tools are optimized for research, coding, and mathematical problem-solving
- OpenAI is democratizing access to powerful reasoning models through their API

This represents a major step forward in making AI reasoning capabilities 
available to the broader developer community. The tools can handle nuanced 
reasoning tasks that previously required human expertise.
```

**Result**: Slides show:
- Part 1: Full article description with context
- Part 2: Key takeaways and what's next
- Supporting notes: Company info, topics, watch points

### Bad Email (Creates Repeated Slides)
```
Subject: OpenAI releases new reasoning tools

Body: Check out: https://openai.com/research/o1
```

**Result**: Slides repeat the headline/link multiple times (boring)

---

## 🔧 Technical Details

### How Carousel Slides Are Generated

1. **Email arrives** → Agent receives email body
2. **Summarization** (optional article fetch)
   - Extracts key points from email
   - Attempts to fetch full article if URL present (may fail)
   - Falls back to email body content if fetch fails
3. **Text Splitting** 
   - If content > 250 chars: split into Part 1 + Part 2
   - If content < 250 chars: show full text in Part 1, leave Part 2 empty
4. **Slide Generation**
   - Slide 1: Image + headline
   - Slide 2 (Part 1): Main content + "Why it matters" note
   - Slide 3 (Part 2): Key takeaways + "What to watch" note (or empty)
   - Slide 4: CTA (Call-to-action, engagement prompt)

### Why Article Enrichment Isn't Reliable

The agent **tries** to fetch full articles from URLs in the email:
```
URL in email: https://openai.com/research/o1
→ Agent downloads HTML
→ Extracts title, description, paragraphs, images
→ Uses full article content for richer slides
```

**However**: 
- Many URLs return 404 (page not found)
- Some sites block automated requests (403 Forbidden)
- JavaScript-heavy sites don't work with simple HTTP fetch
- **Fallback**: Agent gracefully falls back to email body

**Solution**: Don't rely on article fetch. Write rich email bodies instead.

---

## 🎯 Best Practices for Email Content

### Do:
✅ Write 300-500+ character emails
✅ Include key highlights as bullet points
✅ Explain significance and impact
✅ Mention affected companies and technologies
✅ Add action items or what to watch for
✅ Use clear paragraph breaks

### Don't:
❌ Send short one-liners
❌ Just paste URLs without context
❌ Mix unrelated topics in one email
❌ Use cryptic abbreviations
❌ Forget to explain why it matters

### Template for Best Results
```
Subject: [Company] announces [major news item]

[Opening paragraph]: Explain what happened and why it matters
- Clear and direct, 1-2 sentences

[Key Points] (as bullet list):
- Point 1: Technical details or impact
- Point 2: Who this affects
- Point 3: What changes
- Point 4: Timeline or availability

[Significance]:
Explain broader context and implications

[Next Steps]:
What to watch for or how this might develop

[Source or Link]: Optional URL for full details
```

---

## 🚀 Testing Your Setup

Run a sample test:
```powershell
# Generate sample carousel with good email content
python -m email_summary_agent --sample
```

Check the output:
```
reports/latest.md          # Text summary
reports/instagram_posts/   # PNG carousel slides
```

Open the PNG files and verify:
- Slide 2 (Part 1): Has substantial descriptive text ✅
- Slide 3 (Part 2): Has key points or context ✅
- No visible repetition ✅
- Professional appearance ✅

---

## 📞 Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| Repeated text in slides | Email body too short (< 250 chars) | Write richer email content |
| Empty Part 2 slide | Email body is still short | Add more details to email |
| Article not fetched | URL returns 404 or 403 | Use working URLs or write full context in email |
| Slides look plain | Minimal email content | Add structured bullets and details |

---

## 💡 Pro Tips

1. **Structured Content is Best**: Use bullet points and paragraphs, not walls of text
2. **Data > Length**: 300 chars of quality content beats 500 chars of fluff
3. **Context Matters**: Explain impact, not just features
4. **Let the Summarizer Work**: Rich emails help the AI create better summaries
5. **Test and Iterate**: Run `--sample` frequently to verify quality

---

## 🔗 Related Documentation

- [README.md](README.md) - Project overview and features
- [SETUP_STEPS.md](SETUP_STEPS.md) - Installation and configuration
- [scripts/run_free_auto_publish.ps1](scripts/run_free_auto_publish.ps1) - Free cloud publishing
- [scripts/register_ai_instagram_tasks.ps1](scripts/register_ai_instagram_tasks.ps1) - Local Task Scheduler setup

---

**Remember**: The agent is only as good as the email input. Great slides come from great emails! 🚀
