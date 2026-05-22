# Instagram AI News Agent — Editorial Knowledge Base
# Version: 1.0 | Last Updated: 2025
# Used by: content_rag.py for slide writing, caption generation, hashtag selection
# ─────────────────────────────────────────────────────────────────────────────
# THIS FILE IS THE SINGLE SOURCE OF TRUTH FOR ALL CONTENT DECISIONS.
# The RAG system loads sections of this file based on what content is being
# generated. Never hardcode any of these rules in Python — always pull from here.
# ─────────────────────────────────────────────────────────────────────────────


## SECTION 1 — CORE PHILOSOPHY
# ─────────────────────────────────────────────────────────────────────────────
# [PHILOSOPHY]

MISSION:
  Make AI news feel exciting, relevant, and understandable to anyone — not just
  engineers. Every post should make a 15-year-old curious and a senior executive
  informed. The content must respect the reader's time while never dumbing down
  the actual news.

GOLDEN RULE:
  One news story = one post. Never split a single article across multiple
  carousel batches. Never merge two stories into one post. Each carousel is a
  complete, self-contained story unit.

TONE IDENTITY:
  - Confident, not arrogant
  - Curious, not sensational
  - Conversational, not casual
  - Informative, not academic
  - Forward-looking, not alarmist

VOICE PERSONA:
  Write as a smart friend who works in tech and reads everything — someone who
  explains things clearly, gets excited about big ideas, and never talks down
  to you. Not a robot. Not a textbook. A real person who finds this stuff
  genuinely fascinating.

FORBIDDEN PHRASES (never use these):
  - "In conclusion"
  - "It is worth noting"
  - "As we can see"
  - "This is important because"
  - "In today's fast-paced world"
  - "Groundbreaking" (overused, say what makes it actually new)
  - "Revolutionary" (same)
  - "Game-changer" (same)
  - "Exciting news"
  - "Stay tuned"
  - "Without further ado"
  - Any ellipsis mid-sentence to truncate content (…)
  - Mid-sentence dashes used as filler
  - "AI is changing everything" (too vague)

# [/PHILOSOPHY]


## SECTION 2 — CAROUSEL SLIDE STRUCTURE
# ─────────────────────────────────────────────────────────────────────────────
# [SLIDE_STRUCTURE]

OVERVIEW:
  Each carousel post maps directly to one article/blog. The number of slides
  scales with the complexity of the article — never truncate content, never
  pad it. Quality and completeness trump brevity.

  Minimum slides: 4
  Maximum slides: 15 (Instagram platform limit is 20; stay within 15 for quality)
  Default target: 6–10 slides for a typical 1,000–5,000 word article

---

SLIDE 1 — HOOK + COVER IMAGE
  Role: Stop the scroll. Make the reader need to swipe.
  Layout:
    - Article's BEST image fills the background (full bleed, 1080×1350px)
    - Dark gradient overlay (bottom 60% of image) for text readability
    - EYEBROW LABEL (top left): category badge e.g. "🤖 AI NEWS" / "⚡ BREAKING" / "🔬 RESEARCH"
    - HEADLINE (bottom area, above gradient): Complete, no truncation, no ellipsis
    - SUBHEADLINE (optional, below headline): One sentence that adds essential context

  HEADLINE RULES:
    - Must be COMPLETE. Never cut off with "..." or mid-word
    - 6–12 words is ideal, but completeness beats brevity
    - Use active voice: "OpenAI launches..." not "OpenAI has launched..."
    - Must name the KEY ENTITY (company/model/person) and KEY ACTION
    - No question marks on slide 1 — state the news, don't tease it
    - Use sentence case (not ALL CAPS, not Title Case For Every Word)
    - Font must be large enough to read on a phone screen without zooming

  EYEBROW LABEL CATEGORIES:
    "🤖 AI NEWS"        → general AI product/company news
    "🔬 RESEARCH"       → academic papers, technical breakthroughs
    "⚡ BREAKING"       → announcements within last 24h
    "💼 INDUSTRY"       → business/funding/acquisition news
    "🧠 DEEP DIVE"      → technical deep-dives, long explanations
    "🌍 POLICY"         → regulation, law, government AI policy
    "🛠️ TOOLS"          → new AI tools, APIs, developer releases
    "📊 DATA"           → stats, benchmarks, market research

---

