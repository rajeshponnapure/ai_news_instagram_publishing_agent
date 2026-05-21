from __future__ import annotations

import unittest
from datetime import datetime

from email_summary_agent.digest import parse_news_items
from email_summary_agent.instagram import _build_slide_specs, _split_summary_for_carousels
from email_summary_agent.models import EmailItem, EmailSummary


class DigestPipelineTests(unittest.TestCase):
    def test_single_news_email_creates_four_slide_plan(self) -> None:
        summary = _summary_with_articles(1)

        parts = _split_summary_for_carousels(summary)
        slides = _build_slide_specs(parts[0], datetime(2026, 5, 21, 9, 0))

        self.assertEqual(len(parts), 1)
        self.assertEqual([slide["kind"] for slide in slides], ["image", "text", "text", "cta"])

    def test_two_news_digest_creates_seven_slide_plan(self) -> None:
        summary = _summary_with_articles(2)

        parts = _split_summary_for_carousels(summary)
        slides = _build_slide_specs(parts[0], datetime(2026, 5, 21, 9, 0))

        self.assertEqual(len(parts), 1)
        self.assertEqual(len(slides), 7)
        self.assertEqual([slide["kind"] for slide in slides], ["image", "text", "text", "image", "text", "text", "cta"])

    def test_four_news_digest_splits_into_two_carousel_parts(self) -> None:
        summary = _summary_with_articles(4)

        parts = _split_summary_for_carousels(summary)
        slide_counts = [len(_build_slide_specs(part, datetime(2026, 5, 21, 9, 0))) for part in parts]

        self.assertEqual(len(parts), 2)
        self.assertEqual(slide_counts, [10, 4])
        self.assertTrue(parts[0].headline.endswith("Part 1"))
        self.assertTrue(parts[1].headline.endswith("Part 2"))

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


def _summary_with_articles(count: int) -> EmailSummary:
    articles = [
        {
            "url": f"https://example.com/story-{index}",
            "title": f"Story {index} headline",
            "description": f"Story {index} describes an important AI update with enough detail for a summary slide. "
            f"It explains what changed, who it affects, and what to watch next.",
            "excerpt": f"Story {index} excerpt with useful context for creators and developers.",
            "image_path": "",
            "image_url": "",
        }
        for index in range(1, count + 1)
    ]
    return EmailSummary(
        message_key="digest",
        subject="Daily AI Digest",
        source_date="Thu, 21 May 2026 09:00:00 +0530",
        headline="Daily AI Digest",
        summary="A daily collection of AI news.",
        key_points=["AI companies shipped multiple updates.", "Developers should watch adoption."],
        companies=["OpenAI", "AWS"],
        models=[],
        topics=["developer tools"],
        confidence=0.8,
        article_items=articles,
    )


if __name__ == "__main__":
    unittest.main()
