from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from email_summary_agent.article_enricher import extract_article_urls
from email_summary_agent.agent import _email_scan_due
from email_summary_agent.config import Settings
from email_summary_agent.content_rag import retrieve_context
from email_summary_agent.db import AgentStore
from email_summary_agent.digest import parse_news_items
from email_summary_agent.email_client import extract_body
from email_summary_agent.instagram import _build_slide_specs, _find_library_image, _split_summary_for_carousels
from email_summary_agent.models import EmailItem, EmailSummary
from email_summary_agent.summarizer import _article_item_for_instagram, _format_prompt_body, SummaryProvider
from email_summary_agent.article_enricher import ArticleData


class DigestPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self._reference_patch = patch("email_summary_agent.instagram._find_reference_image_for_article_unique", return_value=None)
        self._reference_patch.start()

    def tearDown(self) -> None:
        self._reference_patch.stop()

    def test_single_short_news_email_creates_slide_plan(self) -> None:
        summary = _summary_with_articles(1)

        parts = _split_summary_for_carousels(summary)
        slides = _build_slide_specs(parts[0], datetime(2026, 5, 21, 9, 0))

        self.assertEqual(len(parts), 1)
        self.assertEqual(slides[0]["kind"], "title")
        self.assertGreater(len(slides), 3)
        self.assertEqual(slides[-1]["kind"], "cta")
        self.assertTrue(all(s["kind"] in ("title", "list", "cta") for s in slides))

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
        self.assertGreater(len(slides), 4)
        self.assertEqual(slides[0]["kind"], "title")
        self.assertEqual(slides[-1]["kind"], "cta")
        kinds = [s["kind"] for s in slides]
        self.assertIn("list", kinds)
        self.assertEqual(kinds.count("title"), 2)

    def test_four_news_stories_split_into_multiple_carousel_parts(self) -> None:
        summary = _summary_with_articles(4)

        parts = _split_summary_for_carousels(summary)
        slide_counts = [len(_build_slide_specs(part, datetime(2026, 5, 21, 9, 0))) for part in parts]

        self.assertEqual(len(parts), 2)
        self.assertGreater(slide_counts[0], 4)
        self.assertGreater(slide_counts[1], 4)
        self.assertEqual(parts[0].headline, "AI News Update")
        self.assertEqual(parts[1].headline, "AI News Update")

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

    def test_missing_article_image_generates_branded_fallback(self) -> None:
        summary = _summary_with_articles(1)

        with patch("email_summary_agent.instagram._find_reference_image_for_article_unique", return_value=None):
            slides = _build_slide_specs(summary, datetime(2026, 5, 21, 9, 0))

        self.assertEqual(slides[0]["kind"], "title")
        self.assertTrue(slides[0]["image_path"], "Title slide must always have an image (branded fallback)")

    def test_missing_article_image_can_use_reference_search_result(self) -> None:
        summary = _summary_with_articles(1)

        with patch("email_summary_agent.instagram._find_reference_image_for_article_unique", return_value="data/article_assets/reference.jpg"):
            slides = _build_slide_specs(summary, datetime(2026, 5, 21, 9, 0))

        self.assertEqual(slides[0]["image_path"], "data/article_assets/reference.jpg")

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
            with patch("email_summary_agent.instagram.IMAGE_LIBRARY_DIR", image_dir), patch(
                "email_summary_agent.instagram.IMAGE_INDEX_PATH", image_dir / "index.json"
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
    )
    values.update(overrides)
    return Settings(**values)


if __name__ == "__main__":
    unittest.main()
