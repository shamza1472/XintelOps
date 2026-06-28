"""Tests for final copy-paste safety gate on public X copy."""
from __future__ import annotations

import unittest

from xintelops.delivery.editorial import final_anti_ai_slop_pass
from xintelops.delivery.queue import _format_draft
from xintelops.delivery.x_copy import (
    apply_brand_footer_to_tweets,
    apply_final_copy_safety_gate,
    format_thread_for_display,
    is_truncated_tweet,
)


def _base_result(*, x_thread: list[str] | None = None, x_post: str = "") -> dict:
    return {
        "operator_decisions": {
            "one_signal_to_post": {
                "title": "US-Iran Hormuz escalation",
                "action": "X THREAD",
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
    }


class TestTruncationGuard(unittest.TestCase):
    def test_blocks_incomplete_tweet_ending_with_vi(self):
        self.assertTrue(is_truncated_tweet("Both sides now accuse the other of vi"))
        out = final_anti_ai_slop_pass("Both sides now accuse the other of vi")
        self.assertTrue(out["blocked"])


class TestFinalBannedPhrases(unittest.TestCase):
    def test_removes_this_isnt_a_headline_cycle(self):
        out = final_anti_ai_slop_pass("This isn't a headline cycle — it's a chokepoint governance failure.")
        self.assertFalse(out["blocked"])
        self.assertNotIn("headline cycle", out["text"].lower())

    def test_removes_what_most_analysts_miss(self):
        out = final_anti_ai_slop_pass("What most analysts miss: the trigger was a cargo ship.")
        self.assertFalse(out["blocked"])
        self.assertNotIn("what most analysts miss", out["text"].lower())

    def test_removes_bottom_line(self):
        out = final_anti_ai_slop_pass("Bottom line: this reshapes Gulf basing risk and transit rules now.")
        self.assertFalse(out["blocked"])
        self.assertNotIn("bottom line", out["text"].lower())

    def test_removes_live_event_priority_mode(self):
        out = final_anti_ai_slop_pass("Bottom line: Live Event Priority Mode.")
        self.assertNotIn("live event priority mode", out["text"].lower())

    def test_removes_post_primary_thread(self):
        out = final_anti_ai_slop_pass(
            "Post primary thread, monitor Araghchi statements and any Iranian reopening terms."
        )
        self.assertFalse(out["blocked"])
        self.assertNotIn("post primary thread", out["text"].lower())


class TestEmDashBan(unittest.TestCase):
    def test_removes_all_em_dashes(self):
        out = final_anti_ai_slop_pass("Translation — Washington doesn't control the timeline.")
        self.assertFalse(out["blocked"])
        self.assertNotIn("—", out["text"])
        self.assertNotIn("translation", out["text"].lower())


class TestLengthAndTruncation(unittest.TestCase):
    def test_keeps_tweet_under_280_without_mid_word_cut(self):
        long_text = " ".join(["word"] * 60)
        out = final_anti_ai_slop_pass(long_text)
        self.assertLessEqual(len(out["text"]), 280)
        self.assertFalse(is_truncated_tweet(out["text"]))


class TestInternalLabels(unittest.TestCase):
    def test_blocks_internal_operator_labels(self):
        out = final_anti_ai_slop_pass("Action: X THREAD. Format: THREAD. Tier: FLASHPOINT.")
        self.assertTrue(out["blocked"])


class TestBrandFooter(unittest.TestCase):
    def test_footer_only_once_at_end(self):
        tweets = apply_brand_footer_to_tweets(["One.", "Two.", "Three."])
        rendered = format_thread_for_display(tweets, add_brand_footer=False)
        self.assertEqual(rendered.count("XIntelOps"), 1)


class TestFinalGateIntegration(unittest.TestCase):
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
        self.assertNotIn("COPY BLOCKED", draft)
        self.assertIn("THREAD", draft)

    def test_invalid_thread_renders_final_copy_blocked(self):
        thread = [
            "The Hormuz MoU is breaking in real time with multiple reported strikes.",
            "This isn't a headline cycle — it's a chokepoint governance failure.",
            "Both sides now accuse the other of vi",
        ]
        result = _base_result(x_thread=thread)
        draft = _format_draft(result, "X THREAD")
        meta = result.get("_x_copy_meta") or {}
        self.assertFalse(draft)
        self.assertTrue(meta.get("blocked"))
        self.assertIn("FINAL COPY QUALITY FAIL", meta.get("block_reason", ""))


class TestApplyFinalCopySafetyGate(unittest.TestCase):
    def test_truncated_tweet_blocks_whole_thread(self):
        tweets = [
            "Iran corridor signal one with verified source detail from the strait today.",
            "Insurance repricing may follow if transit delays widen near Hormuz shipping lanes.",
            "Watch routing and Gulf basing posture in the next scan window for updates.",
            "Both sides now accuse the other of vi",
        ]
        gate = apply_final_copy_safety_gate(tweets)
        self.assertTrue(gate["blocked"])
        self.assertIn("FINAL COPY QUALITY FAIL", gate["block_reason"])

    def test_removes_broken_tweet_when_enough_remain(self):
        tweets = [
            "Iran corridor signal one with verified source detail from the strait today.",
            "Insurance repricing may follow if transit delays widen near Hormuz shipping lanes.",
            "Watch routing and Gulf basing posture in the next scan window for updates.",
            "Live Event Priority Mode only.",
        ]
        gate = apply_final_copy_safety_gate(tweets)
        self.assertFalse(gate["blocked"])
        self.assertEqual(len(gate["tweets"]), 3)


if __name__ == "__main__":
    unittest.main()
