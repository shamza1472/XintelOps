"""Tests for active event lifecycle, tier truth, source roles, editorial guard."""
from __future__ import annotations

import unittest

from xintelops.delivery.active_event_clusters import cluster_active_events, event_family
from xintelops.delivery.crisis_tier import classify_scan_tier
from xintelops.delivery.editorial import anti_slop_editorial_pass
from xintelops.delivery.live_events import build_active_live_event_block, merge_active_events
from xintelops.delivery.source_roles import ROLE_PRIMARY, classify_source_role, partition_sources_by_role
from xintelops.delivery.x_copy import is_malformed_tweet, parse_x_thread, prepare_x_copy, validate_thread_tweets


def _hormuz_event(title_suffix: str = "", score: int = 9) -> dict:
    base = "US-Iran Hormuz escalation tanker strike US reprisals"
    return {
        "title": f"{base} {title_suffix}".strip(),
        "normalized_event_key": f"key-{title_suffix or 'a'}",
        "live_event_score": score,
        "last_seen_at": "2026-06-28T10:00:00+00:00",
        "previous_action": "X THREAD",
        "latest_update_summary": "Corridor pressure remains elevated.",
        "carry_status": "carried_forward",
        "regions": ["Gulf"],
    }


class TestActiveEventClustering(unittest.TestCase):
    def test_hormuz_variants_cluster_to_five_or_fewer(self):
        events = [_hormuz_event(str(i)) for i in range(20)]
        clustered = cluster_active_events(events)
        self.assertLessEqual(len(clustered), 5)

    def test_ras_laffan_family_clusters(self):
        titles = [
            "Qatar Ras Laffan LNG site explosion kills at least 13",
            "Qatar Ras Laffan LNG plant explosion kills at least 13, injures dozens",
            "Qatar Ras Laffan LNG site explosion kills at least 13 at main processing hub",
        ]
        events = [{"title": t, "live_event_score": 9, "regions": ["Gulf"]} for t in titles]
        self.assertEqual(event_family(titles[0], ["Gulf"]), "ras_laffan")
        self.assertEqual(len(cluster_active_events(events)), 1)

    def test_render_max_five_clusters_not_twenty_rows(self):
        carry = [_hormuz_event(str(i)) for i in range(20)]
        block = build_active_live_event_block(carry)
        self.assertLessEqual(len(block["events"]), 5)
        self.assertIn("active clusters", block["summary"])
        self.assertTrue(block.get("footer"))


class TestMaterialChangeTruth(unittest.TestCase):
    def test_carried_forward_without_delta_is_cooling(self):
        carry = [_hormuz_event("1")]
        block = build_active_live_event_block(carry, selected_title="Other signal")
        self.assertEqual(block["events"][0]["status"], "cooling")
        self.assertEqual(block["events"][0]["material_change"], "no")
        self.assertEqual(block["events"][0]["operator_decision"], "Monitor Only")

    def test_updated_with_new_information_is_material(self):
        carry = [{**_hormuz_event("1"), "carry_status": "updated", "new_information_detected": True}]
        block = build_active_live_event_block(carry)
        self.assertEqual(block["events"][0]["material_change"], "yes")
        self.assertEqual(block["events"][0]["status"], "updated")


class TestMergeActiveEvents(unittest.TestCase):
    def test_cooling_carried_events_not_reinjected_to_ranking(self):
        active = [_hormuz_event("x")]
        merged, carry = merge_active_events([{"title": "Fresh signal", "url": "https://x.com/1"}], active)
        self.assertEqual(len(carry), 1)
        self.assertEqual(len(merged), 1)
        self.assertFalse(any(s.get("carried_forward") for s in merged))


