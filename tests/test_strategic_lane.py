"""Acceptance tests for strategic-lane scoring (Tests A–E) and live event priority."""
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
from xintelops.delivery.strategic_lane import (
    classify_lane_relevance_type,
    compute_strategic_lane_score,
)


def _live_diplomacy_signal(title: str = "Iran-Gulf ceasefire talks with Hormuz energy market consequences") -> dict:
    return {
        "title": title,
        "region": "Gulf / Iran",
        "domain": "diplomacy",
        "source": "Reuters / Official statements",
        "url": "https://example.com/live-diplomacy",
        "why_hamza_should_care": "Active ceasefire negotiations with maritime chokepoint and energy consequences.",
        "confidence": "HIGH",
        "crisis_flag": True,
        "freshness_class": "LIVE",
        "scores": {
            "edge": 7,
            "post_worthiness": 9,
            "forecast_value": 9,
            "niche_relevance": 8,
            "live_momentum": 10,
            "consequence": 9,
        },
        "recommended_action": "X THREAD",
        "actors": ["iran", "gulf states", "mediator", "energy markets"],
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
            "consequence": 4,
        },
        "recommended_action": "X POST",
    }


def _panama_chokepoint() -> dict:
    return {
        "title": "Panama Canal shipping disruption triggers global logistics repricing",
        "region": "Panama / Global",
        "domain": "maritime",
        "source": "Reuters",
        "url": "https://example.com/panama",
        "why_hamza_should_care": "Major chokepoint closure affecting global shipping lanes and energy routing.",
        "confidence": "HIGH",
        "crisis_flag": True,
        "freshness_class": "BREAKING",
        "scores": {
            "edge": 8,
            "post_worthiness": 9,
            "forecast_value": 8,
            "niche_relevance": 5,
            "live_momentum": 9,
            "consequence": 9,
        },
        "recommended_action": "X POST",
    }


def _routine_nato_aid() -> dict:
    return {
        "title": "NATO announces routine military aid package for Ukraine",
        "region": "Europe / Ukraine",
        "domain": "defense",
        "source": "NATO",
        "url": "https://example.com/nato-aid",
        "why_hamza_should_care": "Standard battlefield aid update without chokepoint or energy linkage.",
        "confidence": "HIGH",
        "scores": {
            "edge": 3,
            "post_worthiness": 4,
            "forecast_value": 4,
            "niche_relevance": 3,
            "live_momentum": 4,
            "consequence": 3,
        },
        "recommended_action": "X POST",
    }


def _black_sea_chokepoint() -> dict:
    return {
        "title": "Black Sea grain and energy blockade disrupts maritime insurance and sanctions enforcement",
        "region": "Ukraine / Black Sea",
        "domain": "maritime",
        "source": "Reuters",
        "url": "https://example.com/black-sea",
        "why_hamza_should_care": "Chokepoint disruption affecting grain exports, energy flows, and maritime insurance.",
        "confidence": "HIGH",
        "freshness_class": "LIVE",
        "scores": {
            "edge": 7,
            "post_worthiness": 8,
            "forecast_value": 8,
            "niche_relevance": 5,
            "live_momentum": 8,
            "consequence": 9,
        },
        "recommended_action": "X POST",
    }


def _us_iran_diplomacy() -> dict:
    return {
        "title": "U.S.-Iran talks reduce immediate Hormuz risk",
        "region": "Gulf / U.S. / Iran",
        "domain": "diplomacy",
        "source": "Reuters",
        "url": "https://example.com/us-iran",
        "why_hamza_should_care": "Diplomacy lowers near-term energy risk at Hormuz chokepoint.",
        "confidence": "HIGH",
        "freshness_class": "LIVE",
        "scores": {"edge": 7, "post_worthiness": 9, "forecast_value": 8, "niche_relevance": 8, "live_momentum": 9},
        "recommended_action": "X POST",
    }


def _india_uae_brahmos() -> dict:
    return {
        "title": "India-UAE BrahMos defense procurement talks advance",
        "region": "India / UAE / Gulf",
        "domain": "defense procurement",
        "source": "Defense News",
        "url": "https://example.com/brahmos",
        "why_hamza_should_care": "Gulf states hedging militarily despite diplomatic calm.",
        "confidence": "MEDIUM",
        "scores": {"edge": 7, "post_worthiness": 7, "forecast_value": 8, "niche_relevance": 8, "live_momentum": 6},
        "recommended_action": "LINKEDIN",
    }


