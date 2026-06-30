"""Tests for editorial quality gate and SCAN-2026-06-30-0058 regression."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from xintelops.delivery.email_builder import build_email_html
from xintelops.delivery.public_copy_gate import (
    assert_no_em_dashes,
    audit_editorial_quality,
    build_minimal_verified_single_tweet,
    format_operator_block_reason,
    prepare_public_copy,
    sanitize_visible_text,
    validate_editorial_quality,
    validate_public_copy,
)
from xintelops.delivery.queue import resolve_queue
from xintelops.delivery.x_dual_copy import build_dual_x_copy

US_IRAN_TITLE = "US and Iran agree to stand down after weekend exchange of strikes"
BAD_SINGLE_0058 = (
    "US and Iran agree to stand down after weekend exchange of strikes. "
    "The ceasefire is live again but fragile, another violation cycle directly affects "
    "Hormuz shipping risk, Gulf basing, and whether Doha talks produce anything durable before markets reopen."
)
CLEAN_SINGLE = (
    "US and Iran say they will stand down after weekend strikes. "
    "The issue now is whether the pause lowers Hormuz shipping risk, Gulf basing pressure, "
    "and insurance pricing before the next round of Doha talks."
)

US_IRAN_SIGNAL = {
    "title": US_IRAN_TITLE,
    "url": "https://reuters.com/us-iran-standdown",
    "source": "Reuters",
    "region": "Gulf",
    "why_hamza_should_care": "Weekend strikes near Hormuz raised transit and basing risk before Tuesday Doha talks.",
    "verified_facts": ["US and Iran agreed to stand down after weekend strikes near Hormuz."],
    "live_event_score": 9,
    "recommended_action": "X THREAD",
    "new_information_detected": True,
    "update_velocity": 8,
}

PAKISTAN_SIGNAL = {
    "title": "Pakistani cross-border strikes kill at least 28 civilians in Afghanistan, UN reports",
    "url": "https://reuters.com/pakistan-afghanistan",
    "region": "South Asia",
    "why_hamza_should_care": "Cross-border strikes on the Durand Line with major civilian casualties.",
    "new_information_detected": True,
}

SOURCES = [{"name": "Reuters", "url": "https://reuters.com/us-iran-standdown", "why_supports": f"Primary source for: {US_IRAN_TITLE}"}]


def _scan_0058(**overrides) -> dict:
    base = {
        "operator_decisions": {
            "one_signal_to_post": {"title": US_IRAN_TITLE, "action": "X THREAD", "why": "Live stand-down signal."},
            "best_immediate_post": {"title": US_IRAN_TITLE, "action": "X THREAD"},
        },
        "ranked_signals": [US_IRAN_SIGNAL, PAKISTAN_SIGNAL],
        "top_signal": US_IRAN_SIGNAL,
        "source_citations": SOURCES,
        "x_post": BAD_SINGLE_0058,
        "x_thread": [
            "UN reports Pakistani cross-border strikes killed civilians in Afghanistan near the Durand Line.",
            "CENTCOM confirmed strikes on Iranian coastal radar sites after the tanker incident.",
            "This is the corridor-defining event for the next 48 hours.",
            "Available reporting is still developing on secondary details.",
            "Watch next: insurers re-price Hormuz transits.",
        ],
        "scan_session": "SCAN-2026-06-30-0058",
        "date_pkt": "2026-06-30",
        "time_pkt": "00:58 PKT",
        "signals_verified": 2,
    }
    base.update(overrides)
    return base


class TestEditorialQualityGate(unittest.TestCase):
    def test_comma_splice_fails(self):
        result = validate_public_copy(BAD_SINGLE_0058, "x", "single_tweet", sources=SOURCES)
        self.assertTrue(result["blocked"])
        self.assertTrue(any("comma splice" in v or "weak phrase" in v for v in result["violations"]))

    def test_live_again_but_fragile_fails(self):
        tweet = "The ceasefire is live again but fragile, another violation cycle follows."
        violations = audit_editorial_quality(tweet)
        self.assertTrue(any("live again but fragile" in v for v in violations))

    def test_violation_cycle_fails(self):
        tweet = "Another violation cycle directly affects Hormuz shipping risk."
        violations = audit_editorial_quality(tweet)
        self.assertTrue(any("violation cycle" in v for v in violations))

    def test_produce_anything_durable_fails(self):
        tweet = "Whether Doha talks produce anything durable before markets reopen."
        violations = audit_editorial_quality(tweet)
        self.assertTrue(any("produce anything durable" in v or "before markets reopen" in v for v in violations))

    def test_manual_rewrite_quality_fails(self):
        result = validate_editorial_quality(BAD_SINGLE_0058, "x", "single_tweet")
        self.assertFalse(result["passed"])

    def test_clean_replacement_passes(self):
        result = validate_public_copy(CLEAN_SINGLE, "x", "single_tweet", sources=SOURCES)
        self.assertTrue(result["passed"])
        assert_no_em_dashes(result["text"])
        self.assertEqual(audit_editorial_quality(result["text"]), [])

    def test_minimal_fallback_is_post_ready(self):
        tweet = build_minimal_verified_single_tweet(US_IRAN_SIGNAL, SOURCES)
        gate = prepare_public_copy(tweet, "x", "single_tweet", sources=SOURCES, primary_title=US_IRAN_TITLE)
        self.assertTrue(gate["passed"])
        self.assertIn("Hormuz", gate["text"])
        self.assertIn("Doha talks", gate["text"])


class TestScan0058Regression(unittest.TestCase):
    def setUp(self) -> None:
        self._thread_builder = patch(
            "xintelops.delivery.x_dual_copy.build_thread_from_facts",
            return_value=[],
        )
        self._thread_builder.start()

    def tearDown(self) -> None:
        self._thread_builder.stop()

    def test_bad_agent_tweet_replaced_with_clean_fallback(self):
        result = resolve_queue(_scan_0058(), None)
        single = result["operator_block"]["x"].get("single_copy") or ""
        self.assertFalse(result["operator_block"]["x"]["copy_blocked"])
        self.assertNotIn("live again but fragile", single.lower())
        self.assertNotIn("violation cycle", single.lower())
        self.assertNotIn("produce anything durable", single.lower())
        self.assertNotIn("before markets reopen", single.lower())
        self.assertIn("The issue now is whether", single)

    def test_recommends_single_when_thread_blocked(self):
        result = resolve_queue(_scan_0058(), None)
        x = result["operator_block"]["x"]
        self.assertEqual(x.get("recommended_format"), "SINGLE TWEET")
        html = build_email_html(result)
        self.assertIn("SINGLE TWEET", html)
        self.assertNotIn("Recommended format:</span> THREAD", html.replace("SINGLE TWEET", ""))

    def test_email_visible_text_has_no_em_dash(self):
        scan = _scan_0058(
            operator_decisions={
                "one_signal_to_post": {
                    "title": US_IRAN_TITLE,
                    "action": "X THREAD",
                    "why": "Weekend stand-down — Hormuz risk remains elevated.",
                },
            }
        )
        result = resolve_queue(scan, None)
        html = build_email_html(result)
        self.assertNotIn("—", html)
        self.assertNotIn("–", html)

    def test_thread_block_reason_is_operator_readable(self):
        dual = build_dual_x_copy(_scan_0058(), SOURCES, US_IRAN_TITLE, "X THREAD")
        reason = dual["thread"].get("block_reason") or ""
        self.assertNotIn("(un)", reason.lower())
        self.assertIn("Thread blocked because", reason)

    def test_broken_un_fragment_not_rendered(self):
        reason = format_operator_block_reason("copy matches different signal topic")
        self.assertNotIn("(un)", reason.lower())
        self.assertIn("different signal topic", reason.lower())

    def test_copy_this_is_post_ready(self):
        result = resolve_queue(_scan_0058(), None)
        single = result["operator_block"]["x"].get("single_copy") or ""
        gate = prepare_public_copy(single, "x", "single_tweet", sources=SOURCES, primary_title=US_IRAN_TITLE)
        self.assertTrue(gate["passed"])
        self.assertEqual(audit_editorial_quality(gate["text"]), [])

    def test_no_public_copy_bypasses_gates(self):
        dual = build_dual_x_copy(_scan_0058(), SOURCES, US_IRAN_TITLE, "X THREAD")
        if dual["single"]["passed"]:
            gate = validate_public_copy(
                dual["single"]["text"],
                "x",
                "single_tweet",
                sources=SOURCES,
                primary_title=US_IRAN_TITLE,
            )
            self.assertTrue(gate["passed"])


class TestVisibleTextSanitization(unittest.TestCase):
    def test_sanitize_visible_text_removes_em_dash(self):
        out = sanitize_visible_text("Why this won — Hormuz risk remains elevated.")
        self.assertNotIn("—", out)
        assert_no_em_dashes(out)


if __name__ == "__main__":
    unittest.main()
