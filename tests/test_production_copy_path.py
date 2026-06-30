"""Production-path copy tests via build_dual_x_copy and resolve_queue."""
from __future__ import annotations

import unittest

from xintelops.delivery.public_copy_gate import (
    _contains_global_banned,
    build_minimal_verified_single_tweet,
    prepare_public_copy,
)
from xintelops.delivery.queue import resolve_queue
from xintelops.delivery.x_dual_copy import build_dual_x_copy, build_single_from_facts, extract_signal_facts
from xintelops.delivery.x_copy import fit_tweet_length

US_IRAN_TITLE = "US and Iran agree to stand down after weekend exchange of strikes"

SOURCES = [
    {
        "name": "Reuters",
        "url": "https://reuters.com/us-iran-standdown",
        "why_supports": f"Primary source for: {US_IRAN_TITLE}",
    }
]

US_IRAN_SIGNAL = {
    "title": US_IRAN_TITLE,
    "url": "https://reuters.com/us-iran-standdown",
    "source": "Reuters",
    "region": "Gulf",
    "domain": "diplomacy",
    "actors": ["US", "Iran"],
    "why_hamza_should_care": "Weekend strikes near Hormuz raised transit and basing risk before Tuesday Doha talks.",
    "verified_facts": ["US and Iran agreed to stand down after weekend strikes near Hormuz."],
    "live_event_score": 9,
    "recommended_action": "X POST",
    "new_information_detected": True,
    "update_velocity": 8,
    "consequence_score": 8,
}


def _scan_fixture(
    scan_session: str,
    time_pkt: str,
    *,
    signal: dict | None = None,
    x_post: str = "",
    x_thread: list | None = None,
    **overrides,
) -> dict:
    sig = signal or US_IRAN_SIGNAL
    base = {
        "operator_decisions": {
            "one_signal_to_post": {"title": sig["title"], "action": "X POST", "why": "Selected signal."},
        },
        "ranked_signals": [sig],
        "top_signal": sig,
        "source_citations": SOURCES,
        "x_post": x_post,
        "x_thread": x_thread or [],
        "scan_session": scan_session,
        "date_pkt": "2026-06-30",
        "time_pkt": time_pkt,
        "signals_verified": 1,
    }
    base.update(overrides)
    return base


class TestBannedPhraseMatching(unittest.TestCase):
    def test_the_key_is_does_not_match_the_key_issue(self):
        self.assertIsNone(_contains_global_banned("The key issue is whether shipping risk eases."))

    def test_the_key_is_still_matches_literal_phrase(self):
        self.assertEqual(_contains_global_banned("Analysts say the key is timing the transit reopening."), "the key is")


class TestBuilderDoesNotPreFit(unittest.TestCase):
    def test_build_single_from_facts_does_not_pre_fit(self):
        long_imp = (
            "Another ceasefire reset after reciprocal strikes keeps Hormuz-adjacent escalation live, "
            "any breakdown re-prices energy and maritime insurance within hours, not days, "
            "and follow-on diplomacy in upcoming Qatar talks may reset transit pricing again."
        )
        sig = {
            **US_IRAN_SIGNAL,
            "title": "Qatar reports new transit insurance review after regional shipping disruption",
            "region": "Europe",
            "why_hamza_should_care": long_imp,
            "action_rationale": "",
        }
        title = sig["title"]
        result = _scan_fixture("SCAN-TEST-LONG", "09:05 PKT", signal=sig)
        result["operator_decisions"]["one_signal_to_post"]["title"] = title
        built = build_single_from_facts(extract_signal_facts(result, title))
        self.assertGreater(len(built), 260)
        self.assertFalse(built.rstrip(".").endswith(" in"))


class TestScan1204Regression(unittest.TestCase):
    """Operator action_rationale must not leak into public tweet copy."""

    def test_build_dual_x_copy_excludes_action_rationale(self):
        sig = {
            **US_IRAN_SIGNAL,
            "action_rationale": "Dominant headline already covered in prior scans within 12h",
        }
        result = _scan_fixture("SCAN-2026-06-30-1204", "12:04 PKT", signal=sig)
        dual = build_dual_x_copy(result, SOURCES, US_IRAN_TITLE, "X POST")
        self.assertTrue(dual["single"]["passed"])
        copy_lower = dual["single"]["text"].lower()
        self.assertNotIn("dominant headline", copy_lower)
        self.assertNotIn("prior scans within 12h", copy_lower)
        self.assertNotIn("worth tracking whether dominant", copy_lower)

    def test_resolve_queue_email_single_excludes_operator_rationale(self):
        sig = {
            **US_IRAN_SIGNAL,
            "action_rationale": "Dominant headline already covered in prior scans within 12h",
        }
        result = _scan_fixture("SCAN-2026-06-30-1204", "12:04 PKT", signal=sig)
        resolved = resolve_queue(result, None)
        single = resolved["operator_block"]["x"]["single_copy"]
        self.assertTrue(single)
        self.assertNotIn("dominant headline", single.lower())
        self.assertFalse(resolved["operator_block"]["x"]["copy_blocked"])


