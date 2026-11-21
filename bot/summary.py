"""סיכום יומי בערב: python -m bot.summary [--dry-run] [--force]"""
import argparse
import logging
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from . import formatter, llm, state, telegram
from .main import load_config

TZ = ZoneInfo("Asia/Jerusalem")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="לשלוח גם אם כבר נשלח סיכום היום")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO)
    cfg = load_config()
    if not cfg.get("daily_summary", {}).get("enabled", True):
        return
    s = state.load()
    today = datetime.now(TZ).strftime("%d.%m.%Y")
    if s["last_summary_date"] == today and not a.force:
        logging.info("הסיכום להיום כבר נשלח")
        return
    posted = [p for p in s["posted"] if time.time() - p["ts"] < 24 * 3600]
    if len(posted) < 3:
        logging.info("מעט מדי ידיעות היום לסיכום")
        return
    text = formatter.summary(llm.write_summary(cfg, posted[-60:]), cfg.get("channel_name", ""), today)
    if a.dry_run:
        print(text)
    else:
        telegram.send(os.environ["TELEGRAM_CHANNEL_ID"], text, show_preview=False)
    s["last_summary_date"] = today
    state.save(s)


if __name__ == "__main__":
    main()
