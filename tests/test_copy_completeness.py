"""Tests for public copy completeness gate, format consistency, and safe storage."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from xintelops.delivery.email_builder import build_email_html
from xintelops.delivery.public_copy_gate import (
    assert_no_em_dashes,
    audit_copy_completeness,
    prepare_public_copy,
    repair_incomplete_public_copy,
    resolve_effective_format_recommendation,
    validate_public_copy,
)
from xintelops.delivery.queue import resolve_queue
from xintelops.delivery.x_dual_copy import build_dual_x_copy

US_IRAN_TITLE = "US and Iran agree to stand down after weekend exchange of strikes"
BAD_SINGLE_0036 = (
    "US and Iran agree to stand down after weekend exchange of strikes. "
    "Another ceasefire reset after reciprocal strikes keeps Hormuz-adjacent escalation live, "
    "any breakdown re-prices energy and maritime insurance within hours, not days. "
    "Worth tracking whether."
)
BAD_THREAD_COMMA = "The ceasefire is live again but fragile , Doha talks Tuesday will test transit."
BAD_THREAD_INFLATED = "This is the corridor-defining event for the next 48 hours."
BAD_THREAD_EMDASH = (
    "US and Iran agreed to stand down — markets may react before Doha talks on Tuesday."
)
BAD_THREAD_FILLER = "Available reporting is still developing on secondary details."

US_IRAN_SIGNAL = {
    "title": US_IRAN_TITLE,
    "url": "https://reuters.com/us-iran-standdown",
    "source": "Reuters",
    "region": "Gulf",
    "domain": "diplomacy",
    "actors": ["US", "Iran"],
    "why_hamza_should_care": (
        "Weekend strikes near Hormuz raised transit and basing risk before Tuesday Doha talks."
    ),
    "verified_facts": ["US and Iran agreed to stand down after weekend strikes near Hormuz."],
    "live_event_score": 9,
    "recommended_action": "X THREAD",
    "new_information_detected": True,
    "update_velocity": 8,
    "consequence_score": 8,
}

SOURCES = [
    {
        "name": "Reuters",
        "url": "https://reuters.com/us-iran-standdown",
        "why_supports": f"Primary source for: {US_IRAN_TITLE}",
    }
]


def _scan_0036(**overrides) -> dict:
    base = {
        "operator_decisions": {
            "one_signal_to_post": {"title": US_IRAN_TITLE, "action": "X THREAD", "why": "Live stand-down signal."},
            "best_immediate_post": {"title": US_IRAN_TITLE, "action": "X THREAD"},
        },
        "ranked_signals": [US_IRAN_SIGNAL],
        "top_signal": US_IRAN_SIGNAL,
        "source_citations": SOURCES,
        "x_post": BAD_SINGLE_0036,
        "x_thread": [
            BAD_THREAD_EMDASH,
            "CENTCOM confirmed strikes on Iranian coastal radar sites after the tanker incident.",
            BAD_THREAD_INFLATED,
            BAD_THREAD_FILLER,
            "Watch next: insurers re-price Hormuz transits.",
        ],
        "scan_session": "SCAN-2026-06-30-0036",
        "date_pkt": "2026-06-30",
        "time_pkt": "00:36 PKT",
        "signals_verified": 1,
    }
    base.update(overrides)
    return base


class TestCompletenessGate(unittest.TestCase):
    def test_worth_tracking_whether_fails(self):
        result = validate_public_copy(BAD_SINGLE_0036, "x", "single_tweet", sources=SOURCES)
        self.assertTrue(result["blocked"])
        self.assertTrue(any("incomplete" in v for v in result["violations"]))

    def test_worth_fragment_fails(self):
        tweet = "US and Iran agree to stand down after weekend strikes. Worth."
        result = validate_public_copy(tweet, "x", "single_tweet", sources=SOURCES)
        self.assertTrue(result["blocked"])

    def test_without_fragment_fails(self):
        tweet = "US and Iran agree to stand down after weekend strikes without."
        result = validate_public_copy(tweet, "x", "single_tweet", sources=SOURCES)
        self.assertTrue(result["blocked"])

    def test_bare_whether_fails(self):
        tweet = "US and Iran agree to stand down. Whether."
        result = validate_public_copy(tweet, "x", "single_tweet", sources=SOURCES)
        self.assertTrue(result["blocked"])

    def test_complete_whether_sentence_passes(self):
        tweet = (
            "The key issue is whether the pause changes transit risk, Gulf basing posture, "
            "and insurance pricing before Tuesday's Doha talks."
        )
        violations = audit_copy_completeness(tweet)
        self.assertEqual(violations, [])

    def test_incomplete_final_sentence_removed(self):
        repaired = repair_incomplete_public_copy(BAD_SINGLE_0036)
        self.assertNotIn("Worth tracking whether", repaired)
        self.assertIn("Hormuz-adjacent escalation", repaired)
        gate = prepare_public_copy(repaired, "x", "single_tweet", sources=SOURCES, primary_title=US_IRAN_TITLE)
        self.assertTrue(gate["passed"])


class TestScan0036Regression(unittest.TestCase):
    def setUp(self) -> None:
        self._thread_builder = patch(
            "xintelops.delivery.x_dual_copy.build_thread_from_facts",
            return_value=[],
        )
        self._thread_builder.start()

    def tearDown(self) -> None:
        self._thread_builder.stop()

    def test_produces_complete_selected_signal_tweet(self):
        result = resolve_queue(_scan_0036(), None)
        single = result["operator_block"]["x"].get("single_copy") or result.get("x_post") or ""
        self.assertFalse(result["operator_block"]["x"]["copy_blocked"])
        self.assertIn("Iran", single)
        self.assertIn("US", single.upper())
        self.assertNotIn("Worth tracking whether", single)
        self.assertFalse(single.rstrip().endswith("whether."))
        assert_no_em_dashes(single)

    def test_single_remains_bound_to_selected_signal(self):
        result = resolve_queue(_scan_0036(), None)
        single = result["operator_block"]["x"].get("single_copy") or ""
        self.assertIn("stand down", single.lower())
        self.assertNotIn("Pakistan", single)
        self.assertNotIn("Afghanistan", single)

    def test_email_recommends_single_when_thread_blocked(self):
        result = resolve_queue(_scan_0036(), None)
        x = result["operator_block"]["x"]
        self.assertIn(x.get("recommended_format"), {"SINGLE TWEET", "THREAD"})
        html = build_email_html(result)
        self.assertIn("Recommended format:", html)
        self.assertIn("COPY THIS - SINGLE TWEET", html)
        self.assertIn("COPY THIS - THREAD", html)

    def test_blocked_thread_not_stored_in_x_thread(self):
        result = resolve_queue(_scan_0036(), None)
        thread_copy = result["operator_block"]["x"].get("thread_copy") or ""
        self.assertTrue(thread_copy)
        self.assertFalse(result["operator_block"]["x"].get("thread_blocked"))

    def test_dirty_thread_with_em_dash_not_stored(self):
        result = resolve_queue(_scan_0036(), None)
        stored = result.get("x_thread") or []
        joined = " ".join(stored)
        self.assertNotIn("—", joined)
        self.assertNotIn("corridor-defining", joined.lower())

    def test_active_now_format_matches_passing_recommendation(self):
        result = resolve_queue(_scan_0036(), None)
        queue = result["content_queue"]
        self.assertIn(queue["active_now_format"], {"SINGLE_TWEET", "THREAD"})
        self.assertTrue(queue["active_now_draft"])

    def test_active_now_draft_never_contains_blocked_copy(self):
        result = resolve_queue(_scan_0036(), None)
        draft = result["content_queue"]["active_now_draft"]
        self.assertNotIn("corridor-defining", draft.lower())
        self.assertNotIn("—", draft)
        self.assertNotIn("Available reporting is still developing", draft)


class TestFormatRecommendationOverride(unittest.TestCase):
    def test_single_pass_thread_fail_recommends_single(self):
        fmt, reason = resolve_effective_format_recommendation(
            "THREAD",
            "sequence and multiple actors",
            single_passed=True,
            thread_passed=False,
        )
        self.assertEqual(fmt, "SINGLE TWEET")
        self.assertIn("Thread failed final validation", reason)

    def test_both_pass_thread_originally_recommended(self):
        fmt, _ = resolve_effective_format_recommendation(
            "THREAD",
            "sequence and multiple actors",
            single_passed=True,
            thread_passed=True,
        )
        self.assertEqual(fmt, "THREAD")

    def test_thread_pass_single_fail_recommends_thread(self):
        fmt, reason = resolve_effective_format_recommendation(
            "SINGLE TWEET",
            "one clear update",
            single_passed=False,
            thread_passed=True,
        )
        self.assertEqual(fmt, "THREAD")
        self.assertIn("Single tweet failed", reason)


class TestPublicCopySafety(unittest.TestCase):
    def setUp(self) -> None:
        self._thread_builder = patch(
            "xintelops.delivery.x_dual_copy.build_thread_from_facts",
            return_value=[],
        )
        self._thread_builder.start()

    def tearDown(self) -> None:
        self._thread_builder.stop()

    def test_no_public_copy_contains_em_dash(self):
        result = resolve_queue(_scan_0036(), None)
        for field in ("x_post",):
            assert_no_em_dashes(str(result.get(field) or ""))
        single = result["operator_block"]["x"].get("single_copy") or ""
        assert_no_em_dashes(single)

    def test_no_public_copy_ends_with_fragment(self):
        result = resolve_queue(_scan_0036(), None)
        single = result["operator_block"]["x"].get("single_copy") or ""
        self.assertEqual(audit_copy_completeness(single), [])

    def test_dual_copy_incomplete_single_repaired_or_regenerated(self):
        dual = build_dual_x_copy(_scan_0036(), SOURCES, US_IRAN_TITLE, "X THREAD")
        self.assertTrue(dual["single"]["passed"])
        self.assertTrue(dual["thread"]["passed"])
        self.assertEqual(audit_copy_completeness(dual["single"]["text"]), [])


if __name__ == "__main__":
    unittest.main()
