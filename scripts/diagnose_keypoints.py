"""Diagnose keypoints output quality by simulating realistic AI news articles through the pipeline."""

from __future__ import annotations
import sys
import re
sys.path.insert(0, ".")

from email_summary_agent.models import EmailItem, EmailSummary
from email_summary_agent.summarizer import SummaryProvider
from email_summary_agent.article_enricher import ArticleData
from email_summary_agent.ig_keypoints import _extract_instagram_key_points
from email_summary_agent.editorial_page import build_editorial_page_copy
from email_summary_agent.ig_copy import clean_creator_text


def simulate_article(title: str, description: str, text: str, url: str) -> ArticleData:
    return ArticleData(
        url=url,
        title=title,
        description=description,
        text=text,
    )


def run_diagnostic() -> None:
    print("=" * 80)
    print("KEYPOINTS QUALITY DIAGNOSTIC")
    print("=" * 80)

    # Scenario 1: Model release (OpenAI)
    print("\n\n" + "=" * 80)
    print("SCENARIO 1: OpenAI model release -- structured article")
    print("-" * 80)

    article1 = simulate_article(
        title="OpenAI launches GPT-5 with multimodal reasoning, real-time inference, and 10x context window",
        description=(
            "OpenAI launched GPT-5, its most advanced model yet, featuring native multimodal "
            "reasoning across text, images, and audio, a 10x larger context window (2M tokens), "
            "and real-time inference capabilities. The model reportedly achieves a 92% pass rate "
            "on advanced coding benchmarks. Enterprise API pricing starts at $0.15 per 1K tokens "
            "with tiered access for developers."
        ),
        text=(
            "OpenAI launched GPT-5 on May 28, 2026, positioning it as a direct competitor to "
            "Google's Gemini 2.5 and Anthropic's Claude 4. The model processes text, images, and "
            "audio natively without separate vision or speech pipelines. Early benchmarks show GPT-5 "
            "achieving 92% on the HumanEval coding benchmark and 88% on MMLU-Pro. The context "
            "window expands to 2 million tokens, up from 128K in GPT-4. OpenAI prices the model "
            "at $0.15 per 1K input tokens and $0.60 per 1K output tokens for the full tier. "
            "Developer access opens today. A free tier with limited rate limits is available through "
            "ChatGPT. The launch signals OpenAI's aggressive push to maintain market leadership "
            "as competitors release increasingly capable models. Analysts project the AI model "
            "market will reach $128 billion by 2028."
        ),
        url="https://openai.com/blog/gpt-5-launch",
    )

    provider = SummaryProvider(provider="local")
    email1 = EmailItem(
        uid="1", message_id="<test@test>", sender="newsletter@aiweekly.com",
        subject="OpenAI launches GPT-5", date="Thu, 28 May 2026 10:00:00 +0000",
        body="",
    )
    summary1 = provider.summarize(email1, article=article1, articles=[article1])
    
    # Build the article dict as the pipeline would
    from email_summary_agent.summarizer import _article_item_for_instagram
    article_dict1 = _article_item_for_instagram(article1)
    
    points1 = _extract_instagram_key_points(article_dict1, summary1, max_points=5)
    
    print(f"\nHEADLINE: {summary1.headline}")
    print(f"\nSTRUCTURED SECTIONS:")
    print(f"  WHAT HAPPENED: {article_dict1.get('what_happened', '')[:200]}")
    print(f"  WHY MATTERS:   {article_dict1.get('why_matters', '')[:200]}")
    print(f"  WHAT TO WATCH: {article_dict1.get('what_to_watch', '')[:200]}")
    print(f"\nKEY POINTS ({len(points1)}):")
    for i, pt in enumerate(points1, 1):
        print(f"  {i}. {pt}")
    
    # Evaluate quality
    print(f"\nQUALITY CHECK:")
    _evaluate_points(points1, "OpenAI")

    # Scenario 2: Enterprise business deal (AWS)
    print("\n\n" + "=" * 80)
    print("SCENARIO 2: AWS enterprise security update -- business/enterprise angle")
    print("-" * 80)

    article2 = simulate_article(
        title="AWS adds URL and domain category filtering to Network Firewall",
        description=(
            "AWS Network Firewall now lets administrators use URL and domain categories "
            "to keep security policies current. The update reduces manual domain-list "
            "maintenance as AI services and SaaS endpoints change. Security teams can "
            "align firewall controls with application categories instead of chasing every domain by hand."
        ),
        text=(
            "AWS announced URL and domain category filtering for Network Firewall on May 27. "
            "The feature groups URLs and domains into categories like SaaS, AI services, "
            "streaming, and social media. Security teams set allow/block policies at the "
            "category level. AWS says the update reduces policy drift as new domains launch. "
            "Over 300 categories ship with the initial release. The feature supports integration "
            "with AWS Organizations for multi-account deployment. Pricing follows standard "
            "Network Firewall rates with no additional per-category charge. Enterprise customers "
            "with complex compliance requirements can submit custom category requests."
        ),
        url="https://aws.amazon.com/blogs/networking-and-content-delivery/url-and-domain-category-filtering-aws-network-firewall",
    )

    email2 = EmailItem(
        uid="2", message_id="<test2@test>", sender="newsletter@awsweekly.com",
        subject="AWS adds network filtering", date="Wed, 27 May 2026 14:00:00 +0000",
        body="",
    )
    summary2 = provider.summarize(email2, article=article2, articles=[article2])
    article_dict2 = _article_item_for_instagram(article2)
    points2 = _extract_instagram_key_points(article_dict2, summary2, max_points=5)

    print(f"\nHEADLINE: {summary2.headline}")
    print(f"\nKEY POINTS ({len(points2)}):")
    for i, pt in enumerate(points2, 1):
        print(f"  {i}. {pt}")
    _evaluate_points(points2, "AWS")

    # Scenario 3: Research paper (DeepMind)
    print("\n\n" + "=" * 80)
    print("SCENARIO 3: DeepMind research paper -- academic/research angle")
    print("-" * 80)

    article3 = simulate_article(
        title="DeepMind achieves 99.2% accuracy on medical diagnosis benchmark with new multimodal model",
        description=(
            "DeepMind researchers published a paper demonstrating a new multimodal model that "
            "achieves 99.2% accuracy on medical diagnosis benchmarks, surpassing board-certified "
            "physicians who scored 94.8%. The model processes X-rays, MRIs, patient histories, and "
            "lab results simultaneously. DeepMind is partnering with three major hospital networks "
            "for clinical trials beginning Q3 2026."
        ),
        text=(
            "DeepMind's new medical AI model, MedGemini, achieves 99.2% accuracy across 47 "
            "diagnostic categories in controlled benchmark testing. Board-certified physicians "
            "achieved 94.8% on the same tests. The model processes imaging data, clinical notes, "
            "laboratory results, and patient history in a single pass using a novel multimodal "
            "architecture. DeepMind is partnering with Mayo Clinic, Johns Hopkins, and the NHS "
            "for clinical trials starting in Q3 2026. The paper notes that while benchmark "
            "performance is strong, real-world deployment requires careful validation for "
            "patient populations not well represented in training data. The model demonstrates "
            "particular strength in dermatological diagnosis (99.7%) and radiology (98.9%), "
            "with slightly lower performance in rare disease identification (87.3%). "
            "DeepMind emphasizes that the model is designed to assist rather than replace "
            "physicians, providing differential diagnoses and supporting evidence."
        ),
        url="https://deepmind.google/research/medgemini",
    )

    email3 = EmailItem(
        uid="3", message_id="<test3@test>", sender="newsletter@researchdigest.com",
        subject="DeepMind medical AI breakthrough", date="Tue, 26 May 2026 08:00:00 +0000",
        body="",
    )
    summary3 = provider.summarize(email3, article=article3, articles=[article3])
    article_dict3 = _article_item_for_instagram(article3)
    points3 = _extract_instagram_key_points(article_dict3, summary3, max_points=5)

    print(f"\nHEADLINE: {summary3.headline}")
    print(f"\nKEY POINTS ({len(points3)}):")
    for i, pt in enumerate(points3, 1):
        print(f"  {i}. {pt}")
    _evaluate_points(points3, "DeepMind")

    # Scenario 4: Startup funding news
    print("\n\n" + "=" * 80)
    print("SCENARIO 4: AI startup raises $500M -- business/funding angle")
    print("-" * 80)

    article4 = simulate_article(
        title="Anthropic raises $500M Series E at $85B valuation for enterprise AI expansion",
        description=(
            "Anthropic raised $500 million in Series E funding at an $85 billion valuation, "
            "bringing total funding to over $15 billion. The company plans to use the capital "
            "to expand enterprise sales teams, build dedicated data centers in Europe and Asia, "
            "and accelerate Claude 5 development. Google participated in the round alongside "
            "existing investors."
        ),
        text=(
            "Anthropic closed a $500 million Series E funding round at an $85 billion valuation, "
            "more than doubling its valuation from the previous $40 billion round in March. "
            "The round was led by Google with participation from Spark Capital and existing "
            "investors. Anthropic says it will use the funds to triple its enterprise sales "
            "organization, build data centers in Frankfurt and Tokyo, and invest in Claude 5 "
            "training runs. The company's annualized revenue has grown to $2.8 billion, up from "
            "$850 million last year, driven primarily by enterprise API usage. Anthropic now "
            "serves over 200,000 enterprise customers, up from 60,000 a year ago. The funding "
            "comes as the AI infrastructure arms race intensifies, with competitors OpenAI and "
            "Google also raising billions for compute capacity."
        ),
        url="https://techcrunch.com/anthropic-series-e",
    )

    email4 = EmailItem(
        uid="4", message_id="<test4@test>", sender="newsletter@techcrunch.com",
        subject="Anthropic raises $500M", date="Mon, 25 May 2026 12:00:00 +0000",
        body="",
    )
    summary4 = provider.summarize(email4, article=article4, articles=[article4])
    article_dict4 = _article_item_for_instagram(article4)
    points4 = _extract_instagram_key_points(article_dict4, summary4, max_points=5)

    print(f"\nHEADLINE: {summary4.headline}")
    print(f"\nKEY POINTS ({len(points4)}):")
    for i, pt in enumerate(points4, 1):
        print(f"  {i}. {pt}")
    _evaluate_points(points4, "Anthropic")

    # Scenario 5: Developer tool (GitHub)
    print("\n\n" + "=" * 80)
    print("SCENARIO 5: GitHub Copilot agentic coding -- developer/tools angle")
    print("-" * 80)

    article5 = simulate_article(
        title="GitHub Copilot launches autonomous coding agents that can build entire features from a prompt",
        description=(
            "GitHub Copilot introduced autonomous coding agents capable of building entire "
            "features from a single natural language prompt. The agents write code, create tests, "
            "run them, and fix bugs autonomously. Developers review and approve changes before "
            "merge. Early testers report 3x faster feature delivery. Available in VS Code today."
        ),
        text=(
            "GitHub Copilot's new agentic mode lets developers describe a feature in plain language "
            "and have Copilot build it end-to-end: planning the implementation, writing code, "
            "creating unit tests, building the application, running tests, and iterating on failures. "
            "The developer reviews a diff before merging. Early access testers at Shopify, Stripe, "
            "and Vercel report average 3x faster feature delivery for full-stack features. "
            "GitHub says the agents handle the full lifecycle for CRUD operations, API endpoints, "
            "and UI components. The feature uses a new multi-step reasoning architecture powered "
            "by OpenAI's o4 model. Available now in VS Code and GitHub Codespaces. Pricing is "
            "included in the $39/month Copilot Enterprise plan."
        ),
        url="https://github.blog/copilot-agentic-features",
    )

    email5 = EmailItem(
        uid="5", message_id="<test5@test>", sender="newsletter@github.blog",
        subject="GitHub Copilot agents", date="Fri, 29 May 2026 09:00:00 +0000",
        body="",
    )
    summary5 = provider.summarize(email5, article=article5, articles=[article5])
    article_dict5 = _article_item_for_instagram(article5)
    points5 = _extract_instagram_key_points(article_dict5, summary5, max_points=5)

    print(f"\nHEADLINE: {summary5.headline}")
    print(f"\nKEY POINTS ({len(points5)}):")
    for i, pt in enumerate(points5, 1):
        print(f"  {i}. {pt}")
    _evaluate_points(points5, "GitHub")

    # ── Overall summary ──
    print("\n\n" + "=" * 80)
    print("OVERALL SUMMARY")
    print("=" * 80)
    all_scenarios = [
        ("OpenAI GPT-5 Launch", points1),
        ("AWS Network Firewall", points2),
        ("DeepMind MedGemini", points3),
        ("Anthropic $500M Raise", points4),
        ("GitHub Copilot Agents", points5),
    ]
    
    total_points = 0
    creator_labels_used = set()
    for name, pts in all_scenarios:
        total_points += len(pts)
        for pt in pts:
            label_match = re.match(r"^([A-Z][A-Z ]{2,24}):\s+", pt)
            if label_match:
                creator_labels_used.add(label_match.group(1))
    
    print(f"\nTotal scenarios: 5")
    print(f"Total key points generated: {total_points}")
    print(f"Unique creator labels used: {sorted(creator_labels_used)}")
    print(f"Avg points per article: {total_points / 5:.1f}")


