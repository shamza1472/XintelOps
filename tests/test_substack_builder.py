"""Production-path tests for Substack builder: no padding, dedupe, adaptive length."""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from xintelops.delivery.cadence import enrich_result
from xintelops.delivery.email_builder import build_email_html
from xintelops.delivery.final_copy import (
    _dedupe_substack_text,
    _substack_source_depth,
    produce_final_linkedin,
    produce_final_substack,
    produce_final_x_thread,
    produce_final_x_tweet,
)
from xintelops.delivery.queue import resolve_queue

OMAN_TITLE = "Oman and Iran advance Strait of Hormuz transit fee plan despite US objections"
FILLER = "Additional reporting may clarify implementation timing, insurer response, and routing adjustments across Gulf-linked trade lanes."

SOURCES = [
    {"name": "TASS", "url": "https://tass.com/world/1980123", "why_supports": "Primary Hormuz fee reporting"},
    {"name": "Politico Europe", "url": "https://www.politico.eu/article/iran-rejects-macron-plan-clear-strait-hormuz/", "why_supports": "French proposal rejection"},
    {"name": "UN News", "url": "https://news.un.org/en/story/2026/06/1154321", "why_supports": "Hormuz reopening cost context"},
]

OMAN_SIGNAL = {
    "title": OMAN_TITLE,
    "url": "https://tass.com/world/1980123",
    "source": "TASS / Politico Europe",
    "region": "Gulf",
    "domain": "maritime",
    "why_hamza_should_care": (
        "A fee mechanism at Hormuz would reprice maritime insurance and Gulf transit behavior "
        "even if fighting stays paused."
    ),
    "verified_facts": [
        "Oman has proposed a Strait of Hormuz fee plan to the United States according to TASS reporting.",
        "Iran and Oman are moving forward with plans to collect payment for ships transiting the strait despite public US objections.",
        "Iran rejected a French proposal to clear the Strait of Hormuz according to Politico Europe reporting.",
    ],
    "live_event_score": 8,
    "consequence_score": 9,
    "new_information_detected": True,
}

ARTIFACT = Path(__file__).resolve().parents[1] / "artifacts" / "scan_result.json"


def _sentences(text: str) -> list[str]:
    return [s.strip().lower() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if len(s.strip()) > 15]


def _scan_0011(**overrides) -> dict:
    data = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    data.update(overrides)
    return data