class TestCrisisTierTruth(unittest.TestCase):
    def test_stale_flashpoint_queue_selected_priority(self):
        result = {
            "operator_decisions": {"best_immediate_post": {"title": "Priority signal"}},
            "ranked_signals": [
                {
                    "title": "Priority signal",
                    "live_event_score": 6,
                    "consequence_score": 7,
                    "update_velocity": 5,
                    "freshness_class": "DEVELOPING",
                    "confidence": "HIGH",
                    "scores": {"live_momentum": 6},
                    "new_information_detected": False,
                },
                {
                    "title": "Stale flashpoint",
                    "live_event_score": 9,
                    "consequence_score": 9,
                    "update_velocity": 9,
                    "freshness_class": "LIVE",
                    "confidence": "HIGH",
                    "scores": {"live_momentum": 9},
                    "carried_forward": True,
                    "new_information_detected": False,
                },
            ],
        }
        tier = classify_scan_tier(result)
        self.assertEqual(tier["immediate_tier"], "PRIORITY")
        self.assertFalse(tier["crisis_detected"])
        self.assertEqual(tier["scan_tier"], "PRIORITY")


class TestSourceRoles(unittest.TestCase):
    def test_primary_without_title_in_why_supports(self):
        src = {
            "name": "Reuters",
            "url": "https://reuters.com/hormuz",
            "why_supports": "Frames escalation as worst since peace deal; confirms tanker strike.",
        }
        role = classify_source_role(
            src,
            primary_title="US-Iran Hormuz escalation: tanker strike",
            package_index=0,
            in_primary_package=True,
        )
        self.assertEqual(role, ROLE_PRIMARY)

    def test_factual_why_becomes_primary(self):
        src = {
            "name": "BBC",
            "url": "https://bbc.com/1",
            "why_supports": "Both-side ceasefire violation claims and CENTCOM strike confirmation.",
        }
        role = classify_source_role(
            src,
            primary_title="US-Iran Hormuz escalation",
            in_primary_package=True,
            package_index=1,
        )
        self.assertEqual(role, ROLE_PRIMARY)

    def test_partition_puts_reuters_in_primary(self):
        buckets = partition_sources_by_role(
            [
                {"name": "Reuters / BBC", "url": "https://reuters.com/x", "why_supports": "Confirms strike."},
                {"name": "Context", "url": "https://example.com/y", "why_supports": "Background only."},
            ],
            primary_title="US-Iran Hormuz escalation",
            selected_signal_url="https://reuters.com/x",
        )
        self.assertTrue(buckets[ROLE_PRIMARY])


class TestEditorialGuard(unittest.TestCase):
    def test_removes_xintelops_angle(self):
        out = anti_slop_editorial_pass("XIntelOps angle: chokepoint + basing + energy")
        self.assertNotIn("xintelops angle", out["text"].lower())

    def test_removes_most_feeds_skip(self):
        out = anti_slop_editorial_pass("Second-order angle most feeds skip undersea cables")
        self.assertNotIn("most feeds skip", out["text"].lower())

    def test_removes_not_a_headline_cycle(self):
        out = anti_slop_editorial_pass("This is not a headline cycle story")
        self.assertNotIn("not a headline cycle", out["text"].lower())


class TestMalformedTweets(unittest.TestCase):
    def test_colon_fragment_is_malformed(self):
        self.assertTrue(is_malformed_tweet(": direct Gulf corridor + multi-state crisis management"))

    def test_validate_removes_malformed_when_enough_valid(self):
        tweets = [
            "US struck Iranian coastal radar after a commercial cargo ship was hit in Hormuz.",
            "Iran retaliated against US-linked sites in Kuwait and Bahrain according to reports.",
            "CENTCOM confirmed the reprisal strikes on missile storage near the coast.",
            ": direct Gulf corridor + multi-state crisis management",
        ]
        result = validate_thread_tweets(tweets)
        self.assertFalse(result["blocked"])
        self.assertEqual(len(result["tweets"]), 3)

    def test_validate_blocks_short_thread(self):
        tweets = ["Valid tweet with enough content here.", ": label only fragment"]
        result = validate_thread_tweets(tweets)
        self.assertTrue(result["blocked"])
        self.assertIn("MALFORMED TWEET", result["block_reason"])

    def test_prepare_x_copy_blocks_malformed_thread(self):
        meta = prepare_x_copy(
            {"x_thread": ["Good tweet with verified source detail here.", ": bad label fragment only"]},
            "X THREAD",
        )
        self.assertTrue(meta["blocked"])


if __name__ == "__main__":
    unittest.main()
