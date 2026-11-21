"""הפיכת הפלט של Claude להודעת Telegram מעוצבת (HTML מאובטח)."""
from html import escape

MAX_LEN = 4000  # המגבלה של Telegram היא 4096


def _terms(terms):
    terms = [t for t in (terms or []) if t.get("term") and t.get("explain")]
    if not terms:
        return ""
    rows = "\n".join(f"• <b>{escape(t['term'])}</b> – {escape(t['explain'])}" for t in terms[:3])
    return f"\n\n📖 <b>מונחים</b>\n{rows}"


def post(p, link, fallback_source):
    icon = "🔴 <b>מבזק</b>" if p.get("urgency") == "breaking" else "🔵 <b>עדכון</b>"
    src = escape(p.get("source_name") or fallback_source)
    text = f"{icon} | <b>{escape(p['headline'])}</b>\n\n{escape(p['body'])}"
    if p.get("context"):
        text += f"\n\n📌 <b>המשמעות</b>\n{escape(p['context'])}"
    text += _terms(p.get("terms"))
    text += f'\n\nמקור: <a href="{escape(link, quote=True)}">{src}</a>' if link else f"\n\nמקור: {src}"
    return text[:MAX_LEN]


def summary(s, channel_name, date_str):
    text = f"🗞 <b>{escape(s.get('title') or 'סיכום היום')}</b>\n<i>{escape(date_str)}</i>"
    for sec in s.get("sections", [])[:4]:
        pts = "\n".join(f"• {escape(x)}" for x in sec.get("points", [])[:4])
        text += f"\n\n<b>{escape(sec.get('name', ''))}</b>\n{pts}"
    if s.get("outlook"):
        text += f"\n\n🔭 <b>למחר</b>\n{escape(s['outlook'])}"
    text += _terms(s.get("terms"))
    text += f"\n\n— {escape(channel_name)}"
    return text[:MAX_LEN]
