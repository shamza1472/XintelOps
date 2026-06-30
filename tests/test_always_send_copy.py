"""Production-path tests for always-send copy delivery behavior."""
from __future__ import annotations

import re
import unittest

from xintelops.delivery.email_builder import build_email_html
from xintelops.delivery.final_copy import produce_final_x_thread, produce_final_x_tweet
from xintelops.delivery.public_copy_gate import prepare_public_copy
from xintelops.delivery.queue import resolve_queue
from xintelops.delivery.x_dual_copy import build_dual_x_copy

OMAN_TITLE = "Oman and Iran advance Strait of Hormuz transit fee plan despite US objections"

SOURCES = [
    {
        "name": "Reuters",
        "url": "https://reuters.com/hormuz-fee",
        "why_supports": f"Primary source for: {OMAN_TITLE}",
    }
]

OMAN_SIGNAL = {
    "title": OMAN_TITLE,
    "url": "https://reuters.com/hormuz-fee",
    "source": "Reuters",
    "region": "Gulf",
    "domain": "maritime",
    "actors": ["Oman", "Iran", "US"],
    "why_hamza_should_care": (
        "A fee mechanism at Hormuz would reprice maritime insurance and Gulf transit behavior "
        "even if fighting stays paused."
    ),
    "verified_facts": [
        "Oman has proposed a Strait of Hormuz fee plan to the United States.",
        "Iran and Oman are moving forward with transit payment collection despite US objections.",
    ],
    "live_event_score": 8,
    "recommended_action": "X POST",
    "new_information_detected": True,
    "update_velocity": 6,
    "consequence_score": 8,
}

LEVERAGE_THREAD = [
    "Oman and Iran advance a Strait of Hormuz transit fee plan despite US objections.",
    "Washington may leverage Gulf basing access to push back on the fee mechanism.",
    "Operators with exposure across Oman, Iran, US face the first-order adjustment window.",
    "Next indicators: Iran and Oman are moving forward with transit payment collection despite US objections.",
    "XIntelOps read: A fee mechanism at Hormuz would reprice maritime insurance and Gulf transit behavior.",
]


def _scan_2256(*, day_of_week: str = "Monday", **overrides) -> dict:
    base = {
        "operator_decisions": {
            "one_signal_to_post": {"title": OMAN_TITLE, "action": "X POST", "why": "Selected signal."},
        },
        "ranked_signals": [OMAN_SIGNAL],
        "top_signal": OMAN_SIGNAL,
        "source_citations": SOURCES,
        "x_post": (
            "Oman and Iran advance a Strait of Hormuz transit fee plan despite US objections. "
            "If implemented, the Strait shifts from a military chokepoint into a pricing chokepoint."
        ),
        "x_thread": LEVERAGE_THREAD,
        "scan_session": "SCAN-2026-06-30-2256",
        "date_pkt": "2026-06-30",
        "time_pkt": "22:56 PKT",
        "day_of_week": day_of_week,
        "signals_verified": 1,
        "runtime": {"runtime_label": "ace371a"},
    }
    base.update(overrides)
    return base


def _assert_no_em_dash(text: str) -> None:
    assert "—" not in text and "–" not in text, f"em dash found in: {text[:120]}"


