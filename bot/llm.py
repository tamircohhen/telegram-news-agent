"""כל הקריאות ל-Claude: סינון, כתיבת פוסט וסיכום יומי."""
import json
import os
import re

import anthropic

_client = None


def client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"].strip())
    return _client


def _ask(model, system, user, max_tokens=2000):
    msg = client().messages.create(
        model=model, max_tokens=max_tokens, system=system,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")


def _json(text):
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1)
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=0)
    return json.loads(text[start:])


# ------------------------------------------------------------------ סינון
TRIAGE_SYSTEM = """You are the news desk editor of a Hebrew Telegram channel for Israeli readers.
Focus: (1) the war/conflict between Israel, Iran and the United States, (2) US news and policy that affects Israel or the Middle East,
(3) other world news that is concretely important to Israel (regional fronts, diplomacy, sanctions, energy/markets impact, aviation/travel to Israel, antisemitism incidents with wide impact).
Ignore: sports, celebrity, lifestyle, local crime abroad, opinion columns, duplicates, items with no new information.

For each candidate item return a JSON object:
- "id": the item id
- "relevant": true/false
- "importance": 1-5 (5 = major breaking development: strikes, attacks, casualties, official declarations, ceasefire; 3 = notable development; 1 = minor)
- "sensitive": true if it touches Israeli security information that may be subject to the Israeli military censor or could be operationally harmful:
   exact impact/interception locations in Israel, IDF troop movements or operational plans, names of casualties before official release, details of hostages,
   classified/leaked intelligence, unverified reports of an Israeli strike before official confirmation. Otherwise false.
- "duplicate": true if it reports the same development as one of the RECENTLY POSTED headlines with no meaningful new detail
- "cluster": a short English key; items about the same event share the same key
Return ONLY a JSON array."""


def triage(cfg, items, recent_headlines):
    lines = [f'{i["id"]} | {i["source"]} | {i["title"]} | {i["summary"][:250]}' for i in items]
    user = ("RECENTLY POSTED (last hours):\n" + ("\n".join("- " + h for h in recent_headlines) or "- none")
            + "\n\nCANDIDATES (id | source | title | summary):\n" + "\n".join(lines))
    out = _json(_ask(cfg["triage_model"], TRIAGE_SYSTEM, user, max_tokens=4000))
    return {r["id"]: r for r in out if isinstance(r, dict) and "id" in r}


# ------------------------------------------------------------------ כתיבה
WRITER_SYSTEM = """אתה עורך חדשות בכיר בערוץ Telegram בעברית, לקהל ישראלי.
כתוב בעברית רשמית, תקנית וברורה (משלב של מהדורת חדשות), בגוף שלישי, ללא סלנג, ללא אימוג'י בתוך הטקסט וללא הבעת עמדה פוליטית.

כללי אמינות – מחייבים:
- כתוב אך ורק את מה שמופיע בחומר שקיבלת. אל תמציא פרטים, מספרים, ציטוטים או שמות.
- ייחס כל טענה למקור שלה ("לפי דיווח ב-BBC", "כך מסר הבית הלבן"). דיווח של כלי תקשורת איראני רשמי סמן במפורש כ"לטענת התקשורת האיראנית".
- אם הידיעה לא אומתה, כתוב זאת ("טרם אושר רשמית").
- אל תפרסם מיקומי נפילות או יירוטים, תנועות כוחות, או שמות נפגעים שלא הותרו לפרסום. השמט פרטים כאלה.

המטרה היא שגם קורא שאינו מומחה יבין: הסבר מונחים, גופים, אנשים וראשי תיבות שמופיעים בידיעה
(למשל: IAEA, העשרת אורניום, משמרות המהפכה, CENTCOM, סנקציות משניות, וטו, החלטה 2231).

החזר JSON בלבד במבנה:
{
 "urgency": "breaking" | "update",
 "headline": "כותרת קצרה וחדה (עד 12 מילים)",
 "body": "2–4 משפטים: מה קרה, מי, מתי, לפי מי",
 "context": "1–2 משפטי רקע: למה זה חשוב לישראל / מה המשמעות (בלי ניחושים)",
 "terms": [{"term": "מונח", "explain": "הסבר קצר וברור במשפט אחד"}],
 "source_name": "שם המקור העיקרי"
}
terms: 0–3 מונחים, רק כאלה שבאמת דורשים הסבר."""


def write_post(cfg, cluster_items):
    parts = []
    for it in cluster_items:
        parts.append(f'מקור: {it["source"]}\nכותרת: {it["title"]}\nתקציר: {it["summary"]}\nקישור: {it["link"]}')
    user = "כתוב פוסט אחד על הידיעה הבאה (ייתכנו כמה מקורות לאותו אירוע):\n\n" + "\n\n---\n\n".join(parts)
    return _json(_ask(cfg["writer_model"], WRITER_SYSTEM, user, max_tokens=1500))


# ------------------------------------------------------------------ סיכום יומי
SUMMARY_SYSTEM = """אתה עורך ראשי של ערוץ חדשות בעברית לקהל ישראלי. כתוב סיכום יומי בעברית רשמית וברורה
על בסיס רשימת הידיעות שפורסמו היום בערוץ בלבד – בלי להוסיף עובדות שלא מופיעות ברשימה.
החזר JSON בלבד:
{"title": "כותרת הסיכום",
 "sections": [{"name": "שם הנושא (למשל: החזית מול איראן / ארה\\"ב / זירה מדינית)", "points": ["נקודה", "..."]}],
 "outlook": "משפט–שניים: מה כדאי לעקוב אחריו מחר (רק על סמך הידיעות)",
 "terms": [{"term": "...", "explain": "..."}]}
עד 4 נושאים, עד 4 נקודות בכל נושא, עד 3 מונחים."""


def write_summary(cfg, posted):
    lines = [f'- {p["headline"]}: {p.get("summary", "")} (מקור: {p.get("source", "")})' for p in posted]
    return _json(_ask(cfg["writer_model"], SUMMARY_SYSTEM, "הידיעות של היום:\n" + "\n".join(lines), max_tokens=2500))