def _evaluate_points(points: list[str], brand: str) -> None:
    """Evaluate key points against editorial quality standards."""
    issues = []
    strengths = []
    
    if len(points) < 4:
        issues.append(f"Only {len(points)} points (target: 4-5)")
    elif len(points) >= 5:
        strengths.append(f"Strong count: {len(points)} points")
    
    brand_lower = brand.lower()
    brand_mention = any(brand_lower in pt.lower() for pt in points)
    if brand_mention:
        strengths.append("Brand (" + brand + ") mentioned in at least one point")
    else:
        issues.append("Brand (" + brand + ") not mentioned in any point")
    
    action_verbs = [
        "launches", "launched", "releases", "released", "achieves", "beats",
        "surpasses", "reveals", "breaks", "builds", "cuts", "doubles",
        "enables", "expands", "introduces", "introduced", "joins", "reaches",
        "replaces", "sets", "ships", "shows", "trains", "upgrades",
        "announces", "unveils", "raises", "adds", "brings", "opens",
    ]
    action_count = sum(1 for pt in points if any(v in pt.lower().split() for v in action_verbs))
    if action_count >= 2:
        strengths.append(f"Strong action verbs in {action_count} points")
    elif action_count == 1:
        strengths.append(f"Action verb in 1 point")
    else:
        issues.append("No action verbs detected in any point")
    
    numbers_found = sum(1 for pt in points if re.search(r"\b\d[\d,]*\.?\d*\s*(?:%|x|B|M|K|bn|mn|billion|million|percent|times)\b", pt, re.I))
    if numbers_found >= 2:
        strengths.append(f"Data/number-driven: {numbers_found} points with concrete numbers")
    elif numbers_found == 1:
        strengths.append(f"1 point with concrete number")
    else:
        issues.append("No concrete numbers found in any point")
    
    ai_sounding = [
        "this means", "this highlights", "it is important", "furthermore",
        "additionally", "overall", "in conclusion", "keep an eye on",
        "where things stand", "the landscape",
    ]
    for phrase in ai_sounding:
        for pt in points:
            if phrase in pt.lower():
                issues.append("AI-sounding phrase: '" + phrase + "' in: " + pt[:60])
                break
    
    creator_labels = sum(1 for pt in points if re.match(r"^[A-Z][A-Z ]{2,24}:\s+", pt))
    if creator_labels >= 2:
        strengths.append(f"Creator labels on {creator_labels} points: variety is good")
    elif creator_labels == len(points):
        strengths.append("All points have creator labels")
    
    # Storytelling flow: check for narrative progression
    if len(points) >= 3:
        first_words = [pt.split()[0].lower().strip(".,:!?") for pt in points if pt.split()]
        has_flow_variety = len(set(first_words[:3])) >= 2
        if has_flow_variety:
            strengths.append("Good narrative variety in sentence starts")
    
    # Each point should be 8-22 words for layout and impact
    word_counts = [len(pt.split()) for pt in points]
    avg_words = sum(word_counts) / len(word_counts) if word_counts else 0
    good_length = all(8 <= wc <= 22 for wc in word_counts)
    if good_length:
        strengths.append(f"Well-bounded word count (avg {avg_words:.0f} words)")
    
    print(f"  STRENGTHS ({len(strengths)}):")
    for s in strengths:
        print(f"    + {s}")
    if issues:
        print(f"  ISSUES ({len(issues)}):")
        for issue in issues:
            print(f"    - {issue}")
    else:
        print(f"  No issues found!")


if __name__ == "__main__":
    run_diagnostic()
