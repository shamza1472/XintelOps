"""Tests for binding X copy to the selected active_now signal."""
from __future__ import annotations

import unittest

from xintelops.delivery.email_builder import build_email_html
from xintelops.delivery.public_copy_gate import (
    assert_no_em_dashes,
    build_minimal_verified_single_tweet,
    extract_binding_anchors,
    format_operator_block_reason,
    prepare_public_copy,
    validate_copy_signal_binding,
    validate_public_copy,
)
from xintelops.delivery.queue import resolve_queue
from xintelops.delivery.x_dual_copy import build_dual_x_copy, _format_block_reason

US_IRAN_TITLE = (
    "US and Iran agree to stand down after weekend exchange of strikes; "
    "Kushner and Witkoff to lead Doha talks"
)
PAKISTAN_TWEET = (
    "Pakistani cross-border strikes kill at least 28 civilians in Afghanistan, UN reports. "
    "A separate live escalation on the Durand Line while global attention sits on Iran , "
    "Islamabad is testing cross-border strike doctrine with major humanitarian blowback. Worth."
)
BAD_THREAD_COMMA = "The ceasefire is live again but fragile , Doha talks Tuesday will test transit."
BAD_THREAD_INFLATED = "This is the corridor-defining event for the next 48 hours."
BAD_THREAD_FILLER = "Available reporting is still developing on secondary details."

US_IRAN_SIGNAL = {
    "title": US_IRAN_TITLE,
    "url": "https://reuters.com/us-iran-standdown",
    "source": "Reuters",
    "region": "Gulf",
    "domain": "diplomacy",
    "actors": ["US", "Iran", "Kushner", "Witkoff"],
    "why_hamza_should_care": "Weekend strikes near Hormuz raised transit and basing risk before Tuesday Doha talks.",
    "verified_facts": ["US and Iran agreed to stand down after weekend strikes near Hormuz."],
    "live_event_score": 9,
    "recommended_action": "X THREAD",
    "new_information_detected": True,
}

PAKISTAN_SIGNAL = {
    "title": "Pakistani cross-border strikes kill at least 28 civilians in Afghanistan, UN reports",
    "url": "https://reuters.com/pakistan-afghanistan",
    "source": "Reuters",
    "region": "South Asia",
    "why_hamza_should_care": "Cross-border strikes on the Durand Line with major civilian casualties.",
    "verified_facts": ["UN reports at least 28 civilian deaths from Pakistani cross-border strikes."],
    "new_information_detected": True,
}

SOURCES = [{"name": "Reuters", "url": "https://reuters.com/us-iran-standdown", "why_supports": f"Primary source for: {US_IRAN_TITLE}"}]


def _scan_2337(**overrides) -> dict:
    base = {
        "operator_decisions": {
            "one_signal_to_post": {"title": US_IRAN_TITLE, "action": "X THREAD", "why": "Live stand-down signal."},
            "best_immediate_post": {"title": US_IRAN_TITLE, "action": "X THREAD"},
        },
        "ranked_signals": [US_IRAN_SIGNAL, PAKISTAN_SIGNAL],
        "top_signal": US_IRAN_SIGNAL,
        "source_citations": SOURCES,
        "x_post": PAKISTAN_TWEET,
        "x_thread": [
            BAD_THREAD_COMMA,
            "CENTCOM confirmed strikes on Iranian coastal radar sites after the tanker incident.",
            BAD_THREAD_INFLATED,
            BAD_THREAD_FILLER,
            "Watch next: insurers re-price Hormuz transits.",
        ],
        "scan_session": "SCAN-2026-06-29-2337",
        "date_pkt": "2026-06-29",
        "time_pkt": "23:37 PKT",
        "signals_verified": 2,
    }
    base.update(overrides)
    return base


class TestBindingValidator(unittest.TestCase):
    def test_pakistan_tweet_fails_for_us_iran_selected(self):
        result = validate_copy_signal_binding(PAKISTAN_TWEET, US_IRAN_SIGNAL, SOURCES, other_signals=[PAKISTAN_SIGNAL])
        self.assertFalse(result["passed"])
        self.assertIn("Pakistan", result["block_reason"])

    def test_us_iran_minimal_passes_binding(self):
        tweet = build_minimal_verified_single_tweet(US_IRAN_SIGNAL, SOURCES)
        result = validate_copy_signal_binding(tweet, US_IRAN_SIGNAL, SOURCES, other_signals=[PAKISTAN_SIGNAL])
        self.assertTrue(result["passed"])

    def test_fallback_must_be_declared(self):
        tweet = build_minimal_verified_single_tweet(PAKISTAN_SIGNAL, SOURCES)
        result = validate_copy_signal_binding(
            tweet,
            US_IRAN_SIGNAL,
            SOURCES,
            allowed_fallback_signal=PAKISTAN_SIGNAL,
            other_signals=[PAKISTAN_SIGNAL],
        )
        self.assertTrue(result["passed"])

    def test_silent_fallback_to_other_signal_fails(self):
        tweet = build_minimal_verified_single_tweet(PAKISTAN_SIGNAL, SOURCES)
        result = validate_copy_signal_binding(
            tweet,
            US_IRAN_SIGNAL,
            SOURCES,
            other_signals=[PAKISTAN_SIGNAL],
        )
        self.assertFalse(result["passed"])


