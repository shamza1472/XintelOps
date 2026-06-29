"""Tests for fail-closed final copy-paste safety gate on public X copy."""
from __future__ import annotations

import unittest

from xintelops.delivery.editorial import audit_final_copy_violations, final_anti_ai_slop_pass
from xintelops.delivery.email_builder import build_email_html
from xintelops.delivery.queue import _format_draft, resolve_queue
from xintelops.delivery.x_copy import (
    apply_brand_footer_to_tweets,
    apply_final_copy_safety_gate,
    format_thread_for_display,
    is_truncated_tweet,
)

SCAN_2026_06_28_1802_THREAD = [
    "A Hormuz ceasefire was supposed to reopen shipping. Instead: drone hit on a commercial cargo ship → US strikes on Iranian coastal targets → Iranian retaliation on US-linked sites in Kuwait and Bahrain. The chokepoint story is kinetic again.",
    "CENTCOM framed the US response as targeting missile/drone storage and coastal radar after the tanker attack. Tehran, meanwhile, says Hormuz 'management' stays under Iranian control for 30 days. Markets hear policy; insurers hear guns.",
    "The under-covered this isn't a bilateral US-Iran scrap. Retaliatory strikes in Kuwait and Bahrain drag host-nation basing and Gulf routing into the same escalation frame as the strait itself.",
    "Pakistan and Qatar had brokered an MOU that briefly ticked Hormuz traffic up and oil down. Today's exchange suggests the 'open strait, unsettled waters' phase. lots of paper, diverging claims, easy re-escalation.",
    "Watch next: (1) whether commercial insurers re-price Hormuz transits, (2) Gulf state statements on basing spillover, (3) whether Araghchi's 30-day control assertion hardens into de facto transit rules.",
    "chokepoints + energy flows + multi-actor diplomacy under fire. If you're only counting sorties, you're late. the corridor risk repricing is the signal.",
]


def _base_result(*, x_thread: list[str] | None = None, x_post: str = "", **overrides) -> dict:
    base = {
        "operator_decisions": {
            "one_signal_to_post": {
                "title": "US-Iran Hormuz escalation",
                "action": "X THREAD",
                "why": "Live corridor pressure.",
            },
        },
        "ranked_signals": [
            {
                "title": "US-Iran Hormuz escalation",
                "url": "https://reuters.com/hormuz",
                "source": "Reuters",
                "new_information_detected": True,
            }
        ],
        "source_citations": [{"name": "Reuters", "url": "https://reuters.com/hormuz"}],
        "x_thread": x_thread or [],
        "x_post": x_post,
        "scan_session": "SCAN-2026-06-28-1802",
        "date_pkt": "2026-06-28",
        "time_pkt": "18:02 PKT",
    }
    base.update(overrides)
    return base


class TestProductionPhraseBlocks(unittest.TestCase):
    def test_under_covered_this_isnt_blocks(self):
        out = final_anti_ai_slop_pass(
            "The under-covered this isn't a bilateral US-Iran scrap. Retaliatory strikes in Kuwait and Bahrain drag host-nation basing into the same frame."
        )
        self.assertTrue(out["blocked"])

    def test_if_youre_only_youre_late_blocks(self):
        out = final_anti_ai_slop_pass("If you're only counting sorties, you're late. Corridor risk matters more.")
        self.assertTrue(out["blocked"])

    def test_markets_hear_insurers_hear_guns_blocks(self):
        out = final_anti_ai_slop_pass(
            "Tehran says Hormuz management stays under Iranian control for 30 days. Markets hear policy; insurers hear guns."
        )
        self.assertTrue(out["blocked"])

    def test_chokepoints_plus_energy_flows_blocks(self):
        out = final_anti_ai_slop_pass(
            "Chokepoints + energy flows + multi-actor diplomacy under fire across the Gulf corridor."
        )
        self.assertTrue(out["blocked"])

    def test_lowercase_sentence_start_blocks(self):
        out = final_anti_ai_slop_pass(
            "Today's exchange suggests diverging claims. lots of paper, diverging claims, easy re-escalation."
        )
        self.assertTrue(out["blocked"])

    def test_arrow_symbol_blocks(self):
        out = final_anti_ai_slop_pass(
            "Drone hit on a cargo ship → US strikes on Iranian coastal targets → Iranian retaliation in Kuwait."
        )
        self.assertTrue(out["blocked"])

    def test_compressed_numbered_list_blocks(self):
        out = final_anti_ai_slop_pass(
            "Worth tracking: (1) whether insurers re-price Hormuz transits, (2) Gulf state statements on basing spillover."
        )
        self.assertTrue(out["blocked"])


class TestFailClosedGate(unittest.TestCase):
    def test_banned_phrase_after_rewrite_still_blocks(self):
        gate = apply_final_copy_safety_gate(
            ["The chokepoint story is kinetic again after reported strikes near the strait."]
        )
        self.assertTrue(gate["blocked"])
        self.assertIn("FINAL COPY QUALITY FAIL", gate["block_reason"])

    def test_any_failed_tweet_blocks_whole_thread(self):
        tweets = [
            "Iran corridor signal one with verified source detail from the strait today.",
            "Insurance repricing may follow if transit delays widen near Hormuz shipping lanes.",
            "Watch routing and Gulf basing posture in the next scan window for updates.",
            "Live Event Priority Mode only.",
        ]
        gate = apply_final_copy_safety_gate(tweets)
        self.assertTrue(gate["blocked"])


