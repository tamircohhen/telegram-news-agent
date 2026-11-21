"""הרצה אחת של הסוכן: אישורים ממתינים ← איסוף ← סינון ← כתיבה ← פרסום.

python -m bot.main            הרצה אחת (כך זה רץ ב-GitHub Actions)
python -m bot.main --loop 90  הרצה רציפה כל 90 שניות (לשרת VPS)
python -m bot.main --dry-run  בלי לשלוח ל-Telegram – רק הדפסה למסך
"""
import argparse
import logging
import os
import sys
import time
import uuid

import yaml

from . import feeds, formatter, llm, state, telegram

log = logging.getLogger("agent")
ROOT = os.path.join(os.path.dirname(__file__), "..")


def load_config():
    with open(os.path.join(ROOT, "config.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def env(name):
    v = os.environ.get(name, "").strip()
    if not v:
        sys.exit(f"חסר משתנה סביבה: {name}")
    return v


# ---------------------------------------------------------------- אישורים
def process_approvals(s, channel, admin, dry):
    if dry:
        return
    updates = telegram.get_updates(s["tg_offset"])
    for u in updates:
        s["tg_offset"] = u["update_id"] + 1
        cb = u.get("callback_query")
        if not cb:
            continue
        if str(cb["from"]["id"]) != admin:          # רק המנהל רשאי לאשר
            telegram.answer_callback(cb["id"], "אין הרשאה")
            continue
        action, _, pid = (cb.get("data") or "").partition(":")
        item = s["pending"].pop(pid, None)
        msg = cb.get("message", {})
        if not item:
            telegram.answer_callback(cb["id"], "הפריט כבר טופל או פג תוקפו")
            continue
        if action == "ok":
            res = telegram.send(channel, item["text"], item.get("link"), item.get("preview", True))
            s["posted"].append({**item["meta"], "ts": time.time(), "message_id": res["message_id"]})
            telegram.answer_callback(cb["id"], "פורסם ✅")
            telegram.edit_text(admin, msg.get("message_id"), "✅ <b>פורסם בערוץ</b>\n\n" + item["text"])
        else:
            telegram.answer_callback(cb["id"], "נדחה")
            telegram.edit_text(admin, msg.get("message_id"), "❌ <b>נדחה</b>\n\n" + item["text"])


# ---------------------------------------------------------------- בחירה
def pick_clusters(cfg, items, verdicts):
    clusters = {}
    for it in items:
        v = verdicts.get(it["id"])
        if not v or not v.get("relevant", True) or v.get("duplicate"):
            continue
        if int(v.get("importance", 0)) < cfg["min_importance"]:
            continue
        key = v.get("cluster") or it["id"]
        c = clusters.setdefault(key, {"items": [], "importance": 0, "sensitive": False, "ts": it["ts"]})
        c["items"].append(it)
        c["importance"] = max(c["importance"], int(v["importance"]))
        c["sensitive"] = c["sensitive"] or bool(v.get("sensitive"))
        c["ts"] = min(c["ts"], it["ts"])
    ranked = sorted(clusters.values(), key=lambda c: (-c["importance"], c["ts"]))
    return ranked


def best_link(cluster):
    direct = [i for i in cluster["items"] if not i["aggregator"]] or cluster["items"]
    return max(direct, key=lambda i: i["weight"])


# ---------------------------------------------------------------- הרצה
def run_once(cfg, dry=False):
    channel = os.environ.get("TELEGRAM_CHANNEL_ID", "@dry-run") if dry else env("TELEGRAM_CHANNEL_ID")
    admin = os.environ.get("ADMIN_CHAT_ID", "0") if dry else env("ADMIN_CHAT_ID")
    s = state.load()

    process_approvals(s, channel, admin, dry)
    state.save(s)  # שומרים מיד, כדי שאישור לא יפורסם פעמיים אם משהו ייכשל בהמשך

    items, errors = feeds.fetch_all(cfg["feeds"])
    for e in errors:
        log.warning("מקור לא זמין: %s", e)

    window = cfg["max_item_age_minutes"] if s["initialized"] else cfg["first_run_window_minutes"]
    cutoff = time.time() - window * 60
    fresh = [i for i in items if i["id"] not in s["seen"] and i["ts"] >= cutoff]
    # מה שישן מדי – מסומן כנראה כדי לא לבדוק שוב
    for i in items:
        if i["ts"] < cutoff:
            s["seen"].setdefault(i["id"], time.time())
    log.info("נאספו %d כתבות, %d חדשות", len(items), len(fresh))

    last_day = sum(1 for p in s["posted"] if time.time() - p["ts"] < 24 * 3600) + len(s["pending"])
    if fresh and last_day >= cfg.get("daily_post_cap", 10**6):
        log.info("הגענו לתקרה היומית (%d) – מדלגים על Claude בהרצה הזו", last_day)
        for i in fresh:
            s["seen"][i["id"]] = time.time()
        fresh = []

    if fresh:
        fresh = sorted(fresh, key=lambda i: -i["ts"])[:60]
        recent = [p["headline"] for p in s["posted"] if time.time() - p["ts"] < 6 * 3600]
        recent += [p["meta"]["headline"] for p in s["pending"].values()]
        verdicts = llm.triage(cfg, fresh, recent)
        clusters = pick_clusters(cfg, fresh, verdicts)
        chosen, overflow = clusters[: cfg["max_posts_per_run"]], clusters[cfg["max_posts_per_run"]:]
        overflow_ids = {i["id"] for c in overflow for i in c["items"]}
        for i in fresh:
            if i["id"] not in overflow_ids:     # עודפים ייבדקו שוב בהרצה הבאה
                s["seen"][i["id"]] = time.time()

        for c in chosen:
            main_item = best_link(c)
            try:
                p = llm.write_post(cfg, c["items"])
                text = formatter.post(p, main_item["link"], main_item["source"])
            except Exception as e:
                log.error("כתיבת פוסט נכשלה: %s", e)
                continue
            meta = {"headline": p["headline"], "summary": p.get("body", "")[:300],
                    "source": main_item["source"], "link": main_item["link"]}
            needs_ok = cfg["publish_mode"] == "approval" or (cfg["publish_mode"] == "hybrid" and c["sensitive"])
            preview = cfg.get("show_link_preview", True)

            if dry:
                print(("[לאישור] " if needs_ok else "[לפרסום] ") + "-" * 40 + "\n" + text + "\n")
                s["posted"].append({**meta, "ts": time.time(), "message_id": 0})
                continue
            if needs_ok:
                pid = uuid.uuid4().hex[:10]
                head = "⏳ <b>ממתין לאישורך</b> (נושא ביטחוני רגיש)\n\n" if c["sensitive"] else "⏳ <b>ממתין לאישורך</b>\n\n"
                buttons = [[{"text": "✅ פרסם", "callback_data": f"ok:{pid}"},
                            {"text": "❌ דחה", "callback_data": f"no:{pid}"}]]
                telegram.send(admin, head + text, main_item["link"], preview, buttons)
                s["pending"][pid] = {"ts": time.time(), "text": text, "link": main_item["link"],
                                     "preview": preview, "meta": meta}
            else:
                res = telegram.send(channel, text, main_item["link"], preview)
                s["posted"].append({**meta, "ts": time.time(), "message_id": res["message_id"]})
            state.save(s)
            time.sleep(1.5)  # מניעת חריגה ממגבלת הקצב של Telegram

    s["initialized"] = True
    state.save(s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", type=int, default=0, help="שניות בין הרצות (0 = הרצה אחת)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config()
    while True:
        try:
            run_once(cfg, a.dry_run)
        except Exception:
            log.exception("ההרצה נכשלה")
            if not a.loop:
                raise
        if not a.loop:
            break
        time.sleep(a.loop)


if __name__ == "__main__":
    main()