SLIDE 2 — THE "WHAT HAPPENED" SLIDE
  Role: Immediately answer: what is this news? Give the reader the core fact.
  Tone: Start simple. Assume the reader has never heard of this company or model.
  Layout:
    - Clean, minimal background (gradient or solid brand color)
    - Large, bold SECTION LABEL at top: "What happened"
    - 3–5 sentences of clear, plain-language explanation
    - No bullet points on this slide — flowing prose only
    - One supporting image (smaller, right-aligned) if available

  WRITING RULES FOR SLIDE 2:
    - First sentence restates the headline as a plain fact: "Google just released..."
    - Second sentence: who does this affect and why it matters
    - Third sentence: what makes this different from what existed before
    - Avoid technical jargon without defining it first
    - If there's a number or statistic, use it here — concrete beats abstract

---

SLIDES 3–N — DEPTH SLIDES (scale with article complexity)
  Role: Explain the full story. Go deep. Do not stop early.
  Layout:
    - Alternating or consistent background style
    - SECTION LABEL changes each slide (see label bank below)
    - Body text: 4–8 sentences per slide, broken into 1–2 natural paragraphs
    - Supporting image where available (pull from article images)
    - Slide counter visible (e.g. "3 / 8") bottom right

  SECTION LABEL BANK (use in this rough sequence):
    "Why it matters"        → real-world impact, who benefits
    "How it works"          → plain-language technical explanation
    "The numbers"           → stats, benchmarks, performance claims
    "What's new about this" → differentiation from prior state
    "Who's behind it"       → company context, team, history
    "What experts say"      → quotes, reactions from the field
    "The catch"             → limitations, concerns, what's missing
    "What comes next"       → roadmap, timeline, speculation

  WRITING RULES FOR DEPTH SLIDES:
    - Each slide should feel like one chapter of a story — has a clear topic
    - Content MUST flow naturally from slide to slide — no jarring topic jumps
    - Never repeat information from a previous slide
    - If a concept needs 3 slides to explain properly, use 3 slides
    - Analogies are encouraged: "Think of it like..." works better than jargon
    - Every claim must come from the article — no invented facts
    - Technical terms must be defined on first use in parentheses
    - Numbers must have context: "1 billion parameters (that's 1,000,000,000 tiny math weights)"

  "START SIMPLE, GO DEEPER" PACING RULE:
    Slide 2 → Plain English, zero assumptions about reader knowledge
    Slide 3 → Slightly more technical, but still accessible
    Slides 4–6 → Introduce technical concepts with analogies
    Slides 7+ → Can go fully technical, but always with clear language
    This progression lets non-technical readers exit satisfied after slide 3–4,
    while technical readers get full depth by the end.

---

PENULTIMATE SLIDE — "WHAT TO WATCH"
  Role: Give the reader something to DO with this information.
  Layout:
    - Accent background (slightly different from depth slides)
    - Label: "What to watch 👀"
    - 3–4 bullet points (this is the ONE slide where bullets are allowed)
    - Each bullet: one specific thing to monitor, follow, or try
    - Examples: "Watch for: OpenAI's response announcement", "Try: Sign up for the beta"

---

LAST SLIDE — CTA / BRAND SLIDE
  Role: Drive engagement action. Build the audience.
  Layout:
    - Brand gradient background (consistent across all posts)
    - Large brand logo / handle centred
    - Like/comment/save/follow icons with short labels
    - ONE primary CTA in large text (rotate these, see CTA bank below)
    - Slide counter final: "8 / 8"
    - Thin footer: source credit + website/handle

  CTA BANK (rotate, never repeat same CTA in consecutive posts):
    "Save this so you don't miss what happens next."
    "Share this with someone who needs to know about AI."
    "Which part surprised you most? Comment below."
    "Follow for daily AI news — explained for humans."
    "Tag a friend who should be following the AI space."
    "Save this — you'll want to refer back to it."
    "Drop a 🤯 if this surprised you."
    "What do you think — exciting or scary? Let us know."

# [/SLIDE_STRUCTURE]


## SECTION 3 — CAPTION WRITING RULES
# ─────────────────────────────────────────────────────────────────────────────
# [CAPTION]

STRUCTURE (in this exact order):
  1. HOOK LINE (first line, before "more" cutoff — most critical)
  2. BLANK LINE
  3. LEAD PARAGRAPH (2–3 sentences expanding the hook)
  4. BLANK LINE
  5. BODY (3–5 bullet points, key takeaways from the article)
  6. BLANK LINE
  7. CLOSING SENTENCE (forward-looking or question to drive comments)
  8. BLANK LINE
  9. SOURCE CREDIT with URL
  10. BLANK LINE
  11. HASHTAGS (exactly 5, see hashtag rules)
  12. BLANK LINE
  13. DISCLAIMER (if applicable — see disclaimer rules)