class TestBlockReasonLabels(unittest.TestCase):
    def test_thread_block_reason_uses_selected_signal_actors(self):
        oman_signal = {
            "title": "Oman and Iran advance Strait of Hormuz transit fee plan despite US objections",
            "actors": ["Oman", "Iran", "US"],
            "region": "Gulf",
        }
        reason = format_operator_block_reason(
            "copy describes Pakistan/Afghanistan but selected signal is Oman/Iran",
            selected_signal=oman_signal,
        )
        self.assertIn("Oman/Iran", reason)
        self.assertNotIn("US/Iran", reason)

    def test_dual_copy_thread_block_reason_uses_selected_actors(self):
        oman_signal = {
            "title": "Oman and Iran advance Strait of Hormuz transit fee plan despite US objections",
            "actors": ["Oman", "Iran", "US"],
            "region": "Gulf",
        }
        reason = _format_block_reason(
            "Thread",
            "copy describes Pakistan/Afghanistan but selected signal is Oman/Iran",
            selected_signal=oman_signal,
        )
        self.assertIn("Oman/Iran", reason)
        self.assertNotIn("US/Iran", reason)


class TestScan2337Regression(unittest.TestCase):
    def test_x_post_is_us_iran_not_pakistan(self):
        result = resolve_queue(_scan_2337(), None)
        single = result["operator_block"]["x"].get("single_copy") or ""
        self.assertFalse(result["operator_block"]["x"]["copy_blocked"])
        self.assertIn("Iran", single)
        self.assertNotIn("Pakistan", single)
        self.assertNotIn("Afghanistan", single)
        self.assertNotIn("Durand", single)

    def test_bound_signal_title_matches_active_now(self):
        result = resolve_queue(_scan_2337(), None)
        x = result["operator_block"]["x"]
        self.assertEqual(x.get("bound_signal_title"), US_IRAN_TITLE)
        self.assertEqual(x.get("post_now"), US_IRAN_TITLE)

    def test_email_shows_us_iran_single_tweet(self):
        result = resolve_queue(_scan_2337(), None)
        html = build_email_html(result)
        self.assertIn("COPY THIS - SINGLE TWEET", html)
        self.assertIn("Iran", html)
        self.assertNotIn("Pakistan", html)

    def test_agent_pakistan_x_post_rejected(self):
        dual = build_dual_x_copy(_scan_2337(), SOURCES, US_IRAN_TITLE, "X THREAD")
        single = dual["single"]["text"]
        self.assertTrue(dual["single"]["passed"])
        self.assertNotIn("Pakistan", single)


class TestThreadQuality(unittest.TestCase):
    def test_thread_fails_comma_spacing(self):
        result = validate_public_copy(BAD_THREAD_COMMA, "x", "thread")
        self.assertTrue(result["blocked"])

    def test_thread_fails_corridor_defining(self):
        result = validate_public_copy(BAD_THREAD_INFLATED, "x", "thread")
        self.assertTrue(result["blocked"])

    def test_thread_fails_generic_filler(self):
        result = validate_public_copy(BAD_THREAD_FILLER, "x", "thread")
        self.assertTrue(result["blocked"])

    def test_thread_actors_match_selected_signal(self):
        result = resolve_queue(_scan_2337(), None)
        thread = result["operator_block"]["x"].get("thread_copy") or ""
        if thread:
            self.assertNotIn("corridor-defining", thread.lower())
            self.assertNotIn("Available reporting is still developing", thread)


class TestActorBinding(unittest.TestCase):
    def test_x_post_actors_match_active_now_signal(self):
        anchors = extract_binding_anchors(US_IRAN_SIGNAL)
        result = resolve_queue(_scan_2337(), None)
        single = result["operator_block"]["x"].get("single_copy") or ""
        hits = {t for t in anchors["tokens"] if t in single.lower()}
        self.assertGreaterEqual(len(hits), 2)

    def test_x_thread_bound_to_selected_signal_when_passes(self):
        clean_thread = [
            "US and Iran agreed to stand down after weekend strikes near Hormuz.",
            "Kushner and Witkoff are expected to lead Doha talks on Tuesday.",
            "The ceasefire remains fragile. Doha talks will test whether transit behavior changes near Hormuz.",
            "Some details remain unclear, including how Tehran frames the stand-down.",
            "The next indicators are Gulf statements and transit recovery data.",
        ]
        scan = _scan_2337(x_thread=clean_thread)
        dual = build_dual_x_copy(scan, SOURCES, US_IRAN_TITLE, "X THREAD")
        if dual["thread"]["passed"]:
            self.assertIn("Iran", dual["thread"]["display"])


class TestGlobalGateStillApplied(unittest.TestCase):
    def test_no_em_dash_in_bound_output(self):
        result = resolve_queue(_scan_2337(), None)
        single = result["operator_block"]["x"].get("single_copy") or ""
        assert_no_em_dashes(single)

    def test_slop_blocked_before_binding(self):
        gate = prepare_public_copy("If you're only counting sorties, you're late.", "x", "single_tweet")
        self.assertTrue(gate["blocked"])


if __name__ == "__main__":
    unittest.main()
