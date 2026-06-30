"""Acceptance tests for XIntelOps delivery-layer patch."""
from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone

from xintelops.delivery.cadence import enrich_result
from xintelops.delivery.crisis_tier import POSTING_TIERS, classify_scan_tier, classify_signal_tier
from xintelops.delivery.editorial import anti_hallucination_pass, anti_slop_editorial_pass, editorial_pipeline
from xintelops.delivery.email_builder import build_email_html
from xintelops.delivery.linkedin_synthesis import build_linkedin_block
from xintelops.delivery.operator import enrich_operator_result
from xintelops.delivery.queue import resolve_queue
from xintelops.delivery.signal_display import cluster_signals, prepare_top_signals
from xintelops.delivery.source_roles import ROLE_PRIMARY, ROLE_SECONDARY, build_role_separated_package
from xintelops.delivery.x_copy import format_thread_for_display, parse_x_thread, prepare_x_copy

PKT = timezone(timedelta(hours=5))


def _base_result(**overrides) -> dict:
    scan_time = datetime(2026, 6, 19, 10, 30, tzinfo=PKT)
    result = {
        "scan_session": "SCAN-TEST-001",
        "date_pkt": scan_time.strftime("%Y-%m-%d"),
        "time_pkt": scan_time.strftime("%H:%M PKT"),
        "day_of_week": "Thursday",
        "ranked_signals": [],
        "operator_decisions": {},
        "source_citations": [],
        "runtime": {"runtime_label": "test"},
    }
    result.update(overrides)
    return result


def _thread_signal(title: str = "PLA Fujian carrier transit") -> dict:
    return {
        "title": title,
        "source": "Reuters",
        "url": "https://reuters.com/fujian",
        "region": "Indo-Pacific",
        "domain": "maritime",
        "why_hamza_should_care": "Carrier transit adds pressure around Taiwan Strait logistics.",
        "recommended_action": "X THREAD",
        "confidence": "HIGH",
        "freshness_class": "LIVE",
        "live_event_score": 8,
        "consequence_score": 8,
        "update_velocity": 7,
        "scores": {"live_momentum": 8},
        "rank_score": 85,
    }


class TestXCopyInOperatorBlock(unittest.TestCase):
    def test_x_thread_renders_copy_inside_operator_block(self):
        thread = [
            "PLA Fujian transited the Taiwan Strait during drills according to regional reporting.",
            "The transit adds maritime pressure but does not prove escalation preparation.",
            "Watch insurance and routing signals in the next scan window for changes.",
            "Corridor risk remains elevated while drills continue near the strait.",
        ]
        result = _base_result(
            x_thread=thread,
            operator_decisions={
                "one_signal_to_post": {"title": "PLA Fujian carrier transit", "action": "X THREAD", "why": "Top live signal"},
                "best_immediate_post": {"title": "PLA Fujian carrier transit", "action": "X THREAD"},
            },
            ranked_signals=[_thread_signal()],
        )
        result = resolve_queue(result, None)
        x = result["operator_block"]["x"]
        html = build_email_html(result)
        self.assertIn("COPY THIS - THREAD", html)
        self.assertIn("1/ PLA Fujian", x.get("thread_copy") or x.get("draft", ""))
        self.assertFalse(x["copy_blocked"])

    def test_x_post_renders_single_post_inside_operator_block(self):
        result = _base_result(
            x_post="Fujian transit adds pressure around Taiwan; sources do not prove escalation prep.",
            operator_decisions={
                "one_signal_to_post": {"title": "PLA Fujian carrier transit", "action": "X POST", "why": "Immediate"},
                "best_immediate_post": {"title": "PLA Fujian carrier transit", "action": "X POST"},
            },
            ranked_signals=[{**_thread_signal(), "recommended_action": "X POST"}],
        )
        result = resolve_queue(result, None)
        x = result["operator_block"]["x"]
        draft = x.get("single_copy") or x.get("draft") or ""
        self.assertNotIn("THREAD", draft.split("\n")[0])
        self.assertIn("Fujian", draft)
        self.assertIn("COPY THIS - SINGLE TWEET", build_email_html(result))

    def test_missing_x_copy_uses_fact_fallback_or_blocks(self):
        result = _base_result(
            operator_decisions={
                "one_signal_to_post": {"title": "Missing copy signal", "action": "X THREAD", "why": "No draft"},
                "best_immediate_post": {"title": "Missing copy signal", "action": "X THREAD"},
            },
            ranked_signals=[{
                **_thread_signal("Missing copy signal"),
                "why_hamza_should_care": "",
                "live_event_score": 0,
            }],
            x_post="If you're only counting sorties, you're late. the corridor risk repricing is the signal.",
            x_thread=["Watch next: (1) bad", "The under-covered this isn't", "→ arrow copy"],
        )
        result = resolve_queue(result, None)
        html = build_email_html(result)
        self.assertNotIn("COPY NOT GENERATED", html)
        x = result["operator_block"]["x"]
        self.assertFalse(x["copy_blocked"])
        self.assertIn("COPY THIS - SINGLE TWEET", html)
        self.assertIn("Missing copy signal", x.get("single_copy") or x.get("draft") or "")


