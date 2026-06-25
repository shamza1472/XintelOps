from __future__ import annotations

import json
import re
from typing import Any

THREAD_BRAND_FOOTER = "XIntelOps | Strategic signal brief"
MAX_TWEET_LEN = 280

_NUMBER_PREFIX = re.compile(
    r"^\s*(?:"
    r"\d+\s*/\s*|"  # 1/ or 2/
    r"\d+\.\s*|"  # 1.
    r"tweet\s*\d+\s*:\s*|"  # Tweet 1:
    r"\(\d+/\d+\)\s*"
    r")",
    re.IGNORECASE,
)


def parse_x_thread(raw: Any) -> list[str]:
    """Normalize x_thread to a list of tweet strings."""
    if raw is None:
        return []
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                parsed = json.loads(text)
                items = parsed if isinstance(parsed, list) else [text]
            except json.JSONDecodeError:
                items = [ln.strip() for ln in text.split("\n") if ln.strip()]
        else:
            items = [ln.strip() for ln in text.split("\n") if ln.strip()]
    else:
        items = [str(raw)]

    tweets: list[str] = []
    for item in items:
        t = str(item or "").strip()
        if not t:
            continue
        t = _NUMBER_PREFIX.sub("", t).strip()
        t = t.replace("🧵", "").strip()
        if t:
            tweets.append(t[:MAX_TWEET_LEN])
    return tweets


def strip_leading_number(text: str) -> str:
    return _NUMBER_PREFIX.sub("", str(text or "").strip()).strip()


def format_thread_for_display(tweets: list[str], *, add_brand_footer: bool = True) -> str:
    """Render numbered thread for operator email."""
    if not tweets:
        return ""
    lines = ["THREAD", ""]
    for idx, tweet in enumerate(tweets, 1):
        lines.append(f"{idx}/ {tweet[:MAX_TWEET_LEN]}")
    if add_brand_footer and tweets:
        footer = THREAD_BRAND_FOOTER
        if len(tweets[-1]) + len(footer) + 3 <= MAX_TWEET_LEN:
            lines[-1] = f"{lines[-1]}\n\n{footer}"
        else:
            lines.extend(["", footer])
    return "\n".join(lines)


def format_single_post(text: str) -> str:
    cleaned = strip_leading_number(str(text or "").strip())
    return cleaned[:MAX_TWEET_LEN]


def prepare_x_copy(result: dict[str, Any], action: str) -> dict[str, Any]:
    """
    Build normalized publishable X copy from scan result.
    Returns dict with copy_text, copy_type, blocked, block_reason, tweets.
    """
    action = str(action or "").upper()
    post_actions = {"X POST", "X THREAD", "SINGLE X POST", "SINGLE TWEET"}

    if action not in post_actions:
        return {
            "copy_text": "",
            "copy_type": "none",
            "blocked": False,
            "block_reason": "",
            "tweets": [],
        }

    if action == "X THREAD":
        tweets = parse_x_thread(result.get("x_thread"))
        if not tweets and result.get("x_post"):
            tweets = [format_single_post(str(result.get("x_post")))]
        if not tweets:
            return {
                "copy_text": "",
                "copy_type": "thread",
                "blocked": True,
                "block_reason": "Operator action requires publishable X copy, but no X copy was available.",
                "tweets": [],
            }
        copy_text = format_thread_for_display(tweets, add_brand_footer=True)
        return {
            "copy_text": copy_text,
            "copy_type": "thread",
            "blocked": False,
            "block_reason": "",
            "tweets": tweets,
        }

    single = format_single_post(str(result.get("x_post") or ""))
    if not single:
        tweets = parse_x_thread(result.get("x_thread"))
        if tweets:
            single = tweets[0]
    if not single:
        return {
            "copy_text": "",
            "copy_type": "single_post",
            "blocked": True,
            "block_reason": "Operator action requires publishable X copy, but no X copy was available.",
            "tweets": [],
        }
    return {
        "copy_text": single,
        "copy_type": "single_post",
        "blocked": False,
        "block_reason": "",
        "tweets": [single],
    }


def apply_x_copy_to_result(result: dict[str, Any], action: str) -> dict[str, Any]:
    """Normalize thread in result and attach prepared copy metadata."""
    tweets = parse_x_thread(result.get("x_thread"))
    if tweets:
        result["x_thread"] = tweets
    meta = prepare_x_copy(result, action)
    result["_x_copy_meta"] = meta
    if not meta["blocked"]:
        if meta["copy_type"] == "thread":
            result["x_thread"] = meta["tweets"]
        elif meta["copy_type"] == "single_post":
            result["x_post"] = meta["tweets"][0]
    return result