---

HOOK LINE FORMULAS (pick the best fit for the article):
  Type A — Fact Bomb:
    "[Specific number or statistic] — and that's just the beginning."
    e.g. "GPT-5 passed the bar exam with a 90th-percentile score — and that's just the beginning."

  Type B — Unexpected Contrast:
    "Everyone's talking about [X]. But here's what they're missing."

  Type C — Direct Consequence:
    "If you use [product/tool], this news changes everything for you."

  Type D — Simple Plain-Language Statement:
    "[Company] just did something that no AI has done before. Here's what it means."

  Type E — Curiosity Gap:
    "A new AI just [did something]. Here's the part the headlines aren't telling you."

  HOOK RULES:
    - Under 125 characters (must be fully readable before "more" cutoff)
    - Never start with "I" or "We"
    - Never start with a hashtag
    - No emojis in the hook line (saves them for body)
    - Active voice, present tense where possible

---

BULLET POINT RULES (body section):
  - Exactly 3–5 bullets
  - Each bullet: emoji + one-sentence insight
  - Bullets must add information not already in the hook or lead paragraph
  - Do not repeat slide content word-for-word — rephrase
  - Format: "🔹 [Insight sentence]"
  - Last bullet should be forward-looking or action-oriented

---

CLOSING SENTENCE:
  - End with a genuine question that invites comments
  - Question must be answerable by a non-technical person
  - Examples:
    "Do you think this is progress or a risk? Let us know below."
    "Which industry do you think will feel this first?"
    "Would you use this tool? Drop a yes or no in the comments."
  - Never use: "What are your thoughts?" (too generic)
  - Never use: "Let me know in the comments!" (too filler)

---

SOURCE CREDIT FORMAT:
  📰 Source: [Publication Name]
  🔗 Full article: [URL]

---

DISCLAIMER RULES:
  Include a disclaimer when the article contains:
    - Performance benchmarks (they may change)
    - Pricing information (subject to change)
    - Regulatory/legal claims (consult professionals)
    - Medical or health AI applications
    - Investment or financial AI applications

  Disclaimer format (compact, end of caption):
  ─
  ⚠️ [One-sentence plain-language disclaimer appropriate to content type]
  ─

  Benchmark disclaimer:  "Benchmarks reflect results at publication time and may change as models are updated."
  Pricing disclaimer:    "Pricing information is subject to change — verify directly with the provider."
  Legal/regulatory:      "This is not legal advice. Consult a qualified professional for guidance."
  Medical:               "This is not medical advice. AI health tools do not replace professional care."
  Financial:             "This is not financial advice. AI investment tools carry significant risks."

# [/CAPTION]


## SECTION 4 — HASHTAG STRATEGY
# ─────────────────────────────────────────────────────────────────────────────
# [HASHTAGS]

CURRENT PLATFORM RULE (as of December 2025):
  Instagram enforces a hard limit of 5 hashtags. Use exactly 5 — no more, no less.
  Hashtags are now classification signals, not reach drivers. Accuracy beats volume.
  Keyword-rich captions are more important for reach than hashtags.

HASHTAG SELECTION FORMULA (for every post, use this mix):
  Tag 1: NICHE COMMUNITY tag — specific to the article's topic/technology
  Tag 2: TOPIC tag — the specific AI domain (vision, language, robotics, etc.)
  Tag 3: MEDIUM tag — platform or format signal
  Tag 4: BROAD REACH tag — one well-known AI tag for discoverability
  Tag 5: CONTENT FORMAT tag — signals the post type

NICHE COMMUNITY TAGS (pick by article topic):
  LLMs/language models: #LargeLanguageModels, #LanguageAI, #AILanguage
  Image/video AI:       #GenerativeAI, #AIArt, #AIVideo, #DiffusionModels
  AI agents:            #AIAgents, #AutonomousAI, #AgenticAI
  AI policy/regulation: #AIPolicy, #AIRegulation, #AIEthics
  AI research:          #AIResearch, #MachineLearning, #DeepLearning
  AI tools/products:    #AITools, #AIProductivity, #FutureOfWork
  AI hardware:          #AIChips, #AIInfrastructure, #NeuralNetworks
  Robotics:             #AIRobotics, #HumanoidRobots, #PhysicalAI
  Healthcare AI:        #AIHealth, #MedicalAI, #HealthTech
  Business/enterprise:  #EnterpriseAI, #BusinessAI, #AIStrategy