class TestThreadNormalization(unittest.TestCase):
    def test_thread_json_string_parses(self):
        raw = json.dumps(["Tweet one about Hormuz.", "Tweet two about insurance."])
        tweets = parse_x_thread(raw)
        self.assertEqual(len(tweets), 2)
        self.assertIn("Hormuz", tweets[0])

    def test_double_numbered_tweets_normalized(self):
        raw = ['2/ 1/ Iran ceasefire track is not over.', "3/ Markets may reprice corridor risk."]
        tweets = parse_x_thread(raw)
        rendered = format_thread_for_display(tweets, add_brand_footer=False)
        self.assertIn("1/ Iran ceasefire", rendered)
        self.assertNotIn("2/ 1/", rendered)


class TestActiveEventsAndTopSignals(unittest.TestCase):
    def test_active_events_survive_finalize_enrich_path(self):
        active = [
            {
                "event_id": "evt_abc",
                "normalized_event_key": "hormuz_key",
                "title": "Hormuz transit disruption",
                "active_until": (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat(),
                "live_event_score": 9,
                "previous_action": "MONITOR",
                "last_seen_at": "2026-06-19T05:00:00+00:00",
            }
        ]
        signal = _thread_signal("India-UAE BrahMos talks")
        result = _base_result(ranked_signals=[signal])
        result = enrich_operator_result(result, active_events=active)
        self.assertTrue(result["active_live_events"]["events"])
        self.assertNotIn("No active live events carried", str(result["active_live_events"]["summary"]))

        result["_enriched"] = True
        result = enrich_result(dict(result), active_events=active)
        self.assertTrue(result["active_live_events"]["events"])

    def test_top_signals_capped_at_ten(self):
        signals = [
            {**_thread_signal(f"Signal {i}"), "rank_score": 100 - i, "normalized_event_key": f"key-{i}"}
            for i in range(15)
        ]
        prep = prepare_top_signals(_base_result(ranked_signals=signals))
        self.assertLessEqual(prep["shown"], 10)
        self.assertEqual(prep["total_eligible"], 15)
        self.assertTrue(prep["truncated"])

    def test_near_duplicate_signals_cluster(self):
        a = _thread_signal("Hormuz shipping insurance warnings rise")
        b = _thread_signal("Hormuz insurance warnings rise for shipping")
        from xintelops.delivery.live_events import normalize_event_key

        a["normalized_event_key"] = normalize_event_key(a["title"], a["url"])
        b["normalized_event_key"] = a["normalized_event_key"]
        clustered = cluster_signals([a, b])
        self.assertEqual(len(clustered), 1)
        self.assertGreaterEqual(clustered[0].get("cluster_count", 1), 2)


class TestSourceRolesAndLinkedIn(unittest.TestCase):
    def test_secondary_source_not_in_primary_package(self):
        primary = _thread_signal("PLA Fujian carrier transit")
        secondary = {
            **_thread_signal("India-UAE BrahMos talks"),
            "url": "https://reuters.com/brahmos",
            "source": "Reuters",
        }
        result = _base_result(
            ranked_signals=[primary, secondary],
            operator_decisions={
                "one_signal_to_post": {"title": primary["title"], "action": "X THREAD"},
                "best_immediate_post": {"title": primary["title"], "action": "X THREAD"},
            },
            cross_event_roles=[
                {
                    "title": primary["title"],
                    "role": ROLE_PRIMARY,
                    "source_package": [{"url": primary["url"], "name": "Reuters"}],
                },
                {
                    "title": secondary["title"],
                    "role": ROLE_SECONDARY,
                    "source_package": [{"url": secondary["url"], "name": "Reuters"}],
                },
            ],
            source_citations=[
                {"name": "Reuters", "url": primary["url"], "why_supports": f"Primary source for: {primary['title']}"},
                {"name": "Reuters", "url": secondary["url"], "why_supports": f"Secondary signal: {secondary['title']}"},
            ],
        )
        buckets = build_role_separated_package(result, primary["title"])
        primary_urls = {s["url"] for s in buckets[ROLE_PRIMARY]}
        secondary_urls = {s["url"] for s in buckets[ROLE_SECONDARY]}
        self.assertIn(primary["url"], primary_urls)
        self.assertIn(secondary["url"], secondary_urls)
        self.assertNotIn(secondary["url"], primary_urls)

    def test_thursday_non_crisis_linkedin_does_not_post(self):
        routine_sig = {
            **_thread_signal(),
            "live_event_score": 5,
            "consequence_score": 5,
            "update_velocity": 4,
            "freshness_class": "DEVELOPING",
            "scores": {"live_momentum": 4},
        }
        result = _base_result(
            day_of_week="Thursday",
            time_pkt="10:00 PKT",
            ranked_signals=[routine_sig],
            operator_decisions={
                "best_immediate_post": {"title": routine_sig["title"]},
                "one_signal_to_post": {"title": routine_sig["title"], "action": "X POST"},
            },
            linkedin_post="LinkedIn article about Fujian transit and corridor risk.",
        )
        result["crisis_tier_meta"] = classify_scan_tier(result)
        block = build_linkedin_block(result, [])
        self.assertEqual(block["status"], "Not scheduled today")
        self.assertTrue(block["copy_this"])
        self.assertEqual(block["action"], "Hold until next LinkedIn window")

    def test_thursday_crisis_linkedin_shows_copy(self):
        crisis_sig = {
            **_thread_signal(),
            "consequence_score": 9,
            "live_event_score": 9,
            "update_velocity": 9,
            "freshness_class": "BREAKING",
            "scores": {"live_momentum": 9},
            "new_information_detected": True,
        }
        result = _base_result(
            day_of_week="Thursday",
            time_pkt="10:00 PKT",
            ranked_signals=[crisis_sig],
            operator_decisions={
                "best_immediate_post": {"title": crisis_sig["title"]},
                "one_signal_to_post": {"title": crisis_sig["title"], "action": "X THREAD"},
            },
            linkedin_post="Crisis LinkedIn copy on Fujian transit with corridor implications.",
        )
        result["crisis_tier_meta"] = classify_scan_tier(result)
        self.assertIn(result["crisis_tier_meta"]["immediate_tier"], POSTING_TIERS)
        block = build_linkedin_block(result, [])
        self.assertEqual(block["status"], "Crisis exception")
        self.assertTrue(block["copy_this"])


class TestEditorialAndBrand(unittest.TestCase):
    def test_anti_slop_removes_phrases(self):
        text = "Chokepoint math is changing fast. Generic headline noise in the XIntelOps lane."
        out = anti_slop_editorial_pass(text)
        lower = out["text"].lower()
        self.assertNotIn("chokepoint math is changing fast", lower)
        self.assertNotIn("generic headline noise", lower)
        self.assertNotIn("xintelops lane", lower)

    def test_brand_footer_once_at_thread_end(self):
        tweets = ["First tweet.", "Second tweet.", "Third tweet."]
        rendered = format_thread_for_display(tweets, add_brand_footer=True)
        self.assertEqual(rendered.count("XIntelOps"), 1)
        self.assertTrue(rendered.strip().endswith("brief") or "XIntelOps" in rendered.split("\n")[-1])

    def test_single_x_posts_do_not_auto_mention_brand(self):
        meta = prepare_x_copy(_base_result(x_post="Transit adds pressure; evidence does not prove escalation."), "X POST")
        self.assertNotIn("XIntelOps", meta["copy_text"])

    def test_unsupported_claims_blocked_or_rewritten(self):
        text = "China is preparing to escalate around Taiwan. Markets will reprice Hormuz risk immediately."
        out = anti_hallucination_pass(text, sources=[{"url": "https://reuters.com/a", "name": "Reuters"}])
        lowered = out["text"].lower()
        self.assertTrue(any(w in lowered for w in ("may", "could", "suggests", "points to")))

    def test_analytical_inference_uses_cautious_wording(self):
        text = "The Gulf is preparing for war."
        out = editorial_pipeline(text, [{"url": "https://example.com", "name": "Source"}])
        lowered = out["text"].lower()
        self.assertTrue(any(w in lowered for w in ("may", "could", "points to", "hedging", "suggests")))

    def test_hallucination_risk_score_included(self):
        out = editorial_pipeline("Reuters reports transit delays near Hormuz.", [{"url": "https://reuters.com/x", "name": "Reuters"}])
        self.assertIn("hallucination_risk", out["scores"])


class TestEmailIntegration(unittest.TestCase):
    def test_email_shows_copy_source_roles_and_max_ten_signals(self):
        thread = [
            "Iran corridor signal one with verified source detail from the strait.",
            "Insurance repricing may follow if transit delays widen near Hormuz.",
            "Watch routing and Gulf basing posture in the next scan window.",
            "Fourth tweet adds consequence detail for operator monitoring only.",
        ]
        titles = [
            "PLA Fujian carrier transit through Taiwan Strait",
            "India-UAE BrahMos procurement talks advance",
            "Hormuz shipping insurance premiums jump",
            "Panama Canal drought transit limits",
            "Black Sea grain corridor insurance shift",
            "Red Sea rerouting adds Suez delay costs",
            "NATO Baltic air policing rotation expands",
            "Japan MSDF submarine deployment schedule",
            "UAE energy hedge contracts with Asian buyers",
            "Turkey S-400 maintenance dispute with Russia",
            "South China Sea reef resupply incident",
            "EU sanctions package on dual-use electronics",
        ]
        signals = [
            {
                **_thread_signal(title),
                "rank_score": 90 - i,
                "normalized_event_key": f"unique-key-{i}",
                "url": f"https://reuters.com/signal-{i}",
            }
            for i, title in enumerate(titles)
        ]
        primary = signals[0]
        primary["new_information_detected"] = True
        result = _base_result(
            x_thread=thread,
            ranked_signals=signals,
            operator_decisions={
                "one_signal_to_post": {"title": primary["title"], "action": "X THREAD", "why": "Top ranked"},
                "best_immediate_post": {"title": primary["title"], "action": "X THREAD"},
            },
            source_citations=[
                {"name": "Reuters", "url": primary["url"], "why_supports": f"Primary source for: {primary['title']}"},
            ],
        )
        result = enrich_result(result)
        html = build_email_html(result)
        self.assertIn("COPY THIS", html)
        self.assertIn("SOURCE PACKAGE", html)
        self.assertIn("Top Signals Today", html)
        self.assertIn("Showing top 10 of 12", html)
        self.assertLessEqual(len(result["top_signals_display"]["entries"]), 10)


class TestCrisisTiering(unittest.TestCase):
    def test_high_live_without_material_change_is_monitor(self):
        sig = {**_thread_signal(), "carried_forward": True, "new_information_detected": False}
        tier = classify_signal_tier(sig, material_change=False)
        self.assertEqual(tier, "MONITOR")


class TestRuntimeFooter(unittest.TestCase):
    def test_runtime_footer_shows_actual_commit(self):
        from xintelops.runtime_metadata import attach_runtime_metadata, get_runtime_metadata

        meta = get_runtime_metadata()
        self.assertTrue(meta.get("runtime_commit_short"))
        self.assertIn("@", meta.get("runtime_label", ""))

        result = attach_runtime_metadata(_base_result())
        self.assertIn("runtime", result)
        self.assertEqual(result["runtime"]["runtime_commit_short"], meta["runtime_commit_short"])


class TestLinkedInNoContradiction(unittest.TestCase):
    def test_linkedin_decision_and_copy_do_not_contradict(self):
        routine_sig = {
            **_thread_signal(),
            "live_event_score": 5,
            "consequence_score": 5,
            "update_velocity": 4,
            "scores": {"live_momentum": 4},
        }
        result = _base_result(
            day_of_week="Thursday",
            time_pkt="22:29 PKT",
            ranked_signals=[routine_sig],
            linkedin_post="No LinkedIn post today (Thursday). Next window: Friday 09:00–11:00 PKT.",
        )
        result["crisis_tier_meta"] = classify_scan_tier(result)
        block = build_linkedin_block(result, [])
        self.assertTrue(block.get("copy_this"))
        self.assertNotIn("No LinkedIn post today", block.get("copy_this", ""))
        self.assertEqual(block["action"], "Hold until next LinkedIn window")


if __name__ == "__main__":
    unittest.main()
