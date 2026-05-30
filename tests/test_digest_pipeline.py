from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from email_summary_agent.article_enricher import extract_article_urls
from email_summary_agent.agent import _email_scan_due
from email_summary_agent.article_quality import is_publishable_article
from email_summary_agent.config import Settings
from email_summary_agent.content_rag import retrieve_context
from email_summary_agent.db import AgentStore
from email_summary_agent.digest import parse_news_items
from email_summary_agent.email_client import extract_body
from email_summary_agent.instagram import _build_slide_specs
from email_summary_agent.ig_image import _find_library_image
from email_summary_agent.ig_slide_builder import _split_summary_for_carousels
from email_summary_agent.models import EmailItem, EmailSummary
from email_summary_agent.summarizer import _article_item_for_instagram, _format_prompt_body, SummaryProvider
from email_summary_agent.article_enricher import ArticleData
from email_summary_agent.ig_copy import layout_safe_headline, layout_safe_points, trim_without_ellipsis
from email_summary_agent.ig_keypoints import _extract_instagram_key_points
from email_summary_agent.renderer import _build_slide_html
from email_summary_agent.verifier import verify_pre_publish


class DigestPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        # _find_reference_image_for_article_unique lives in ig_image and is
        # called internally by _select_unique_article_image there.
        self._reference_patch = patch(
            "email_summary_agent.ig_image._find_reference_image_for_article_unique",
            return_value=None,
        )
        self._reference_patch.start()
        # Suppress live network calls so the test suite runs offline and fast.
        # _fetch_og_image_from_url is called from two places after the refactor:
        # once inside ig_image (internal calls) and once via ig_slide_builder's
        # imported name -- patch both namespaces to suppress all network traffic.
        self._og_patch = patch(
            "email_summary_agent.ig_image._fetch_og_image_from_url",
            return_value=None,
        )
        self._og_patch.start()
        self._og_patch2 = patch(
            "email_summary_agent.ig_slide_builder._fetch_og_image_from_url",
            return_value=None,
        )
        self._og_patch2.start()
        # _scrape_article_text is imported into ig_slide_builder from ig_utils.
        self._scrape_patch = patch(
            "email_summary_agent.ig_slide_builder._scrape_article_text",
            return_value=None,
        )
        self._scrape_patch.start()
        # Also patch the library image lookup to avoid hitting cached images.
        self._lib_patch = patch(
            "email_summary_agent.ig_image._find_library_image_unique",
            return_value=None,
        )
        self._lib_patch.start()

    def tearDown(self) -> None:
        self._reference_patch.stop()
        self._og_patch.stop()
        self._og_patch2.stop()
        self._scrape_patch.stop()
        self._lib_patch.stop()

    def test_single_short_news_email_creates_slide_plan(self) -> None:
        summary = _summary_with_articles(1)

        parts = _split_summary_for_carousels(summary)
        slides = _build_slide_specs(parts[0], datetime(2026, 5, 21, 9, 0))

        self.assertEqual(len(parts), 1)
        # Unified layout: one article produces one slide.
        self.assertEqual(slides[0]["kind"], "digest")
        self.assertEqual(len(slides), 2)
        self.assertEqual(slides[-1]["kind"], "cta")

    def test_single_long_news_email_creates_more_keypoints(self) -> None:
        summary = _summary_with_articles(1, long=True)

        parts = _split_summary_for_carousels(summary)
        short_slides = _build_slide_specs(_summary_with_articles(1), datetime(2026, 5, 21, 9, 0))
        long_slides = _build_slide_specs(parts[0], datetime(2026, 5, 21, 9, 0))

        self.assertEqual(len(parts), 1)
        self.assertGreaterEqual(len(long_slides), len(short_slides))

    def test_two_news_stories_create_carousel(self) -> None:
        summary = _summary_with_articles(2)

        parts = _split_summary_for_carousels(summary)
        slides = _build_slide_specs(parts[0], datetime(2026, 5, 21, 9, 0))

        self.assertEqual(len(parts), 1)
        self.assertEqual(len(slides), 3)
        self.assertEqual(slides[0]["kind"], "digest")
        self.assertEqual(slides[1]["kind"], "digest")
        self.assertEqual(slides[-1]["kind"], "cta")

    def test_four_news_stories_split_into_multiple_carousel_parts(self) -> None:
        summary = _summary_with_articles(4)

        parts = _split_summary_for_carousels(summary)
        slide_counts = [len(_build_slide_specs(part, datetime(2026, 5, 21, 9, 0))) for part in parts]

        # Unified batching: 4 articles all fit in a single carousel post
        self.assertEqual(len(parts), 1)
        self.assertEqual(slide_counts[0], 5)
        self.assertEqual(parts[0].headline, "AI News Update")

    def test_article_batches_are_fixed_groups_of_eight(self) -> None:
        cases = {
            1: [1],
            5: [5],
            8: [8],
            9: [8, 1],
            17: [8, 8, 1],
            50: [8, 8, 8, 8, 8, 8, 2],
        }
        expected_slides = {
            1: [2],
            5: [6],
            8: [9],
            9: [9, 2],
            17: [9, 9, 2],
            50: [9, 9, 9, 9, 9, 9, 3],
        }

        for article_count, expected_counts in cases.items():
            with self.subTest(article_count=article_count):
                parts = _split_summary_for_carousels(_summary_with_articles(article_count))
                actual_counts = [len(part.article_items or []) for part in parts]
                self.assertEqual(actual_counts, expected_counts)

                slide_counts = [
                    len(_build_slide_specs(part, datetime(2026, 5, 21, 9, 0)))
                    for part in parts
                ]
                self.assertEqual(slide_counts, expected_slides[article_count])

    def test_digest_parser_extracts_one_story_per_url(self) -> None:
        email = EmailItem(
            uid="1",
            message_id="<digest@example.com>",
            sender="grdevelopers.co@gmail.com",
            subject="AI Digest - TechCrunch AI, AWS Machine Learning",
            date="Thu, 21 May 2026 09:00:00 +0530",
            body=(
                "1. OpenAI launches a new coding model\n"
                "The model improves agent workflows.\n"
                "https://example.com/openai-coding-model\n\n"
                "2. AWS improves real-time voice inference\n"
                "SageMaker adds a lower-latency deployment path.\n"
                "https://aws.example.com/voice-inference\n"
            ),
        )

        items = parse_news_items(email, max_links=10)

        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].title, "OpenAI launches a new coding model")
        self.assertIn("voice inference", items[1].title.lower())

    def test_single_link_alert_ignores_for_more_details_label(self) -> None:
        email = EmailItem(
            uid="1",
            message_id="<single@example.com>",
            sender="grdevelopers.co@gmail.com",
            subject="OpenAI releases new reasoning tools for developers",
            date="Thu, 21 May 2026 09:00:00 +0530",
            body=(
                "OpenAI released reasoning tools for developers.\n\n"
                "Key highlights:\n"
                "- The o1 model improves complex problem solving.\n"
                "- Developers can use stronger reasoning in API workflows.\n\n"
                "For more details, visit: https://openai.com/research/reasoning"
            ),
        )

        items = parse_news_items(email, max_links=0)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "OpenAI released reasoning tools for developers.")
        self.assertIn("o1 model improves complex problem solving", items[0].context)
        self.assertNotEqual(items[0].context.lower(), "for more details, visit:")

    def test_publishability_rejects_promo_noise_and_url_slug_titles(self) -> None:
        promo = {
            "url": "https://techcrunch.com/events/disrupt-early-bird",
            "title": "Get Disrupt Early Bird savings",
            "description": "Startups are the core of TechCrunch, so get our best coverage delivered weekly.",
            "text": "Early Bird ticket savings of up to $410 end May 29 at 11:59 p.m.",
        }
        slug = {
            "url": "https://www.bloomberg.com/news/articles/2026-05-30/ovation-and-ai-technology-ai-university-waterloo-labs",
            "title": "Ovation-and-ai technology ai university-waterloo-labs",
            "description": "This AI startup will clean your home for free to train future robots.",
            "text": "The robotics company is using real-world household tasks to improve AI robot training.",
        }
        real_story = {
            "url": "https://aws.amazon.com/blogs/networking-and-content-delivery/url-and-domain-category-filtering-aws-network-firewall",
            "title": "AWS adds URL and domain category filtering to Network Firewall",
            "description": "AWS Network Firewall now lets teams manage URL and domain categories without manually curating every domain list.",
            "text": "The policy update helps security teams keep application controls current as AI services, developer platforms, and new SaaS domains change.",
        }

        self.assertFalse(is_publishable_article(promo))
        self.assertFalse(is_publishable_article(slug))
        self.assertTrue(is_publishable_article(real_story))

    def test_html_email_preserves_link_hrefs(self) -> None:
        message = EmailMessage()
        message["Subject"] = "AI Alert"
        message.set_content("Plain fallback without links")
        message.add_alternative(
            '<html><body><h2>LangChain launch</h2><a href="https://example.com/langchain-launch">Read more</a></body></html>',
            subtype="html",
        )

        body = extract_body(message)
        urls = extract_article_urls(body)

        self.assertIn("https://example.com/langchain-launch", urls)

    def test_missing_article_image_returns_empty_path(self) -> None:
        summary = _summary_with_articles(1)

        with patch("email_summary_agent.ig_image._find_reference_image_for_article_unique", return_value=None):
            slides = _build_slide_specs(summary, datetime(2026, 5, 21, 9, 0))

        # Unified layout: first slide is always kind="digest"
        self.assertEqual(slides[0]["kind"], "digest")
        self.assertEqual(slides[0]["image_path"], "")

    def test_renderer_omits_blank_image_panel_when_image_missing(self) -> None:
        html = _build_slide_html(
            {
                "kind": "digest",
                "eyebrow": "Industry",
                "title": "Blue Origin&#x27;s New Glenn test fails during Florida run",
                "body": "Blue Origin&#x27;s rocket test ended early during a controlled Florida trial.\nEngineers now have a cleaner failure window to inspect before the next attempt.",
                "source_label": "example.com",
                "image_path": "",
                "url": "https://example.com/blue-origin-ai-test",
            },
            1,
            2,
            datetime(2026, 5, 21, 9, 0),
        )

        self.assertNotIn('<div class="digest-image"', html)
        self.assertIn("digest-body no-image", html)
        self.assertNotIn("&amp;#x27;", html)
        self.assertIn("Blue Origin&#x27;s New Glenn test fails during Florida run", html)

    def test_article_slide_uses_only_same_article_image(self) -> None:
        summary = _summary_with_articles(1)
        with TemporaryDirectory() as tmp:
            image_path = Path(tmp) / "article-image.jpg"
            image_path.write_bytes(b"same article image")
            summary.article_items[0]["image_path"] = str(image_path)

            slides = _build_slide_specs(summary, datetime(2026, 5, 21, 9, 0))

        self.assertEqual(slides[0]["image_path"], str(image_path))
        self.assertEqual(slides[0]["image_source"], "article")

    def test_verifier_blocks_digest_slide_without_article_image(self) -> None:
        report = verify_pre_publish(
            [
                {
                    "kind": "digest",
                    "title": "AWS updates Network Firewall policy controls.",
                    "body": "Security teams get stronger control over fast-changing domains.",
                    "url": "https://example.com/aws-firewall",
                    "image_path": "",
                    "image_source": "",
                },
                {"kind": "cta", "title": "SAVE THIS.", "body": "", "image_path": ""},
            ]
        )

        self.assertFalse(report.passed)
        self.assertTrue(any(c.check_id == 6 and not c.passed for c in report.checks))

    def test_email_scan_gate_waits_for_configured_interval(self) -> None:
        with TemporaryDirectory() as tmp:
            store = AgentStore(Path(tmp) / "agent.sqlite3")
            store.initialize()
            key = "last_email_scan_at|INBOX|sender@example.com"
            store.set_state(key, datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"))

            self.assertFalse(_email_scan_due(store, key, 50))

            old = datetime.now(timezone.utc).astimezone() - timedelta(minutes=51)
            store.set_state(key, old.isoformat(timespec="seconds"))
            self.assertTrue(_email_scan_due(store, key, 50))
            store.close()

    def test_image_library_rejects_unrelated_cached_image(self) -> None:
        with TemporaryDirectory() as tmp:
            image_dir = Path(tmp)
            (image_dir / "abc123.jpg").write_bytes(b"fake image")
            (image_dir / "index.json").write_text(
                '{"images":[{"id":"abc123","path":"' + str(image_dir / "abc123.jpg").replace("\\", "\\\\") + '","seed":"OpenAI GPT model launch","tokens":["openai","model"]}]}',
                encoding="utf-8",
            )
            with patch("email_summary_agent.ig_image.IMAGE_LIBRARY_DIR", image_dir), patch(
                "email_summary_agent.ig_image.IMAGE_INDEX_PATH", image_dir / "index.json"
            ):
                self.assertIsNone(_find_library_image("AWS voice inference deployment"))
                self.assertEqual(_find_library_image("OpenAI GPT developer model"), str(image_dir / "abc123.jpg"))

    def test_rag_retrieves_creator_rules_for_ai_launch(self) -> None:
        context = retrieve_context("OpenAI released a new developer API and model launch", limit=2)

        self.assertTrue(context.rules)
        self.assertTrue(any("product" in entry.get("id", "") or "editorial" in entry.get("id", "") for entry in context.entries))

    def test_article_item_includes_retrieved_rag_metadata(self) -> None:
        article = ArticleData(
            url="https://example.com/openai-api",
            title="OpenAI launches a developer API for agents",
            description="OpenAI launched an API that helps developers build agent workflows.",
            text="OpenAI launched an API that helps developers build agent workflows. The update improves tool use and deployment for teams.",
        )

        item = _article_item_for_instagram(article)

        self.assertTrue(item["rag_angles"])
        self.assertTrue(item["rag_rules"])

    def test_full_extract_prompt_keeps_whole_blog_text(self) -> None:
        body = "Paragraph one with details.\n\nParagraph two with more details.\n\nParagraph three finishes the story."

        self.assertEqual(_format_prompt_body(body, full_extract=True), body)

    def test_full_extract_summary_includes_later_blog_details(self) -> None:
        provider = SummaryProvider(provider="local", ollama_url="http://localhost:11434", ollama_model="llama3.2:3b")
        email = EmailItem(
            uid="1",
            message_id="<blog@example.com>",
            sender="writer@example.com",
            subject="Blog post",
            date="Thu, 21 May 2026 09:00:00 +0530",
            body="",
        )
        article = ArticleData(
            url="https://example.com/blog",
            title="Long blog post",
            description="First part explains the launch.",
            text=(
                "First part explains the launch. "
                "Second part gives technical details and rollout notes. "
                "Final part explains limitations, follow-up steps, and why readers should care."
            ),
        )

        summary = provider.summarize(email, article=article)

        self.assertIn("Final part explains limitations", summary.summary)
        self.assertGreaterEqual(len(summary.key_points), 3)

    def test_creator_copy_is_layout_safe(self) -> None:
        headline = layout_safe_headline(
            "Final answer in last AIMessage for TodoListMiddleware (#37643)"
        )
        points = layout_safe_points([
            "Dismiss alert {{ message }} langchain-ai / langgraph Public Notifications You must be signed in to change.",
            "Scientists found something shocking that could affect millions of AI users worldwide.",
            "Developers can ship reliable agent workflows without stitching fragile scripts together.",
        ])

        self.assertLessEqual(len(headline.split()), 7)
        self.assertTrue(points)
        self.assertTrue(all("..." not in point for point in points))
        self.assertTrue(all(len(point.split()) <= 16 for point in points))
        self.assertFalse(any("dismiss alert" in point.lower() for point in points))
        self.assertFalse(any("here is the key detail" in point.lower() for point in points))
        self.assertEqual(
            trim_without_ellipsis("This sentence is intentionally much too long for a carousel text box", 32)[-1],
            ".",
        )

    def test_blocked_page_text_never_becomes_keypoints(self) -> None:
        summary = _summary_with_articles(1)
        article = {
            "url": "https://www.bloomberg.com/example",
            "title": "Bloomberg are you a robot",
            "description": "Get the most important global markets news at your fingertips with a Bloomberg.com subscription.",
            "scraped_content": (
                "We've detected unusual activity from your computer network. "
                "To continue, please click the box below. "
                "For inquiries related to this message please contact our support team."
            ),
        }

        points = _extract_instagram_key_points(article, summary, max_points=4)

        joined = " ".join(points).lower()
        self.assertNotIn("are you a robot", joined)
        self.assertNotIn("unusual activity", joined)
        self.assertNotIn("support team", joined)
        self.assertNotIn("subscription", joined)

    def test_article_slides_do_not_reuse_global_summary_points(self) -> None:
        summary = _summary_with_articles(2)
        summary.key_points[:] = [
            "Global repeated fallback point that should not appear on every article slide.",
            "Second repeated fallback point that should not appear on every article slide.",
        ]

        slides = _build_slide_specs(summary, datetime(2026, 5, 21, 9, 0))
        bodies = [slide["body"] for slide in slides if slide.get("kind") == "digest"]

        self.assertEqual(len(bodies), 2)
        self.assertNotEqual(bodies[0], bodies[1])
        self.assertFalse(any("global repeated fallback" in body.lower() for body in bodies))

    def test_article_prefixed_titles_remain_publishable_content(self) -> None:
        summary = _summary_with_articles(3)
        for index, item in enumerate(summary.article_items or [], start=1):
            item["title"] = f"Article {index} AI launch changes developer workflows"
            item["description"] = (
                f"Article {index} reveals a specific AI update with adoption signals, "
                "numbers, and practical developer impact."
            )

        slides = _build_slide_specs(summary, datetime(2026, 5, 21, 9, 0))

        self.assertEqual(len(slides), 4)
        self.assertEqual(slides[-1]["kind"], "cta")
        digest = [s for s in slides if s.get("kind") == "digest"]
        self.assertEqual(len(digest), 3)
        self.assertTrue(all(len(slide.get("summary_lines", [])) >= 1 for slide in digest))
        self.assertTrue(all(len(slide.get("key_points", [])) == 4 for slide in digest))
        self.assertTrue(all("global repeated fallback" not in slide["body"].lower() for slide in digest))

    def test_digest_slides_have_editorial_heading_summary_and_four_keypoints(self) -> None:
        summary = _summary_with_articles(1)
        item = summary.article_items[0]
        item["title"] = "AWS adds URL and domain category filtering to Network Firewall"
        item["description"] = (
            "AWS Network Firewall now lets administrators use URL and domain categories "
            "to keep security policies current. The update reduces manual domain-list "
            "maintenance as AI services and SaaS endpoints change. Security teams can "
            "align firewall controls with application categories instead of chasing every domain by hand."
        )
        item["excerpt"] = ""

        slides = _build_slide_specs(summary, datetime(2026, 5, 21, 9, 0))
        digest = slides[0]

        self.assertEqual(digest["kind"], "digest")
        self.assertTrue(digest["title"].endswith("."))
        self.assertEqual(len(digest["summary_lines"]), 3)
        self.assertEqual(len(digest["key_points"]), 4)
        self.assertTrue(all(point.endswith(".") for point in digest["key_points"]))
        self.assertFalse(any("story 1" in point.lower() for point in digest["key_points"]))


def _summary_with_articles(count: int, long: bool = False) -> EmailSummary:
    detail = (
        "It explains what changed, who it affects, what technical details matter, how the market could react, "
        "why developers should care, what adoption signals are worth watching, and what limitations or follow-up "
        "announcements would make the update more important for real-world AI workflows. "
    )
    if long:
        detail = detail * 5
    articles = [
        {
            "url": f"https://example.com/story-{index}",
            "title": f"Story {index} headline",
            "description": f"Story {index} describes an important AI update with enough detail for a summary slide. "
            f"{detail}",
            "excerpt": f"Story {index} excerpt with useful context for creators and developers.",
            "image_path": "",
            "image_url": "",
        }
        for index in range(1, count + 1)
    ]
    return EmailSummary(
        message_key="test",
        subject="AI News Update",
        source_date="Thu, 21 May 2026 09:00:00 +0530",
        headline="AI News Update",
        summary="A daily collection of AI news.",
        key_points=["AI companies shipped multiple updates.", "Developers should watch adoption."],
        companies=["OpenAI", "AWS"],
        models=[],
        topics=["developer tools"],
        confidence=0.8,
        article_items=articles,
    )


def _settings(**overrides) -> Settings:
    values = dict(
        imap_host="imap.gmail.com",
        imap_port=993,
        imap_username="user@example.com",
        imap_password="password",
        email_sender_filter="sender@example.com",
        email_folder="INBOX",
        lookback_hours=48,
        max_emails_per_run=5,
        poll_interval_minutes=15,
        email_check_interval_minutes=50,
        summary_provider="local",
        ollama_url="http://localhost:11434",
        ollama_model="llama3.2:3b",
        db_path=Path(":memory:"),
        reports_dir=Path("reports"),
        instagram_dir=Path("reports/instagram_posts"),
        create_instagram_posts=True,
        process_all_matching=False,
        enrich_articles=True,
        max_article_links_per_email=20,
        article_assets_dir=Path("data/article_assets"),
        public_media_base_url="https://example.github.io/reports/instagram_posts",
        auto_publish_instagram=True,
        ig_user_id="17841447323115790",
        ig_access_token="ig-token",
        ig_api_version="v24.0",
        gemini_api_key="",
        gemini_model="gemini-2.5-flash",
    )
    values.update(overrides)
    return Settings(**values)


if __name__ == "__main__":
    unittest.main()