class StrategicLaneAcceptanceTests(unittest.TestCase):
    def test_a_preferred_region_low_momentum_does_not_beat_chokepoint(self):
        """Test A — China analysis should not beat breaking maritime/energy event."""
        china = _slow_burn_china()
        china["freshness_class"] = "ANALYSIS"
        maritime = {
            "title": "Red Sea shipping disruption forces reroute through Cape of Good Hope",
            "region": "Red Sea / Global",
            "domain": "maritime",
            "source": "Reuters",
            "why_hamza_should_care": "Major shipping lane disruption with energy and insurance consequences.",
            "confidence": "HIGH",
            "freshness_class": "BREAKING",
            "scores": {"edge": 7, "post_worthiness": 9, "forecast_value": 8, "niche_relevance": 7, "live_momentum": 9, "consequence": 9},
            "recommended_action": "X POST",
        }
        ranked = apply_ranking_bias([china, maritime])
        immediate = select_immediate_post(ranked, None)
        self.assertEqual(immediate["title"], maritime["title"])
        self.assertGreater(immediate.get("final_score", 0), ranked[1].get("final_score", 0))

    def test_b_non_core_chokepoint_global_strategic_relevance(self):
        """Test B — Panama Canal can become Best Immediate Post."""
        panama = _panama_chokepoint()
        lane_type = classify_lane_relevance_type(panama, live_event_score=9)
        self.assertIn(lane_type, {"Global strategic relevance", "Live momentum override"})
        ranked = apply_ranking_bias([_slow_burn_china(), panama])
        immediate = select_immediate_post(ranked, None)
        self.assertEqual(immediate["title"], panama["title"])
        self.assertIn("why_xintelops_fits", immediate)

    def test_c_core_region_live_crisis(self):
        """Test C — Iran-Gulf ceasefire talks become Best Immediate Post."""
        live = _live_diplomacy_signal()
        meta = compute_live_event_score(live)
        self.assertGreaterEqual(meta["live_event_score"], 8)
        ranked = apply_ranking_bias([_slow_burn_china(), live])
        immediate = select_immediate_post(ranked, None)
        self.assertEqual(immediate["title"], live["title"])

    def test_d_cross_event_synthesis_roles(self):
        """Test D — X primary-focused; LinkedIn may carry cross-event roles."""
        primary = _us_iran_diplomacy()
        secondary = _india_uae_brahmos()
        result = enrich_operator_result(
            {"scan_session": "TEST", "ranked_signals": [primary, secondary]},
        )
        immediate = result["operator_decisions"]["best_immediate_post"]
        self.assertIn("Iran", immediate["title"])
        roles = result.get("cross_event_roles") or []
        role_map = {r["title"]: r["role"] for r in roles}
        self.assertEqual(role_map.get(primary["title"]), "Primary Event")
        self.assertIn(role_map.get(secondary["title"]), {"Secondary Signal", "Background", "Watchlist"})

    def test_e_routine_nato_archived_chokepoint_wins(self):
        """Test E — Routine NATO archived; Black Sea chokepoint can win."""
        nato = _routine_nato_aid()
        black_sea = _black_sea_chokepoint()
        ranked = apply_ranking_bias([nato, black_sea])
        nato_ranked = next(s for s in ranked if s["title"] == nato["title"])
        self.assertEqual(nato_ranked.get("recommended_action"), "ARCHIVE")
        immediate = select_immediate_post(ranked, None)
        self.assertEqual(immediate["title"], black_sea["title"])

    def test_diagnostic_fields_on_ranked_signals(self):
        ranked = apply_ranking_bias([_live_diplomacy_signal()])
        sig = ranked[0]
        for field in (
            "strategic_lane_score",
            "lane_relevance_type",
            "region_actor_boost",
            "consequence_score",
            "source_confidence",
            "live_event_score",
            "freshness_class",
            "repetition_penalty",
            "final_score",
            "why_it_ranked_here",
        ):
            self.assertIn(field, sig, f"Missing diagnostic field: {field}")

    def test_strategic_lane_score_from_themes_not_region(self):
        panama = _panama_chokepoint()
        nato = _routine_nato_aid()
        self.assertGreater(compute_strategic_lane_score(panama), compute_strategic_lane_score(nato))


class LiveEventAcceptanceTests(unittest.TestCase):
    def test_c_high_momentum_event_scores_and_wins(self):
        live = _live_diplomacy_signal()
        china = _slow_burn_china()
        meta = compute_live_event_score(live)
        self.assertGreaterEqual(meta["live_event_score"], 8)

        ranked = apply_ranking_bias([china, live])
        immediate = select_immediate_post(ranked, None)
        self.assertEqual(immediate["title"], live["title"])

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
        self.assertEqual(len(merged), 2)
        self.assertTrue(any(s.get("carried_forward") for s in merged))

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
        penalty, _ = cooldown_penalty(china, rec_history)
        self.assertGreaterEqual(penalty, 40)

    def test_linkedin_window_states(self):
        result = {
            "day_of_week": "Monday",
            "date_pkt": "2026-06-22",
            "time_pkt": "09:30 PKT",
            "ranked_signals": [_slow_burn_china()],
            "linkedin_post": "LinkedIn draft ready.",
        }
        self.assertEqual(linkedin_window_state(result), "in_window")
        block = build_linkedin_block(result, [])
        self.assertEqual(block["status"], "Post now")

    def test_enrich_operator_lane_fields(self):
        result = enrich_operator_result(
            {"scan_session": "TEST", "ranked_signals": [_live_diplomacy_signal(), _slow_burn_china()]},
        )
        immediate = result["operator_decisions"]["best_immediate_post"]
        self.assertTrue(immediate.get("why_xintelops_fits"))
        self.assertTrue(immediate.get("lane_relevance_type"))


if __name__ == "__main__":
    unittest.main()
