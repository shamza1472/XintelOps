"""Comprehensive tests for the global public copy gate."""
from __future__ import annotations

import unittest

from xintelops.delivery.linkedin_synthesis import build_linkedin_block
from xintelops.delivery.public_copy_gate import (
    assert_no_em_dashes,
    build_minimal_verified_single_tweet,
    build_safe_linkedin_fallback,
    gate_public_thread,
    get_verified_signals,
    is_verified_signal,
    prepare_public_copy,
    sanitize_public_copy,
    validate_public_copy,
)

SOURCES = [{"url": "https://reuters.com/hormuz", "name": "Reuters"}]


def _signal(**kwargs) -> dict:
    base = {
        "title": "Hormuz transit disruption",
        "region": "Gulf",
        "confidence": "HIGH",
        "url": "https://reuters.com/hormuz",
        "source": "Reuters",
        "verified_facts": ["A commercial cargo ship was delayed near the strait."],
        "why_hamza_should_care": "Transit delays may widen insurance premiums.",
    }
    base.update(kwargs)
    return base


class TestSanitizePublicCopy(unittest.TestCase):
    def test_replaces_em_dash_with_comma(self):
        out = sanitize_public_copy("Policy shift — markets may react.")
        self.assertNotIn("—", out)
        self.assertIn("Policy shift", out)

    def test_replaces_arrow_symbols(self):
        out = sanitize_public_copy("Drone hit → US strikes → retaliation.")
        self.assertNotIn("→", out)
        self.assertNotIn("->", out)

    def test_rewrites_plus_shorthand_lists(self):
        out = sanitize_public_copy("Chokepoints + energy flows + diplomacy under pressure.")
        self.assertNotIn("+", out)
        self.assertIn("and", out.lower())

    def test_strips_hashtags_and_emojis(self):
        out = sanitize_public_copy("Transit update #Hormuz 🚢 with emoji noise.")
        self.assertNotIn("#", out)
        self.assertNotIn("🚢", out)

    def test_empty_input_returns_empty(self):
        self.assertEqual(sanitize_public_copy(""), "")
        self.assertEqual(sanitize_public_copy("   "), "")


class TestValidatePublicCopy(unittest.TestCase):
    def test_clean_single_tweet_passes(self):
        result = validate_public_copy(
            "Iran reports transit delays near Hormuz according to regional reporting.",
            "x",
            "single_tweet",
            sources=SOURCES,
        )
        self.assertTrue(result["passed"])
        self.assertFalse(result["blocked"])
        assert_no_em_dashes(result["text"])

    def test_banned_phrase_blocks(self):
        result = validate_public_copy(
            "Analysts should leverage a comprehensive landscape view of corridor risk.",
            "x",
            "single_tweet",
        )
        self.assertTrue(result["blocked"])
        self.assertIn("banned phrase", result["block_reason"])

    def test_em_dash_violation_blocks_after_failed_rewrite(self):
        result = validate_public_copy("—", "x", "single_tweet")
        self.assertTrue(result["blocked"])

    def test_empty_copy_blocks(self):
        result = validate_public_copy("", "x", "single_tweet")
        self.assertTrue(result["blocked"])
        self.assertIn("empty", result["violations"])

    def test_truncated_tweet_blocks(self):
        result = validate_public_copy(
            "Both sides now accuse the other of vi",
            "x",
            "single_tweet",
        )
        self.assertTrue(result["blocked"])

    def test_influencer_phrase_blocks(self):
        result = validate_public_copy(
            "If you're only counting sorties, you're late. Corridor risk matters more.",
            "x",
            "single_tweet",
        )
        self.assertTrue(result["blocked"])

    def test_multi_actor_diplomacy_phrase_blocks(self):
        result = validate_public_copy(
            "Chokepoints and energy flows and multi-actor diplomacy under fire near Hormuz.",
            "x",
            "single_tweet",
        )
        self.assertTrue(result["blocked"])

    def test_linkedin_post_passes_clean_copy(self):
        result = validate_public_copy(
            "Iran corridor reporting remains uneven on secondary transit details.\n\n"
            "The issue is whether enforcement behavior changes before diplomacy catches up.",
            "linkedin",
            "linkedin_post",
            sources=SOURCES,
        )
        self.assertTrue(result["passed"])


class TestPreparePublicCopy(unittest.TestCase):
    def test_prepare_passes_already_clean_copy(self):
        result = prepare_public_copy(
            "Officials confirmed transit delays near Hormuz without escalation claims.",
            "x",
            "single_tweet",
            sources=SOURCES,
        )
        self.assertTrue(result["passed"])

    def test_prepare_blocks_irrecoverable_slop(self):
        result = prepare_public_copy(
            "If you're only counting sorties, you're late. Corridor risk matters more.",
            "x",
            "single_tweet",
        )
        self.assertTrue(result["blocked"])


class TestVerifiedSignals(unittest.TestCase):
    def test_is_verified_with_url(self):
        self.assertTrue(is_verified_signal({"title": "Signal", "url": "https://reuters.com/x"}))

    def test_is_verified_with_verified_facts(self):
        self.assertTrue(is_verified_signal({"title": "Signal", "verified_facts": ["Fact one."]}))

    def test_is_not_verified_without_anchor(self):
        self.assertFalse(is_verified_signal({"title": "Signal"}))

    def test_get_verified_signals_prefers_verified_rows(self):
        result = {
            "ranked_signals": [
                {"title": "Unverified", "why_hamza_should_care": "No url."},
                {"title": "Verified", "url": "https://reuters.com/x"},
            ]
        }
        verified = get_verified_signals(result)
        self.assertEqual(verified[0]["title"], "Verified")


