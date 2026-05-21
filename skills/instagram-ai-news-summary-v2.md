# Instagram AI News Summary V2 Skill

Purpose: turn one AI-news blog/article into a detailed, human-readable Instagram carousel story.

## Output Contract
- One story should produce one image/reference slide plus three detailed content slides.
- The content must be useful enough that a viewer understands the article without opening the source link.
- Do not write generic category labels such as "model release", "developer tools", or "primary entities to watch" as the main substance.
- Do not invent facts. If the article does not say it, do not add it.
- Use the project RAG knowledge base before writing: retrieve relevant rules, angles, and patterns from `data/knowledge_base/instagram_ai_content.json`.
- Treat RAG patterns as editorial guidance, not facts. Facts must come from the opened article/blog.

## Story Structure
1. What happened:
   - State the real announcement or event clearly.
   - Name the company/product/person if available.
   - Include concrete details such as model names, API names, launch names, pricing, dates, partners, regions, or affected users.
2. Why it matters:
   - Explain the practical impact in simple language.
   - Connect the update to developers, creators, companies, AI users, or the market.
   - Avoid hype unless the source gives a real reason for it.
3. What to watch next:
   - Explain the next signal to watch: rollout, adoption, pricing, competition, limitations, risks, benchmarks, or user reaction.
   - Make it feel like a human tech-news editor wrote it.

## Writing Voice
- Plain English, but not boring.
- Short paragraphs with strong verbs.
- Human editorial tone: specific, direct, curious, and grounded.
- Use words that help Instagram readers care: "why it matters", "the bigger signal", "what changes", "watch this next", "the catch", "the practical impact".
- Avoid robotic phrasing: "This article discusses", "The email indicates", "Primary entities", "Likely themes".
- Avoid filler: "in the rapidly evolving world", "game changer", "revolutionary", unless the article proves it.

## RAG/NLP Workflow
1. Clean the article text first: remove cookie banners, footers, decorative symbols, email unsubscribe text, and legal boilerplate.
2. Retrieve relevant knowledge-base entries using the article title, article description, article body, company/model names, and topic.
3. Use retrieved rules to choose the best angle: product impact, market signal, research capability, regulation/safety, or creator-facing explanation.
4. Summarize the full article into an editorial narrative:
   - What actually happened.
   - Why it matters in practical terms.
   - What signal to watch next.
5. Rewrite into human-readable Instagram language. Do not paste raw article sentences unless they are already clear and specific.
6. Keep every claim grounded in the article source.

## Visual Rules
- Main headline must be bold and large.
- Neon green section labels must be readable and larger than small metadata text.
- White body content should fill the slide without overflowing.
- If the article has an image, use that image and fit the entire image without cropping.
- If the article has no image, use a relevant public reference image only when the search result matches the article subject. Otherwise use a clean source/title card.

## Caption Rules
- Lead with the actual news, not a category.
- Include a short disclaimer that this is an AI-assisted summary.
- Include source links where available.
- Keep hashtags relevant to the article entities and AI topic.