class TestFooterRule(unittest.TestCase):
    def test_dense_final_tweet_omits_footer(self):
        dense = (
            "Chokepoints, energy flows, and multi-actor diplomacy remain under pressure across the Gulf. "
            "Corridor risk repricing may follow if insurers adjust Hormuz transit terms this week."
        )
        tweets = apply_brand_footer_to_tweets(["One.", "Two.", dense])
        self.assertNotIn("XIntelOps", tweets[-1])

    def test_clean_final_tweet_gets_footer(self):
        tweets = apply_brand_footer_to_tweets(["One.", "Two.", "Watch for insurance advisories and Gulf statements."])
        self.assertIn("XIntelOps", tweets[-1])


class TestScanRegression(unittest.TestCase):
    def test_scan_2026_06_28_1802_blocks_entire_thread(self):
        gate = apply_final_copy_safety_gate(SCAN_2026_06_28_1802_THREAD)
        self.assertTrue(gate["blocked"])
        self.assertIn("COPY BLOCKED — FINAL COPY QUALITY FAIL", gate["block_reason"])

    def test_scan_thread_does_not_render_copy_this(self):
        result = _base_result(x_thread=SCAN_2026_06_28_1802_THREAD)
        draft = _format_draft(result, "X THREAD")
        meta = result.get("_x_copy_meta") or {}
        self.assertFalse(draft)
        self.assertTrue(meta.get("blocked"))
        self.assertIn("FINAL COPY QUALITY FAIL", meta.get("block_reason", ""))


class TestEmailAndDbGating(unittest.TestCase):
    def test_email_shows_partial_copy_when_one_format_passes(self):
        result = resolve_queue(_base_result(x_thread=SCAN_2026_06_28_1802_THREAD), None)
        html = build_email_html(result)
        x = result["operator_block"]["x"]
        if x.get("copy_blocked"):
            self.assertIn("X BLOCKED", html)
        else:
            self.assertTrue("COPY THIS — SINGLE TWEET" in html or "COPY THIS — THREAD" in html)

    def test_active_now_draft_empty_when_both_formats_fail(self):
        result = resolve_queue(
            _base_result(
                x_thread=SCAN_2026_06_28_1802_THREAD,
                ranked_signals=[{
                    "title": "If you're only counting sorties, you're late.",
                    "why_hamza_should_care": "Watch next: chokepoints + energy flows under fire.",
                    "url": "https://reuters.com/hormuz",
                }],
                operator_decisions={
                    "one_signal_to_post": {
                        "title": "If you're only counting sorties, you're late.",
                        "action": "X THREAD",
                    },
                },
            ),
            None,
        )
        self.assertEqual(result["content_queue"]["active_now_draft"], "")
        self.assertTrue(result["operator_block"]["x"]["copy_blocked"])


class TestCleanThreadPasses(unittest.TestCase):
    def test_serious_analyst_thread_passes(self):
        thread = [
            "The Hormuz reopening framework is under strain after a commercial cargo ship was hit.",
            "CENTCOM struck Iranian missile and radar sites, and Iran retaliated in Kuwait and Bahrain.",
            "The issue is control of transit rules and enforcement of the June 17 framework.",
            "The trigger involved commercial shipping, which can move insurance premiums before formal closure.",
            "Watch for insurance advisories, Gulf damage assessments, and Iranian reopening statements.",
        ]
        gate = apply_final_copy_safety_gate(thread)
        self.assertFalse(gate["blocked"])
        self.assertEqual(len(gate["tweets"]), 5)

    def test_valid_thread_renders_copy_this(self):
        thread = [
            "The Hormuz reopening framework is under strain after a commercial cargo ship was hit.",
            "CENTCOM struck Iranian missile and radar sites, and Iran retaliated in Kuwait and Bahrain.",
            "The issue is control of transit rules and enforcement of the June 17 framework.",
            "The trigger involved commercial shipping, which can move insurance premiums before formal closure.",
            "Watch for insurance advisories, Gulf damage assessments, and Iranian reopening statements.",
        ]
        result = _base_result(x_thread=thread)
        draft = _format_draft(result, "X THREAD")
        self.assertTrue(draft)
        self.assertIn("THREAD", draft)
        self.assertNotIn("→", draft)


class TestTruncationGuard(unittest.TestCase):
    def test_blocks_incomplete_tweet_ending_with_vi(self):
        self.assertTrue(is_truncated_tweet("Both sides now accuse the other of vi"))
        out = final_anti_ai_slop_pass("Both sides now accuse the other of vi")
        self.assertTrue(out["blocked"])


class TestLegacyExactPhrases(unittest.TestCase):
    def test_em_dash_removed_or_blocked(self):
        out = final_anti_ai_slop_pass("Translation — Washington doesn't control the timeline for reopening.")
        self.assertTrue(out["blocked"] or "—" not in out["text"])

    def test_internal_operator_labels_block(self):
        out = final_anti_ai_slop_pass("Action: X THREAD. Format: THREAD. Tier: FLASHPOINT.")
        self.assertTrue(out["blocked"])

    def test_long_clean_text_fits_280(self):
        long_text = " ".join(["Transit"] * 40)
        out = final_anti_ai_slop_pass(long_text)
        self.assertLessEqual(len(out["text"]), 280)
        self.assertFalse(out["blocked"])


if __name__ == "__main__":
    unittest.main()
