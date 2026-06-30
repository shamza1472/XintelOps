"""Production-path regression tests for copy desk editorial upgrade (SCAN-2026-06-30-2339)."""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from xintelops.delivery.cadence import enrich_result
from xintelops.delivery.crisis_tier import classify_scan_tier
from xintelops.delivery.email_builder import build_email_html
from xintelops.delivery.final_copy import produce_final_linkedin, produce_final_x_thread
from xintelops.delivery.queue import resolve_queue
from xintelops.delivery.source_roles import render_source_package_html

OMAN_TITLE = "Oman and Iran advance Strait of Hormuz transit fee plan despite US objections"

ARTIFACT = Path(__file__).resolve().parents[1] / "artifacts" / "scan_result.json"


def _scan_2339(**overrides) -> dict:
    data = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    data.update(overrides)
    return data


def _resolved(**overrides) -> dict:
    result = enrich_result(_scan_2339(**overrides))
    return resolve_queue(result, None)


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip().lower() for p in parts if len(p.strip()) > 20]


def _assert_no_em_dash(text: str) -> None:
    assert "—" not in text and "–" not in text, f"em dash found in: {text[:120]}"


class TestCopyDeskFixScan2339(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = _resolved()
        cls.delivery = cls.result["delivery"]
        cls.html = build_email_html(cls.result)
        cls.linkedin = cls.delivery["linkedin"]
        cls.thread_display = cls.delivery["x_thread_display"]
        cls.thread_tweets = cls.delivery["x_thread"]
        cls.substack = cls.delivery["substack"]

    def test_linkedin_does_not_repeat_same_sentence(self):
        sents = _sentences(self.linkedin)
        self.assertEqual(len(sents), len(set(sents)))

    def test_linkedin_never_ends_with_what_to_monitor_malformed(self):
        self.assertNotRegex(self.linkedin, r"What to monitor:\.?\s*$")
        self.assertNotIn("What to monitor:.", self.linkedin)

    def test_linkedin_length_700_to_1200(self):
        self.assertGreaterEqual(len(self.linkedin), 700)
        self.assertLessEqual(len(self.linkedin), 1200)

    def test_thread_has_no_xintelops_footer(self):
        self.assertNotIn("XIntelOps | Strategic signal brief", self.thread_display)
        self.assertNotRegex(self.thread_display.lower(), r"xintelops\s*\|\s*strategic signal brief")

    def test_thread_tweet_4_is_grammatical_and_complete(self):
        self.assertGreaterEqual(len(self.thread_tweets), 4)
        tweet4 = self.thread_tweets[3]
        self.assertTrue(tweet4.endswith("."))
        self.assertNotRegex(tweet4.lower(), r"next readouts also rejected")
        self.assertIn("pressure point", tweet4.lower())

    def test_thread_has_no_repeated_sentence(self):
        normalized = [t.strip().lower() for t in self.thread_tweets]
        self.assertEqual(len(normalized), len(set(normalized)))

    def test_substack_exists_in_delivery_object(self):
        self.assertTrue(self.delivery.get("substack"))
        self.assertIn("substack", self.result["delivery"])
        self.assertIn("Thesis", self.substack)

    def test_email_renders_copy_this_substack(self):
        self.assertIn("COPY THIS - SUBSTACK", self.html)

    def test_substack_not_in_source_package(self):
        buckets = self.result["operator_block"]["x"].get("source_buckets") or {}
        source_html = render_source_package_html(buckets, lambda x: str(x))
        self.assertNotIn("Thesis", source_html)
        self.assertNotIn("Second-order effects", source_html)

    def test_suggested_format_and_labels_consistent(self):
        delivery = self.result["operator_block"]["delivery"]
        x_html = self.html.split("X - post now")[1].split("Suggested format")[0]
        self.assertIn("Suggested format:", self.html)
        self.assertNotIn("Recommended format:", self.html)
        self.assertNotIn("Action:</span> X POST", x_html)
        self.assertTrue(delivery.get("suggested_format"))
        self.assertTrue(delivery.get("also_included"))
        self.assertIn("Also included:", self.html)

    def test_crisis_header_uses_selected_signal_tier(self):
        tier_meta = self.result["crisis_tier_meta"]
        self.assertEqual(tier_meta["immediate_tier"], "LIVE_EVENT")
        self.assertFalse(tier_meta["crisis_detected"])
        self.assertIn("TIER <span>LIVE_EVENT</span>", self.html)
        self.assertIn("CRISIS <span>NO</span>", self.html)

    def test_email_contains_all_four_copy_blocks(self):
        for label in (
            "COPY THIS - SINGLE TWEET",
            "COPY THIS - THREAD",
            "COPY THIS - LINKEDIN",
            "COPY THIS - SUBSTACK",
        ):
            self.assertIn(label, self.html)

    def test_no_visible_generated_copy_contains_em_dash(self):
        visible = "\n".join(
            [
                self.delivery.get("x_tweet", ""),
                self.thread_display,
                self.linkedin,
                self.substack,
            ]
        )
        _assert_no_em_dash(visible)

    def test_no_malformed_section_label_rendered(self):
        self.assertNotIn("What to monitor:.", self.html)
        self.assertNotRegex(self.html, r"What to monitor:\.\s*</")

    def test_youtube_placeholder_only(self):
        note = self.delivery["youtube_note"]
        self.assertIn("Not active yet", note)
        self.assertIn("Video scripts will be added soon", note)
        self.assertIn("YouTube: Not active yet", self.html)
        self.assertNotIn("COPY THIS - YOUTUBE", self.html.upper())


class TestCopyDeskBeforeAfter(unittest.TestCase):
    BAD_LINKEDIN = (
        "Oman and Iran advance Strait of Hormuz transit fee plan despite US objections. "
        "Oman and Iran advance Strait of Hormuz transit fee plan despite US objections. "
        "What to monitor:."
    )
    BAD_THREAD = (
        "THREAD\n\n"
        "1/ Oman and Iran advance a Strait of Hormuz transit fee plan despite US objections.\n"
        "2/ If implemented, transit fees would reprice maritime insurance and Gulf shipping behavior even if fighting stays paused.\n"
        "3/ Operators with exposure across Oman, Iran, and US-linked Gulf routes face the first-order adjustment window.\n"
        "4/ Next readouts also rejected a French proposal to clear the Strait of Hormuz, keeping diplomatic and fee tracks separate.\n"
        "5/ Next indicators: official fee implementation language, transit behavior near Hormuz, and insurance notices from major underwriters. "
        "XIntelOps | Strategic signal brief"
    )

    def test_linkedin_before_after_quality(self):
        signal = _scan_2339()["ranked_signals"][0]
        sources = _scan_2339()["source_citations"]
        after = produce_final_linkedin(signal, sources).get("text", "")
        self.assertIn("What to monitor:.", self.BAD_LINKEDIN)
        self.assertNotIn("What to monitor:.", after)
        self.assertGreaterEqual(len(after), 700)
        self.assertIn("structural pricing", after.lower())

    def test_thread_before_after_quality(self):
        signal = _scan_2339()["ranked_signals"][0]
        sources = _scan_2339()["source_citations"]
        after = produce_final_x_thread(signal, sources).get("display", "")
        self.assertIn("XIntelOps | Strategic signal brief", self.BAD_THREAD)
        self.assertNotIn("XIntelOps | Strategic signal brief", after)
        self.assertIn("pricing chokepoint", after.lower())


class TestCrisisGuardrail(unittest.TestCase):
    def test_high_score_secondary_signal_does_not_trigger_crisis_for_hormuz(self):
        result = _scan_2339()
        tier = classify_scan_tier(result)
        self.assertEqual(tier["immediate_tier"], "LIVE_EVENT")
        self.assertFalse(tier["crisis_detected"])
        self.assertIn(tier["scan_max_tier"], {"FLASHPOINT", "CRISIS", "LIVE_EVENT", "PRIORITY"})


if __name__ == "__main__":
    unittest.main()