class TestMandatorySingleTweetFallback(unittest.TestCase):
    def test_minimal_verified_single_tweet_from_title(self):
        tweet = build_minimal_verified_single_tweet(_signal(), SOURCES)
        self.assertIn("Hormuz transit disruption", tweet)
        self.assertLessEqual(len(tweet), 280)
        assert_no_em_dashes(tweet)

    def test_minimal_tweet_uses_signal_consequence_not_doha_template(self):
        signal = _signal(
            title="Oman and Iran advance Strait of Hormuz transit fee plan despite US objections",
            region="Gulf",
            actors=["Oman", "Iran", "US"],
            why_hamza_should_care=(
                "A fee mechanism at Hormuz would reprice maritime insurance and Gulf transit behavior "
                "even if fighting stays paused."
            ),
            verified_facts=[
                "Oman has proposed a Strait of Hormuz fee plan to the United States.",
                "Iran and Oman are moving forward with transit payment collection despite US objections.",
            ],
        )
        tweet = build_minimal_verified_single_tweet(signal, SOURCES)
        self.assertIn("fee mechanism at hormuz", tweet.lower())
        self.assertNotIn("doha talks", tweet.lower())
        self.assertNotIn("stand down", tweet.lower())

    def test_minimal_tweet_includes_verified_fact(self):
        tweet = build_minimal_verified_single_tweet(
            _signal(
                verified_facts=["A cargo ship was delayed near Hormuz."],
                why_hamza_should_care="",
            ),
            SOURCES,
        )
        self.assertIn("cargo ship", tweet.lower())

    def test_minimal_tweet_strips_toxic_implication(self):
        tweet = build_minimal_verified_single_tweet(
            _signal(why_hamza_should_care="If you're only counting sorties, the signal is late."),
            SOURCES,
        )
        self.assertNotIn("you're late", tweet.lower())
        self.assertNotIn("the signal", tweet.lower())

    def test_minimal_tweet_adds_cautious_line_for_medium_confidence(self):
        tweet = build_minimal_verified_single_tweet(
            _signal(confidence="MEDIUM", why_hamza_should_care="Transit delays widen insurance premiums."),
            SOURCES,
        )
        self.assertIn("transit delays", tweet.lower())


class TestLinkedInGate(unittest.TestCase):
    def test_safe_linkedin_fallback_has_three_paragraphs(self):
        text = build_safe_linkedin_fallback(_signal(), SOURCES)
        self.assertEqual(text.count("\n\n"), 2)
        assert_no_em_dashes(text)

    def test_safe_linkedin_fallback_mentions_region(self):
        text = build_safe_linkedin_fallback(_signal(region="Gulf"), SOURCES)
        self.assertIn("Gulf", text)

    def test_linkedin_block_fail_closed_on_toxic_agent_copy(self):
        result = {
            "day_of_week": "Friday",
            "date_pkt": "2026-06-29",
            "time_pkt": "10:00 PKT",
            "ranked_signals": [
                {
                    "title": "Hormuz transit disruption",
                    "url": "https://reuters.com/hormuz",
                    "live_event_score": 9,
                    "freshness_class": "BREAKING",
                    "why_hamza_should_care": "Transit delays widen.",
                }
            ],
            "linkedin_post": (
                "If you're only counting sorties, you're late. "
                "the corridor risk repricing is the real signal."
            ),
            "crisis_tier_meta": {"immediate_tier": "FLASHPOINT"},
        }
        block = build_linkedin_block(result, [])
        self.assertFalse(block.get("copy_blocked"))
        self.assertTrue(block.get("copy_this"))
        assert_no_em_dashes(block["copy_this"])
        self.assertNotIn("if you're only", block["copy_this"].lower())
        self.assertNotIn("the signal", block["copy_this"].lower())


class TestThreadGate(unittest.TestCase):
    def test_gate_public_thread_passes_clean_tweets(self):
        tweets = [
            "The Hormuz reopening framework is under strain after a cargo ship was hit.",
            "CENTCOM struck Iranian radar sites, and Iran retaliated in Kuwait and Bahrain.",
            "Watch for insurance advisories, Gulf damage assessments, and reopening statements.",
        ]
        result = gate_public_thread(tweets, sources=SOURCES, primary_title="Hormuz")
        self.assertTrue(result["passed"])
        assert_no_em_dashes(result["text"])

    def test_gate_public_thread_blocks_toxic_tweet(self):
        tweets = [
            "The under-covered this isn't a bilateral US-Iran scrap near Hormuz.",
            "Insurance repricing may follow if transit delays widen near the strait.",
            "Official statements remain the next indicator for corridor behavior.",
        ]
        result = gate_public_thread(tweets, sources=SOURCES)
        self.assertTrue(result["blocked"])
        self.assertIn("Tweet 1", result["block_reason"])

    def test_gate_public_thread_blocks_empty_thread(self):
        result = gate_public_thread([])
        self.assertTrue(result["blocked"])
        self.assertIn("empty thread", result["violations"])


class TestAssertNoEmDashes(unittest.TestCase):
    def test_assert_no_em_dashes_passes_clean_text(self):
        assert_no_em_dashes("Clean copy with commas only.")


if __name__ == "__main__":
    unittest.main()
