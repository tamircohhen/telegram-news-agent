"""שמירת מצב בין הרצות: אילו כתבות כבר נראו, מה פורסם, ומה ממתין לאישור."""
import json
import os
import time

STATE_PATH = os.environ.get("STATE_PATH", os.path.join(os.path.dirname(__file__), "..", "state", "state.json"))

SEEN_TTL = 3 * 24 * 3600      # זוכרים כתבות שנראו 3 ימים
POSTED_TTL = 2 * 24 * 3600    # היסטוריית פרסומים ליומיים (לסיכום ולמניעת כפילויות)
PENDING_TTL = 12 * 3600       # פריט שממתין לאישור יותר מ-12 שעות פג


def load():
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            s = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        s = {}
    s.setdefault("seen", {})          # item_id -> timestamp
    s.setdefault("posted", [])        # [{ts, headline, summary, source, link, message_id}]
    s.setdefault("pending", {})       # pid -> {ts, text, link, admin_message_id}
    s.setdefault("tg_offset", 0)
    s.setdefault("last_summary_date", "")
    s.setdefault("initialized", False)
    return s


def prune(s):
    now = time.time()
    s["seen"] = {k: v for k, v in s["seen"].items() if now - v < SEEN_TTL}
    s["posted"] = [p for p in s["posted"] if now - p["ts"] < POSTED_TTL]
    s["pending"] = {k: v for k, v in s["pending"].items() if now - v["ts"] < PENDING_TTL}


def save(s):
    prune(s)
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=1)
    os.replace(tmp, STATE_PATH)
