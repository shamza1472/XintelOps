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


_MALFORMED_LABEL = re.compile(r"^[\s:+\-/]+$")
_HAS_VERB = re.compile(r"\b(is|are|was|were|hit|struck|struck|says|said|reports|reported|confirms|may|could|adds|killed|injured|transit|struck|struck|launched|warns|announced)\b", re.I)

_TRUNCATION_ENDINGS = frozenset(
    {"of", "to", "with", "by", "for", "and", "or", "vi", "the", "a", "an", "in", "at", "on", "as", "is", "it"}
)


def fit_tweet_length(text: str, max_len: int = MAX_TWEET_LEN) -> str:
    """Shorten at word boundary; never cut mid-word."""
    t = str(text or "").strip()
    if len(t) <= max_len:
        return t
    cut = t[:max_len]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    cut = cut.rstrip(",;:- ")
    if cut and not re.search(r'[.!?…"\']$', cut):
        cut += "."
    return cut


def is_truncated_tweet(text: str) -> bool:
    """Detect partial words, unfinished phrases, and limit-slice truncation."""
    t = str(text or "").strip()
    if not t:
        return True
    if t.count("(") != t.count(")"):
        return True
    tokens = re.findall(r"\b[\w']+\b", t)
    if not tokens:
        return True
    last = tokens[-1].lower()
    if last in _TRUNCATION_ENDINGS:
        return True
    if len(last) <= 3 and not re.search(r'[.!?…"\']$', t):
        return True
    if len(t) > 30 and not re.search(r'[.!?…"\']$', t):
        if last in _TRUNCATION_ENDINGS:
            return True
    return False


def is_malformed_tweet(text: str) -> bool:
    """Detect label fragments and non-publishable tweet text."""
    t = strip_leading_number(str(text or "")).strip()
    if not t:
        return True
    if t.startswith(":") or t.startswith(";"):
        return True
    if re.match(r"^[^\w]*$", t):
        return True
    lower = t.lower()
    if "post now" in lower:
        return True
    if "xintelops angle" in lower:
        return True
    if len(t) < 20:
        return True
    if _MALFORMED_LABEL.match(t.replace(" ", "")):
        return True
    # keyword salad: mostly plus-separated fragments without verbs
    if t.count("+") >= 2 and not _HAS_VERB.search(t):
        return True
    return False


def validate_thread_tweets(tweets: list[str]) -> dict[str, Any]:
    """Remove malformed tweets or block thread if too few valid tweets remain."""
    valid: list[str] = []
    removed: list[str] = []
    for tweet in tweets:
        if is_malformed_tweet(tweet):
            removed.append(tweet)
        else:
            valid.append(tweet)
    if removed and len(valid) >= 3:
        return {"tweets": valid, "blocked": False, "block_reason": "", "removed": removed}
    if removed:
        idx = tweets.index(removed[0]) + 1 if removed else 0
        return {
            "tweets": [],
            "blocked": True,
            "block_reason": f"COPY BLOCKED — MALFORMED TWEET\nReason: Tweet {idx} is a label fragment, not publishable copy.",
            "removed": removed,
        }
    return {"tweets": valid, "blocked": False, "block_reason": "", "removed": []}


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
            tweets.append(fit_tweet_length(t))
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
    return fit_tweet_length(cleaned)


def apply_brand_footer_to_tweets(tweets: list[str]) -> list[str]:
    """Attach brand footer once to the final tweet in the thread."""
    if not tweets:
        return []
    out = list(tweets)
    footer = THREAD_BRAND_FOOTER
    last = out[-1]
    if footer in last:
        return out
    if is_truncated_tweet(last):
        out.append(footer)
        return out
    if len(last) + len(footer) + 3 <= MAX_TWEET_LEN:
        out[-1] = f"{last}\n\n{footer}"
    else:
        out.append(footer)
    return out


def apply_final_copy_safety_gate(tweets: list[str]) -> dict[str, Any]:
    """
    Final copy-paste safety gate on rendered tweet texts (after footer insertion).
    Rewrites when possible; removes failing tweets if thread stays >= 3; else blocks.
    """
    from xintelops.delivery.editorial import final_anti_ai_slop_pass

    if not tweets:
        return {
            "tweets": [],
            "blocked": True,
            "block_reason": "COPY BLOCKED — FINAL COPY QUALITY FAIL\nReason: No tweets to publish.",
            "removed": [],
        }

    processed: list[str] = []
    removed: list[dict[str, Any]] = []

    for idx, tweet in enumerate(tweets, 1):
        result = final_anti_ai_slop_pass(tweet)
        if result["blocked"]:
            removed.append({"index": idx, "tweet": tweet, "reason": result.get("block_reason") or "quality fail"})
            continue
        if result["text"].strip():
            processed.append(result["text"])

    if removed and len(processed) >= 3:
        if any("truncated" in str(r.get("reason") or "").lower() for r in removed):
            first = removed[0]
            return {
                "tweets": [],
                "blocked": True,
                "block_reason": (
                    f"COPY BLOCKED — FINAL COPY QUALITY FAIL\n"
                    f"Reason: Tweet {first['index']}: {first.get('reason') or 'truncated text'}"
                ),
                "removed": removed,
            }
        return {"tweets": processed, "blocked": False, "block_reason": "", "removed": removed}

    if removed:
        first = removed[0]
        reason = first.get("reason") or "Tweet failed final copy quality check."
        return {
            "tweets": [],
            "blocked": True,
            "block_reason": f"COPY BLOCKED — FINAL COPY QUALITY FAIL\nReason: Tweet {first['index']}: {reason}",
            "removed": removed,
        }

    footer_count = sum(1 for t in processed if THREAD_BRAND_FOOTER in t)
    if footer_count > 1:
        return {
            "tweets": [],
            "blocked": True,
            "block_reason": "COPY BLOCKED — FINAL COPY QUALITY FAIL\nReason: Brand footer appears more than once.",
            "removed": [],
        }

    return {"tweets": processed, "blocked": False, "block_reason": "", "removed": []}


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
        validation = validate_thread_tweets(tweets)
        if validation["blocked"]:
            return {
                "copy_text": "",
                "copy_type": "thread",
                "blocked": True,
                "block_reason": validation["block_reason"],
                "tweets": [],
            }
        tweets = validation["tweets"]
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
    if not single or is_malformed_tweet(single):
        return {
            "copy_text": "",
            "copy_type": "single_post",
            "blocked": True,
            "block_reason": "COPY BLOCKED — MALFORMED TWEET\nReason: Single post is a label fragment, not publishable copy.",
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
