"""Tests for dual-format X copy (single tweet + thread)."""
from __future__ import annotations

import unittest

from xintelops.delivery.email_builder import build_email_html
from xintelops.delivery.queue import resolve_queue
from xintelops.delivery.x_dual_copy import (
    build_dual_x_copy,
    build_single_from_facts,
    build_thread_from_facts,
    extract_signal_facts,
    recommend_x_format,
)


def _signal(**kwargs) -> dict:
    base = {
        "title": "Iran says frozen assets may move from Qatar",
        "source": "Reuters",
        "url": "https://reuters.com/iran-assets",
        "region": "Gulf",
        "domain": "sanctions",
        "why_hamza_should_care": "Iran says $6B in frozen assets will be released from Qatar. US officials dispute the transfer.",
        "recommended_action": "X POST",
        "confidence": "MEDIUM",
        "live_event_score": 5,
        "consequence_score": 6,
        "update_velocity": 4,
        "rank_score": 70,
    }
    base.update(kwargs)
    return base


def _sequence_signal(**kwargs) -> dict:
    base = {
        "title": "US-Iran Hormuz strike sequence widens",
        "why_hamza_should_care": "A cargo ship was hit near Hormuz, CENTCOM struck Iranian coastal sites, and Iran retaliated in Kuwait and Bahrain.",
        "recommended_action": "X THREAD",
        "live_event_score": 9,
        "update_velocity": 8,
        "consequence_score": 9,
        "verified_facts": [
            "A commercial cargo ship was hit in the Strait of Hormuz.",
            "CENTCOM confirmed strikes on Iranian coastal radar sites.",
        ],
    }
    base.update(kwargs)
    return _signal(**base)


def _base_result(*, signal: dict | None = None, x_thread=None, x_post: str = "", **kwargs) -> dict:
    sig = signal or _signal()
    return {
        "operator_decisions": {
            "one_signal_to_post": {
                "title": sig["title"],
                "action": sig.get("recommended_action", "X POST"),
                "why": "Selected signal.",
            },
        },
        "ranked_signals": [sig],
        "source_citations": [{"name": "Reuters", "url": "https://reuters.com/x"}],
        "top_signal": {
            "title": sig["title"],
            "summary": sig.get("why_hamza_should_care"),
            "region": sig.get("region"),
            "verified_facts": sig.get("verified_facts") or [],
        },
        "x_thread": x_thread or [],
        "x_post": x_post,
        "scan_session": "SCAN-TEST-DUAL",
        "date_pkt": "2026-06-29",
        "time_pkt": "21:06 PKT",
        **kwargs,
    }


class TestFormatRecommendation(unittest.TestCase):
    def test_recommends_single_for_simple_update(self):
        facts = extract_signal_facts(_base_result(), _signal()["title"])
        fmt, reason = recommend_x_format(_signal(), facts, "X POST")
        self.assertEqual(fmt, "SINGLE TWEET")
        self.assertIn("one clear update", reason.lower())

    def test_recommends_thread_for_multi_actor_sequence(self):
        sig = _sequence_signal()
        facts = extract_signal_facts(_base_result(signal=sig), sig["title"])
        fmt, reason = recommend_x_format(sig, facts, "X THREAD")
        self.assertEqual(fmt, "THREAD")
        self.assertIn("sequence", reason.lower())