class TestAlwaysSendCopy(unittest.TestCase):
    def test_banned_word_in_thread_triggers_repair_not_email_block(self):
        result = resolve_queue(_scan_2256(), None)
        html = build_email_html(result)
        x = result["operator_block"]["x"]
        self.assertFalse(x["copy_blocked"])
        self.assertNotIn("THREAD BLOCKED", html)
        self.assertNotIn("banned phrase", html.lower())
        self.assertIn("COPY THIS - THREAD", html)

    def test_email_includes_single_tweet_and_thread(self):
        result = resolve_queue(_scan_2256(), None)
        html = build_email_html(result)
        self.assertIn("COPY THIS - SINGLE TWEET", html)
        self.assertIn("COPY THIS - THREAD", html)
        self.assertTrue(result["operator_block"]["x"]["single_copy"])
        self.assertTrue(result["operator_block"]["x"]["thread_copy"])

    def test_email_includes_linkedin_copy_daily(self):
        result = resolve_queue(_scan_2256(day_of_week="Tuesday"), None)
        html = build_email_html(result)
        self.assertIn("COPY THIS - LINKEDIN", html)
        self.assertTrue(result["operator_block"]["linkedin"]["copy_this"])

    def test_email_includes_substack_copy_daily(self):
        result = resolve_queue(_scan_2256(), None)
        html = build_email_html(result)
        self.assertIn("COPY THIS - SUBSTACK", html)
        self.assertTrue(result["operator_block"]["delivery"]["substack_copy"])

    def test_linkedin_cadence_changes_label_not_copy_generation(self):
        li_day = resolve_queue(_scan_2256(day_of_week="Monday"), None)
        non_li_day = resolve_queue(_scan_2256(day_of_week="Tuesday"), None)
        self.assertTrue(li_day["operator_block"]["linkedin"]["copy_this"])
        self.assertTrue(non_li_day["operator_block"]["linkedin"]["copy_this"])
        self.assertIn("suggested LinkedIn posting day", li_day["operator_block"]["delivery"]["linkedin_cadence_note"])
        self.assertIn("Not a scheduled LinkedIn posting day", non_li_day["operator_block"]["delivery"]["linkedin_cadence_note"])

    def test_youtube_placeholder_no_script(self):
        result = resolve_queue(_scan_2256(), None)
        html = build_email_html(result)
        note = result["operator_block"]["delivery"]["youtube_note"]
        self.assertIn("Not active yet", note)
        self.assertIn("Video scripts will be added soon", note)
        self.assertIn("YouTube: Not active yet", html)
        self.assertNotIn("COPY THIS - YOUTUBE", html.upper())

    def test_scan_2256_does_not_render_thread_blocked(self):
        html = build_email_html(resolve_queue(_scan_2256(), None))
        self.assertNotIn("THREAD BLOCKED", html)
        self.assertNotIn("FINAL COPY QUALITY FAIL", html)

    def test_scan_2256_produces_clean_thread(self):
        result = resolve_queue(_scan_2256(), None)
        thread = result["operator_block"]["x"]["thread_copy"]
        self.assertIn("COPY THIS - THREAD", build_email_html(result))
        self.assertNotRegex(thread.lower(), r"\bleverage\b")
        self.assertGreaterEqual(len(re.findall(r"\d+/", thread)), 4)

    def test_scan_2256_produces_business_consequence_tweet(self):
        tweet = resolve_queue(_scan_2256(), None)["operator_block"]["x"]["single_copy"]
        self.assertNotIn("The issue now is whether", tweet)
        self.assertTrue(
            any(
                phrase in tweet.lower()
                for phrase in ("pricing chokepoint", "shipping", "insurance", "fee mechanism", "repric")
            )
        )

    def test_no_visible_email_text_contains_em_dash(self):
        html = build_email_html(resolve_queue(_scan_2256(), None))
        _assert_no_em_dash(html)

    def test_no_email_exposes_banned_word_failure_reasons(self):
        html = build_email_html(resolve_queue(_scan_2256(), None)).lower()
        self.assertNotIn("banned phrase", html)
        self.assertNotIn("banned word", html)
        self.assertNotIn("leverage", html)

    def test_suggested_format_section_appears(self):
        result = resolve_queue(_scan_2256(), None)
        html = build_email_html(result)
        delivery = result["operator_block"]["delivery"]
        self.assertIn("Suggested format:", html)
        self.assertTrue(delivery.get("suggested_format"))
        self.assertTrue(delivery.get("suggested_format_reason"))

    def test_copy_formats_are_advisory_not_auto_post(self):
        result = resolve_queue(_scan_2256(), None)
        html = build_email_html(result)
        self.assertIn("Suggested format:", html)
        self.assertIn("COPY THIS - SINGLE TWEET", html)
        self.assertIn("COPY THIS - THREAD", html)
        self.assertNotIn("AUTO POST", html.upper())

    def test_thread_regeneration_removes_banned_terms(self):
        thread = produce_final_x_thread(OMAN_SIGNAL, SOURCES, agent_thread=LEVERAGE_THREAD)
        combined = thread.get("display") or thread.get("text") or ""
        self.assertNotRegex(combined.lower(), r"\bleverage\b")

    def test_substack_copy_passes_anti_slop_gate(self):
        result = resolve_queue(_scan_2256(), None)
        substack = result["operator_block"]["delivery"]["substack_copy"]
        gate = prepare_public_copy(substack, "substack", "substack_post", sources=SOURCES, primary_title=OMAN_TITLE)
        self.assertTrue(gate["passed"] or len(substack.split()) >= 80)
        self.assertEqual(substack.lower().count("additional reporting may clarify"), 0)

    def test_linkedin_copy_passes_anti_slop_gate(self):
        result = resolve_queue(_scan_2256(), None)
        linkedin = result["operator_block"]["linkedin"]["copy_this"]
        gate = prepare_public_copy(linkedin, "linkedin", "linkedin_post", sources=SOURCES, primary_title=OMAN_TITLE)
        self.assertTrue(gate["passed"])
        self.assertGreaterEqual(len(linkedin), 700)
        self.assertLessEqual(len(linkedin), 1200)


class TestDualCopyAlwaysPassesWhenVerified(unittest.TestCase):
    def test_build_dual_x_copy_always_passes_with_verified_signal(self):
        dual = build_dual_x_copy(_scan_2256(), SOURCES, OMAN_TITLE, "X POST")
        self.assertTrue(dual["has_verified_signals"])
        self.assertTrue(dual["single"]["passed"])
        self.assertTrue(dual["thread"]["passed"])
        self.assertTrue(dual["delivery"]["single_copy"])
        self.assertTrue(dual["delivery"]["thread_copy"])


if __name__ == "__main__":
    unittest.main()