class TestScan0905Regression(unittest.TestCase):
    """Pre-gate fit must not produce dangling clause fragments like 'diplomacy in.'"""

    def test_long_built_candidate_passes_without_pre_truncation(self):
        long_imp = (
            "Another ceasefire reset after reciprocal strikes keeps Hormuz-adjacent escalation live, "
            "any breakdown re-prices energy and maritime insurance within hours, not days, "
            "and follow-on diplomacy in upcoming Qatar talks may reset transit pricing again."
        )
        sig = {**US_IRAN_SIGNAL, "why_hamza_should_care": long_imp, "action_rationale": ""}
        result = _scan_fixture("SCAN-2026-06-30-0905", "09:05 PKT", signal=sig)
        dual = build_dual_x_copy(result, SOURCES, US_IRAN_TITLE, "X POST")
        self.assertTrue(dual["single"]["passed"])
        text = dual["single"]["text"]
        self.assertNotRegex(text.lower(), r"diplomacy in\.?$")
        self.assertLessEqual(len(text), 280)

    def test_pre_truncated_builder_copy_is_blocked(self):
        long_imp = (
            "Another ceasefire reset after reciprocal strikes keeps Hormuz-adjacent escalation live, "
            "any breakdown re-prices energy and maritime insurance within hours, not days, "
            "and follow-on diplomacy in upcoming Qatar talks may reset transit pricing again."
        )
        event = f"{US_IRAN_TITLE}."
        bad_built = fit_tweet_length(f"{event} {long_imp}", 260)
        gate = prepare_public_copy(bad_built, "x", "single_tweet", sources=SOURCES, primary_title=US_IRAN_TITLE)
        self.assertFalse(gate["passed"])


class TestScan0606Regression(unittest.TestCase):
    def test_resolve_queue_produces_clean_single_copy(self):
        long_imp = (
            "Another ceasefire reset after reciprocal strikes keeps Hormuz-adjacent escalation live, "
            "any breakdown re-prices energy and maritime insurance within hours, not days, "
            "and follow-on diplomacy in upcoming Qatar talks may reset transit pricing again."
        )
        sig = {**US_IRAN_SIGNAL, "why_hamza_should_care": long_imp, "action_rationale": ""}
        result = _scan_fixture("SCAN-2026-06-30-0606", "06:06 PKT", signal=sig)
        resolved = resolve_queue(result, None)
        x = resolved["operator_block"]["x"]
        self.assertFalse(x["copy_blocked"])
        self.assertTrue(x["single_copy"])
        self.assertNotRegex(x["single_copy"].lower(), r"diplomacy in\.?$")
        self.assertEqual(resolved["x_post"], x["single_copy"])


class TestScan0305Regression(unittest.TestCase):
    """Minimal selected-signal fallback must not self-block on 'the key is' substring false positive."""

    def test_minimal_phrasing_passes_word_boundary_ban(self):
        phrase = "The key issue is whether shipping and basing risk ease before follow-on diplomacy."
        self.assertIsNone(_contains_global_banned(phrase))
        gate = prepare_public_copy(phrase, "x", "single_tweet", sources=SOURCES, primary_title=US_IRAN_TITLE)
        self.assertTrue(gate["passed"])

    def test_mandatory_fallback_passes_when_agent_copy_blocked(self):
        sig = {
            **US_IRAN_SIGNAL,
            "confidence": "LOW",
            "why_hamza_should_care": "Watch next: chokepoints under fire.",
        }
        toxic_agent = "If you're only counting sorties, you're late. Corridor risk matters more."
        result = _scan_fixture("SCAN-2026-06-30-0305", "03:05 PKT", signal=sig, x_post=toxic_agent)
        dual = build_dual_x_copy(result, SOURCES, US_IRAN_TITLE, "X POST")
        self.assertTrue(dual["single"]["passed"])
        self.assertNotIn("No clean single tweet from selected signal", dual["single"].get("block_reason", ""))

    def test_resolve_queue_clears_x_post_on_validation_failure(self):
        sig = {
            **US_IRAN_SIGNAL,
            "confidence": "LOW",
            "why_hamza_should_care": "Watch next: chokepoints under fire.",
        }
        toxic_agent = "If you're only counting sorties, you're late. Corridor risk matters more."
        result = _scan_fixture("SCAN-2026-06-30-0305", "03:05 PKT", signal=sig, x_post=toxic_agent)
        resolved = resolve_queue(result, None)
        self.assertTrue(resolved["operator_block"]["x"]["single_copy"])
        self.assertNotEqual(resolved["x_post"], toxic_agent)


class TestFailedFormatClearing(unittest.TestCase):
    def test_clears_x_post_and_x_thread_when_both_fail(self):
        sig = {
            **US_IRAN_SIGNAL,
            "title": "If you're only counting sorties, you're late.",
            "why_hamza_should_care": "Watch next: chokepoints under fire.",
        }
        title = sig["title"]
        result = _scan_fixture(
            "SCAN-TEST-CLEAR",
            "12:00 PKT",
            signal=sig,
            x_post="If you're only counting sorties, you're late. Corridor risk matters more.",
            x_thread=[
                "A Hormuz ceasefire was supposed to reopen shipping. Instead: drone hit → US strikes.",
                "The under-covered this isn't a bilateral US-Iran scrap.",
                "Watch next: (1) insurers re-price Hormuz transits, (2) Gulf statements follow.",
            ],
        )
        result["operator_decisions"]["one_signal_to_post"]["title"] = title
        result["operator_decisions"]["one_signal_to_post"]["action"] = "X THREAD"
        sig["recommended_action"] = "X THREAD"
        resolved = resolve_queue(result, None)
        self.assertTrue(resolved["operator_block"]["x"]["single_copy"])
        self.assertTrue(resolved["operator_block"]["x"]["thread_copy"])
        self.assertFalse(resolved["operator_block"]["x"]["copy_blocked"])


class TestMinimalFallbackSafe(unittest.TestCase):
    def test_build_minimal_verified_single_tweet_does_not_pre_fit(self):
        minimal = build_minimal_verified_single_tweet(US_IRAN_SIGNAL, SOURCES)
        self.assertTrue(minimal)
        gate = prepare_public_copy(minimal, "x", "single_tweet", sources=SOURCES, primary_title=US_IRAN_TITLE)
        self.assertTrue(gate["passed"])


if __name__ == "__main__":
    unittest.main()