class TestDualCopyGeneration(unittest.TestCase):
    def test_both_formats_generated_for_same_signal(self):
        sig = _sequence_signal()
        thread = [
            "A commercial cargo ship was hit in the Strait of Hormuz according to regional reporting.",
            "CENTCOM confirmed strikes on Iranian coastal radar sites after the tanker incident.",
            "Iran retaliated against US-linked infrastructure in Kuwait and Bahrain.",
            "Treat early casualty and routing details as provisional until follow-on confirmation.",
            "The next indicators are insurance notices, Gulf statements, and Iranian reopening language.",
        ]
        result = _base_result(signal=sig, x_thread=thread, x_post="Hormuz transit pressure remains elevated after weekend strikes near the strait.")
        dual = build_dual_x_copy(result, result["source_citations"], sig["title"], "X THREAD")
        self.assertTrue(dual["single"]["passed"] or dual["thread"]["passed"])

    def test_single_passes_when_agent_thread_fails(self):
        bad_thread = [
            "A Hormuz ceasefire was supposed to reopen shipping. Instead: drone hit → US strikes.",
            "The under-covered this isn't a bilateral US-Iran scrap.",
            "Watch next: (1) insurers re-price Hormuz transits, (2) Gulf statements follow.",
        ]
        result = _base_result(
            signal=_signal(),
            x_post="Iran says frozen assets may move from Qatar. US officials dispute the transfer. Treat this as unconfirmed until financial movement is verified.",
            x_thread=bad_thread,
        )
        resolved = resolve_queue(result, None)
        x = resolved["operator_block"]["x"]
        self.assertTrue(x.get("single_copy"))
        self.assertFalse(x["copy_blocked"])

    def test_single_fails_when_agent_and_facts_toxic(self):
        thread = [
            "A commercial cargo ship was hit in the Strait of Hormuz according to regional reporting.",
            "CENTCOM confirmed strikes on Iranian coastal radar sites after the tanker incident.",
            "Iran retaliated against US-linked infrastructure in Kuwait and Bahrain.",
            "Treat early casualty and routing details as provisional until follow-on confirmation.",
            "The next indicators are insurance notices, Gulf statements, and Iranian reopening language.",
        ]
        result = _base_result(
            signal=_sequence_signal(
                title="If you're only counting sorties, you're late.",
                why_hamza_should_care="If you're only counting sorties, you're late. the corridor risk repricing is the signal.",
            ),
            x_thread=thread,
            x_post="If you're only counting sorties, you're late. the corridor risk repricing is the signal.",
        )
        dual = build_dual_x_copy(result, result["source_citations"], result["ranked_signals"][0]["title"], "X THREAD")
        self.assertTrue(dual["single"]["passed"])
        self.assertTrue(dual["thread"]["passed"])

    def test_both_pass_render_both(self):
        thread = [
            "A commercial cargo ship was hit in the Strait of Hormuz according to regional reporting.",
            "CENTCOM confirmed strikes on Iranian coastal radar sites after the tanker incident.",
            "Iran retaliated against US-linked infrastructure in Kuwait and Bahrain.",
            "Treat early casualty and routing details as provisional until follow-on confirmation.",
            "The next indicators are insurance notices, Gulf statements, and Iranian reopening language.",
        ]
        result = _base_result(
            signal=_sequence_signal(),
            x_thread=thread,
            x_post="Hormuz transit pressure remains elevated after weekend strikes near the strait. Worth tracking insurance notices before Tuesday talks.",
        )
        resolved = resolve_queue(result, None)
        html = build_email_html(resolved)
        x = resolved["operator_block"]["x"]
        self.assertFalse(x["copy_blocked"])
        self.assertIn("COPY THIS - SINGLE TWEET", html)
        self.assertIn("COPY THIS - THREAD", html)

    def test_both_fail_monitor_only(self):
        result = _base_result(
            signal=_sequence_signal(
                title="If you're only counting sorties, you're late.",
                why_hamza_should_care="Watch next: chokepoints + energy flows under fire.",
            ),
            x_thread=[
                "A Hormuz ceasefire was supposed to reopen shipping. Instead: drone hit → US strikes.",
                "The under-covered this isn't a bilateral US-Iran scrap.",
                "Watch next: (1) insurers re-price Hormuz transits, (2) Gulf statements follow.",
            ],
            x_post="If you're only counting sorties, you're late. the corridor risk repricing is the signal.",
        )
        resolved = resolve_queue(result, None)
        html = build_email_html(resolved)
        self.assertIn("COPY THIS - SINGLE TWEET", html)
        self.assertIn("COPY THIS - THREAD", html)
        self.assertFalse(resolved["operator_block"]["x"]["copy_blocked"])