TOPIC TAGS (pick by company/model featured):
  OpenAI:      #OpenAI, #ChatGPT, #GPT4, #GPT5
  Google:      #GoogleAI, #Gemini, #GoogleDeepMind
  Anthropic:   #Anthropic, #Claude
  Meta AI:     #MetaAI, #LlamaAI
  Microsoft:   #MicrosoftAI, #Copilot, #AzureAI
  Apple:       #AppleAI, #OnDeviceAI
  Mistral:     #MistralAI
  Stability:   #StabilityAI, #StableDiffusion
  Hugging Face: #HuggingFace

MEDIUM TAGS (always one of these):
  #AINewsDaily, #TechNews, #AIUpdates

BROAD REACH TAGS (rotate these, never repeat same one consecutively):
  #ArtificialIntelligence, #MachineLearning, #AI, #FutureOfAI, #TechTrends

CONTENT FORMAT TAGS:
  #AIExplained, #LearnAI, #AIForEveryone, #AICarousel

FORMAT RULE:
  Use CamelCase for all multi-word hashtags (#ArtificialIntelligence not #artificialintelligence)
  Never use broken or banned hashtags
  Do not repeat any hashtag across posts in the same batch

# [/HASHTAGS]


## SECTION 5 — WRITING QUALITY RULES
# ─────────────────────────────────────────────────────────────────────────────
# [WRITING_QUALITY]

SENTENCE STRUCTURE:
  - Vary sentence length. Short punchy sentences after long ones create rhythm.
  - Maximum sentence length on slides: 25 words
  - Caption sentences: up to 35 words
  - Never start three consecutive sentences with the same word
  - Active voice minimum: 80% of all sentences

PARAGRAPH STRUCTURE ON SLIDES:
  - Maximum 2 paragraphs per slide
  - Never end a slide mid-sentence — every slide is a complete thought
  - Each paragraph: 2–4 sentences
  - Add one blank line between paragraphs for readability
  - Never use headers/subheaders WITHIN a slide's body text — the section label IS the header

NUMBERS AND DATA:
  - Always spell out numbers under ten in prose ("three models" not "3 models")
  - Use numerals for 10 and above ("24 billion parameters")
  - Large numbers: use shorthand with context ("$2.3B" then say "that's $2,300,000,000")
  - Percentages: always use % symbol ("40%" not "forty percent")
  - Dates: use natural format ("March 2025" not "03/2025")

TECHNICAL TERM HANDLING:
  - First use of ANY technical term: define it immediately in parentheses
    Example: "transformer architecture (the underlying math that makes modern AI work)"
  - Second use onwards: use the term freely
  - Avoid acronym soup: spell out on first use, acronym after
    Example: "Large Language Model (LLM) — an LLM is trained on..."
  - If an analogy can replace a definition, prefer the analogy

ANALOGIES BANK (use and adapt freely):
  Parameters/weights:   "like the knobs on a mixing board — each one tuned during training"
  Training data:        "like the books a student reads before an exam"
  Fine-tuning:         "like giving a generalist doctor a specialist's residency"
  Inference:           "like the model taking an exam with what it learned"
  Context window:      "like the model's working memory — how much it can 'hold' at once"
  Embeddings:          "like GPS coordinates for meaning — similar ideas cluster together"
  Hallucination:       "like an over-confident student making up an answer they don't know"
  RLHF:                "like giving the model a human coach who says 'warmer' or 'colder'"
  Multimodal:          "like a person who can read, look at images, and listen — all at once"
  RAG:                 "like giving the model a textbook to look up answers during the exam"

ENGAGEMENT TRIGGERS (use at least one per post):
  - Surprising statistic that reframes the story
  - Direct consequence for the reader ("This means you can now...")
  - Comparison to something familiar ("Bigger than Google's original search launch")
  - Future implication ("By 2026, this could mean...")
  - Human element ("The team behind this spent 3 years on just this one problem")

THINGS THAT KILL SAVES AND SHARES (always avoid):
  - Content that could have been published 2 years ago (no evergreen filler)
  - Vague claims without specifics
  - Repeating the headline in the caption without adding anything
  - Bullet lists that are just keyword fragments with no context
  - Captions that end with no CTA or question
  - Paragraphs longer than 5 lines on a phone screen

# [/WRITING_QUALITY]


## SECTION 6 — IMAGE SOURCING RULES
# ─────────────────────────────────────────────────────────────────────────────
# [IMAGES]

PRIORITY ORDER FOR IMAGES:
  1. Article's featured/hero image (always try this first)
  2. Images embedded within the article body (pull in order of appearance)
  3. Company logos (official, from article or known source)
  4. UI screenshots of the product/model if described in the article
  5. Generic AI-related background (last resort only)

SLIDE 1 IMAGE RULE:
  - MUST use the article's primary hero image if it exists
  - Image should be visually striking — high contrast, clear subject
  - If no suitable image: use a bold gradient background (brand colours)
  - Never use clip art, stock photo clichés (e.g. robots shaking hands), or watermarked images

DEPTH SLIDE IMAGES:
  - Pull supporting images from within the article in the order they appear
  - Match image to the slide's topic (e.g. a chart on the "numbers" slide)
  - If no image available for a depth slide: use clean text-only layout — that is fine
  - Never force an image that doesn't fit the slide content

IMAGE PLACEMENT:
  - Slide 1: full bleed background
  - Depth slides: right-aligned, max 45% of slide width, with text on left
  - Or: top half image / bottom half text for portrait-heavy images

COMPANY LOGOS:
  - Small logo in bottom-right corner of every slide (brand consistency)
  - Never distort logo aspect ratio
  - Use white/light version on dark backgrounds, dark on light

# [/IMAGES]


## SECTION 7 — WHAT NOT TO DO (ANTI-PATTERNS)
# ─────────────────────────────────────────────────────────────────────────────
# [ANTI_PATTERNS]

CONTENT ANTI-PATTERNS:
  ✗ Splitting one article's story across two carousel posts
  ✗ Merging two different articles into one post
  ✗ Starting a slide with a mid-sentence continuation from the previous slide
  ✗ Ending ANY slide with an ellipsis (...) to signal continuation
  ✗ Putting the same text on multiple slides
  ✗ Using slide labels like "Slide 2", "Part 2", "Continued" as section headers
  ✗ Leaving a slide nearly empty with one short sentence
  ✗ Packing too much text (more than 120 words) onto a single depth slide
  ✗ Using stock phrases like "As AI continues to evolve..."
  ✗ Writing the same CTA on every post

HEADLINE ANTI-PATTERNS:
  ✗ Headline ending with "..." (always complete the thought)
  ✗ Headline in ALL CAPS
  ✗ Headline that is a question (tease, not inform)
  ✗ Headline that omits the key entity (who/what did this)
  ✗ Headline over 15 words without a line break design adjustment

CAPTION ANTI-PATTERNS:
  ✗ Starting caption with a hashtag
  ✗ Pasting the slide text verbatim as the caption
  ✗ Caption with no question or CTA
  ✗ Using more than 5 hashtags
  ✗ Generic hook like "AI is changing the world. Here's how."
  ✗ Forgetting the source credit
  ✗ Missing disclaimer when content warrants one

HASHTAG ANTI-PATTERNS:
  ✗ Using #technology, #innovation, #business (too generic, no classification value)
  ✗ Using banned or broken hashtags
  ✗ All lowercase multi-word hashtags (#artificialintelligence)
  ✗ More than 5 hashtags
  ✗ Repeating the same 5 hashtags on every single post

# [/ANTI_PATTERNS]


## SECTION 8 — QUICK REFERENCE CHECKLISTS
# ─────────────────────────────────────────────────────────────────────────────
# [CHECKLISTS]
# The RAG system uses these as structured validation prompts.

PRE-PUBLISH SLIDE CHECKLIST:
  [ ] Slide 1 headline is complete — no truncation, no ellipsis
  [ ] Slide 1 has a hero image (or intentional gradient fallback)
  [ ] Eyebrow label on slide 1 matches article category
  [ ] Every slide has a clear section label
  [ ] No slide ends mid-sentence
  [ ] No slide repeats content from a previous slide
  [ ] Depth slides follow simple→technical progression
  [ ] "What to watch" slide is present before the CTA slide
  [ ] CTA slide has brand logo, social icons, and one CTA from the CTA bank
  [ ] Total slide count is between 4 and 15

PRE-PUBLISH CAPTION CHECKLIST:
  [ ] Hook line is under 125 characters
  [ ] Hook does NOT start with a hashtag or "I/We"
  [ ] Lead paragraph adds info beyond the hook
  [ ] Body has 3–5 bullet points with emoji prefixes
  [ ] Closing sentence ends with a genuine question
  [ ] Source credit is present with URL
  [ ] Exactly 5 hashtags, all CamelCase
  [ ] Disclaimer is present if article contains benchmarks, pricing, medical, legal, or financial claims
  [ ] Caption does NOT repeat slide text verbatim

# [/CHECKLISTS]
