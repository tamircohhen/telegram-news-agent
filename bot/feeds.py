"""איסוף כתבות ממקורות RSS."""
import calendar
import hashlib
import html
import re
import time
from concurrent.futures import ThreadPoolExecutor

import feedparser
import requests

UA = "Mozilla/5.0 (compatible; NewsAgentBot/1.0)"
TAG_RE = re.compile(r"<[^>]+>")


def clean(text, limit=600):
    text = html.unescape(TAG_RE.sub(" ", text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def norm_title(t):
    t = re.sub(r"\s+-\s+[^-]{2,40}$", "", t)  # Google News מוסיף " - שם המקור"
    return re.sub(r"\W+", " ", t.lower()).strip()


def item_id(link, title):
    return hashlib.sha1(((link or "") + "|" + norm_title(title)).encode()).hexdigest()[:16]


def _fetch_one(feed):
    try:
        r = requests.get(feed["url"], headers={"User-Agent": UA}, timeout=15)
        r.raise_for_status()
        parsed = feedparser.parse(r.content)
    except Exception as e:  # מקור שנפל לא עוצר את השאר
        return feed, [], str(e)
    out = []
    for e in parsed.entries[:40]:
        title = clean(e.get("title", ""), 300)
        if not title:
            continue
        ts = None
        for key in ("published_parsed", "updated_parsed"):
            if e.get(key):
                ts = calendar.timegm(e[key])
                break
        link = e.get("link", "")
        out.append({
            "id": item_id(link, title),
            "title": title,
            "summary": clean(e.get("summary", "") or e.get("description", "")),
            "link": link,
            "source": feed["name"],
            "weight": feed.get("weight", 1),
            "aggregator": feed.get("aggregator", False),
            "ts": ts or time.time(),
        })
    return feed, out, None


def fetch_all(feeds):
    items, errors = [], []
    with ThreadPoolExecutor(max_workers=8) as ex:
        for feed, got, err in ex.map(_fetch_one, feeds):
            if err:
                errors.append(f"{feed['name']}: {err}")
            items.extend(got)
    # הסרת כפילויות לפי כותרת מנורמלת – עדיפות למקור ישיר ובעל משקל גבוה
    items.sort(key=lambda i: (i["aggregator"], -i["weight"]))
    by_title, uniq = set(), []
    for it in items:
        k = norm_title(it["title"])
        if k in by_title:
            continue
        by_title.add(k)
        uniq.append(it)
    return uniq, errors
