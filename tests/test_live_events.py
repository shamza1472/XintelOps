"""Acceptance tests for live event priority, LinkedIn scheduling, and cooldown."""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from xintelops.delivery.linkedin_synthesis import build_linkedin_block, linkedin_window_state
from xintelops.delivery.live_events import (
    classify_freshness,
    compute_live_event_score,
    cooldown_penalty,
    merge_active_events,
    normalize_event_key,
)
from xintelops.delivery.operator import enrich_operator_result
from xintelops.delivery.ranking import apply_ranking_bias, select_immediate_post

PKT = timezone(timedelta(hours=5))


def _live_diplomacy_signal(title: str = "Multi-state ceasefire talks with energy market consequences") -> dict:
    return {
        "title": title,
        "region": "Gulf / South Asia / Europe",
        "domain": "diplomacy",
        "source": "Reuters / Official statements",
        "url": "https://example.com/live-diplomacy",
        "why_hamza_should_care": "Active negotiations with maritime and energy consequences across multiple states.",
        "confidence": "HIGH",
        "crisis_flag": True,
        "freshness_class": "LIVE",
        "scores": {
            "edge": 7,
            "post_worthiness": 9,
            "forecast_value": 9,
            "niche_relevance": 8,
            "live_momentum": 10,
        },
        "recommended_action": "X THREAD",
        "actors": ["state a", "state b", "state c", "state d"],
    }


def _slow_burn_china() -> dict:
    return {
        "title": "China farm drones: a trojan horse Washington overlooks",
        "region": "China / Indo-Pacific",
        "domain": "dual-use technology",
        "source": "War on the Rocks",
        "url": "https://warontherocks.com/farm-drones",
        "why_hamza_should_care": "Evergreen analysis on agricultural drone supply chains.",
        "confidence": "HIGH",
        "scores": {
            "edge": 8,
            "post_worthiness": 8,
            "forecast_value": 7,
            "niche_relevance": 9,
            "live_momentum": 4,
        },
        "recommended_action": "X POST",
    }


class LiveEventAcceptanceTests(unittest.TestCase):
    def test_c_high_momentum_event_scores_and_wins(self):
        live = _live_diplomacy_signal()
        china = _slow_burn_china()
        meta = compute_live_event_score(live)
        self.assertGreaterEqual(meta["live_event_score"], 9)
        self.assertTrue(meta["live_event_priority"])

        ranked = apply_ranking_bias([china, live])
        immediate = select_immediate_post(ranked, None)
        self.assertEqual(immediate["title"], live["title"])
        self.assertGreaterEqual(immediate.get("live_event_score", 0), 9)

    def test_c_active_event_carried_forward(self):
        live = _live_diplomacy_signal()
        active = [
            {
                "normalized_event_key": normalize_event_key(live["title"], live["url"]),
                "title": live["title"],
                "regions": ["Gulf"],
                "active_until": (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat(),
                "live_event_score": 10,
                "momentum_score": 10,
                "crisis_flag": True,
                "latest_update_summary": "Talks ongoing.",
                "resolved": False,
            }
        ]
        merged, carry = merge_active_events([_slow_burn_china()], active)
        self.assertEqual(len(merged), 1)
        self.assertFalse(any(s.get("carried_forward") for s in merged))
        self.assertEqual(carry[0]["carry_status"], "carried_forward")

    def test_d_slow_burn_cooldown(self):
        china = _slow_burn_china()
        key = normalize_event_key(china["title"], china["url"])
        rec_history = [
            {
                "normalized_event_key": key,
                "title": china["title"],
                "recommended_at": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
            }
        ]
        penalty, reason = cooldown_penalty(china, rec_history)
        self.assertGreaterEqual(penalty, 40)

        ranked = apply_ranking_bias([china], rec_history=rec_history)
        self.assertGreaterEqual(ranked[0].get("penalty", 0), 40)

    def test_a_monday_linkedin_in_window(self):
        result = {
            "day_of_week": "Monday",
            "date_pkt": "2026-06-22",
            "time_pkt": "09:30 PKT",
            "ranked_signals": [_slow_burn_china()],
            "linkedin_post": "LinkedIn draft ready for posting.",
        }
        self.assertEqual(linkedin_window_state(result), "in_window")
        block = build_linkedin_block(result, [])
        self.assertEqual(block["status"], "In scheduled window")
        self.assertEqual(block["action"], "Post now")
        self.assertTrue(block.get("copy_this"))

    def test_b_monday_after_window_no_crisis(self):
        result = {
            "day_of_week": "Monday",
            "date_pkt": "2026-06-22",
            "time_pkt": "18:00 PKT",
            "crisis_detected": False,
            "ranked_signals": [_slow_burn_china()],
        }
        self.assertEqual(linkedin_window_state(result), "after_window")
        block = build_linkedin_block(result, [])
        self.assertEqual(block["status"], "Window passed")
        self.assertIn("Wednesday", block.get("next_window", ""))

    def test_b_crisis_exception_after_window(self):
        live = _live_diplomacy_signal()
        result = {
            "day_of_week": "Monday",
            "date_pkt": "2026-06-22",
            "time_pkt": "18:00 PKT",
            "ranked_signals": [live],
            "operator_decisions": {
                "best_immediate_post": {"title": live["title"]},
                "one_signal_to_post": {"title": live["title"], "action": "X THREAD"},
            },
            "linkedin_post": "Crisis LinkedIn post.",
        }
        result["crisis_tier_meta"] = {
            "immediate_tier": "FLASHPOINT",
            "posting_exception": True,
            "crisis_detected": True,
            "scan_tier": "FLASHPOINT",
        }
        block = build_linkedin_block(result, [])
        self.assertEqual(block["status"], "Crisis exception")
        self.assertEqual(block["action"], "Post now despite missed window")

    def test_freshness_classification(self):
        self.assertIn(classify_freshness(_slow_burn_china()), {"ANALYSIS", "EVERGREEN"})
        self.assertIn(classify_freshness(_live_diplomacy_signal()), {"LIVE", "BREAKING", "DEVELOPING"})

    def test_enrich_operator_pending_events(self):
        result = enrich_operator_result(
            {
                "scan_session": "TEST-SCAN",
                "ranked_signals": [_live_diplomacy_signal(), _slow_burn_china()],
            }
        )
        self.assertTrue(result.get("_pending_active_events"))
        self.assertGreaterEqual(result["operator_decisions"]["best_immediate_post"].get("live_event_score", 0), 9)


if __name__ == "__main__":
    unittest.main()