class TestStructuredFallback(unittest.TestCase):
    def test_fallback_single_from_facts_when_agent_draft_blocked(self):
        sig = _signal(title="Official denial on asset transfer timing")
        facts = extract_signal_facts(_base_result(signal=sig, x_post=""), sig["title"])
        single = build_single_from_facts(facts)
        self.assertGreater(len(single), 40)
        self.assertNotIn("→", single)

    def test_scan_2106_style_produces_both_formats(self):
        sig = _sequence_signal()
        thread = [
            "Hormuz transit pressure remains elevated after weekend strikes near the strait.",
            "CENTCOM confirmed strikes on Iranian coastal radar sites after the tanker incident.",
            "Iran retaliated against US-linked infrastructure in Kuwait and Bahrain.",
            "Treat early casualty and routing details as provisional until follow-on confirmation.",
            "The next indicators are insurance notices, Gulf statements, and Iranian reopening language.",
        ]
        result = _base_result(
            signal=sig,
            x_thread=thread,
            x_post="Hormuz transit pressure remains elevated after weekend strikes near the strait. Worth tracking insurance notices before Tuesday talks.",
            scan_session="SCAN-2026-06-29-2106",
        )
        resolved = resolve_queue(result, None)
        x = resolved["operator_block"]["x"]
        self.assertFalse(x["copy_blocked"])
        self.assertTrue(x.get("single_copy") or x.get("thread_copy"))

    def test_scan_0004_blocked_agent_uses_fact_fallback(self):
        sig = _signal(title="Asset release update from Qatar")
        result = _base_result(
            signal=sig,
            x_post="If you're only counting sorties, you're late. the corridor risk repricing is the signal.",
            x_thread=["Watch next: (1) insurers re-price Hormuz transits, (2) Gulf statements follow."],
            scan_session="SCAN-2026-06-29-0004",
        )
        dual = build_dual_x_copy(result, result["source_citations"], sig["title"], "X POST")
        self.assertTrue(dual["single"]["passed"])
        self.assertIn("Asset release", dual["single"]["text"])


class TestDbFields(unittest.TestCase):
    def test_stores_x_post_and_x_thread_separately(self):
        thread = [
            "A commercial cargo ship was hit in the Strait of Hormuz according to regional reporting.",
            "CENTCOM confirmed strikes on Iranian coastal radar sites after the tanker incident.",
            "Iran retaliated against US-linked infrastructure in Kuwait and Bahrain.",
            "Treat early casualty and routing details as provisional until follow-on confirmation.",
            "The next indicators are insurance notices, Gulf statements, and Iranian reopening language.",
        ]
        result = _base_result(
            signal=_sequence_signal(),
            x_thread=thread,
            x_post="Hormuz transit pressure remains elevated after weekend strikes near the strait. Worth tracking insurance notices before Tuesday talks.",
        )
        resolved = resolve_queue(result, None)
        self.assertTrue(resolved.get("x_post") or resolved["operator_block"]["x"].get("single_copy"))
        self.assertTrue(resolved.get("x_thread") or resolved["operator_block"]["x"].get("thread_copy"))


class TestSlopFreeOutput(unittest.TestCase):
    def test_single_has_no_banned_symbols(self):
        sig = _signal()
        facts = extract_signal_facts(_base_result(signal=sig), sig["title"])
        single = build_single_from_facts(facts)
        self.assertNotIn("→", single)
        self.assertNotIn("—", single)
        self.assertNotIn("#", single)

    def test_thread_builder_avoids_plus_shorthand(self):
        sig = _sequence_signal()
        facts = extract_signal_facts(_base_result(signal=sig), sig["title"])
        tweets = build_thread_from_facts(facts)
        joined = " ".join(tweets)
        self.assertNotIn("+", joined)


if __name__ == "__main__":
    unittest.main()