class TestSubstackBuilder(unittest.TestCase):
    def test_substack_does_not_repeat_any_sentence(self):
        text = produce_final_substack(OMAN_SIGNAL, SOURCES).get("text", "")
        sents = _sentences(text)
        self.assertEqual(len(sents), len(set(sents)))

    def test_filler_phrase_cannot_appear(self):
        text = produce_final_substack(OMAN_SIGNAL, SOURCES).get("text", "")
        self.assertNotIn(FILLER.lower(), text.lower())
        self.assertEqual(text.lower().count("additional reporting may clarify"), 0)

    def test_scan_0011_no_repeated_filler(self):
        result = resolve_queue(enrich_result(_scan_0011()), None)
        substack = result["delivery"]["substack"]
        self.assertEqual(substack.lower().count("additional reporting may clarify"), 0)
        self.assertEqual(len(_sentences(substack)), len(set(_sentences(substack))))

    def test_thin_source_produces_shorter_note(self):
        thin_signal = {
            "title": "Routine procurement update in Baltic states",
            "region": "Europe",
            "domain": "defense procurement",
            "verified_facts": ["Latvia announced a small radar procurement review."],
        }
        thin_sources = [{"name": "Defense News", "url": "https://example.com/a", "why_supports": "Single source"}]
        text = produce_final_substack(thin_signal, thin_sources).get("text", "")
        self.assertLessEqual(len(text.split()), 450)
        self.assertGreaterEqual(len(text.split()), 50)

    def test_substack_does_not_force_500_words_on_thin_source(self):
        thin_signal = {
            "title": "Small corridor notice in Baltic shipping lanes",
            "region": "Europe",
            "domain": "maritime",
            "verified_facts": ["A port authority issued a routing notice."],
        }
        thin_sources = [{"name": "Reuters", "url": "https://example.com/b", "why_supports": "Only source"}]
        text = produce_final_substack(thin_signal, thin_sources).get("text", "")
        self.assertLess(len(text.split()), 500)

    def test_required_sections_present(self):
        text = produce_final_substack(OMAN_SIGNAL, SOURCES).get("text", "")
        for label in (
            "Thesis",
            "What changed",
            "Why it matters",
            "Second-order effects",
            "What to watch",
            "Bottom line",
        ):
            self.assertIn(label, text)

    def test_bottom_line_not_malformed(self):
        text = produce_final_substack(OMAN_SIGNAL, SOURCES).get("text", "")
        self.assertIn("Bottom line", text)
        self.assertNotRegex(text, r"What to monitor:\.?\s*$")
        self.assertIn("price passage", text.lower())

    def test_sentence_dedup_runs_before_render(self):
        raw = (
            "Title Here\n\nThesis\nSame point twice. Same point twice.\n\n"
            "What changed\nUpdate confirmed."
        )
        deduped = _dedupe_substack_text(raw)
        self.assertEqual(deduped.lower().count("same point twice"), 1)

    def test_email_renders_deduped_substack_only(self):
        result = resolve_queue(enrich_result(_scan_0011()), None)
        substack = result["delivery"]["substack"]
        html = build_email_html(result)
        self.assertIn("COPY THIS - SUBSTACK", html)
        self.assertIn("Bottom line", html)
        self.assertEqual(html.lower().count("additional reporting may clarify"), 0)
        self.assertIn(substack.split("\n\n")[0], html)

    def test_other_delivery_formats_unchanged(self):
        result = resolve_queue(enrich_result(_scan_0011()), None)
        delivery = result["delivery"]
        self.assertTrue(delivery["x_tweet"])
        self.assertGreaterEqual(len(delivery["x_thread"]), 4)
        self.assertGreaterEqual(len(delivery["linkedin"]), 700)
        self.assertIn("Not active yet", delivery["youtube_note"])
        self.assertEqual(delivery["suggested_format"], "THREAD")

    def test_hormuz_target_quality_sections(self):
        text = produce_final_substack(OMAN_SIGNAL, SOURCES).get("text", "")
        self.assertIn("Hormuz Risk Is Moving From Shock Pricing To Structural Pricing", text)
        self.assertIn("pricing chokepoint", text.lower())
        self.assertIn("who gets to price passage", text.lower())

    def test_multi_source_depth_classification(self):
        self.assertEqual(_substack_source_depth(OMAN_SIGNAL, SOURCES), "deep")

    def test_direct_producers_still_independent(self):
        tweet = produce_final_x_tweet(OMAN_SIGNAL, SOURCES).get("text", "")
        thread = produce_final_x_thread(OMAN_SIGNAL, SOURCES).get("display", "")
        linkedin = produce_final_linkedin(OMAN_SIGNAL, SOURCES).get("text", "")
        self.assertTrue(any(k in tweet.lower() for k in ("pricing chokepoint", "fee mechanism", "repric")))
        self.assertIn("1/", thread)
        self.assertGreaterEqual(len(linkedin), 700)


class TestSubstackBeforeAfter(unittest.TestCase):
    BAD_SUBSTACK = (
        "Oman and Iran advance Strait of Hormuz transit fee plan despite US objections Thesis\n"
        "A fee mechanism at Hormuz would reprice maritime insurance.\n"
        f"{FILLER} {FILLER} {FILLER}"
    )

    def test_before_after_no_filler_repetition(self):
        after = produce_final_substack(OMAN_SIGNAL, SOURCES).get("text", "")
        self.assertGreaterEqual(self.BAD_SUBSTACK.lower().count("additional reporting may clarify"), 2)
        self.assertEqual(after.lower().count("additional reporting may clarify"), 0)


if __name__ == "__main__":
    unittest.main()
