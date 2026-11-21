"""בדיקת התקנה: python -m bot.check_setup
בודק את הבוט, מציג את מספר הצ'אט שלך (ADMIN_CHAT_ID), בודק את הערוץ, את מפתח Claude ואת כל המקורות."""
import os

from . import feeds, telegram
from .main import load_config


def main():
    cfg = load_config()
    print("== Telegram ==")
    if os.environ.get("TELEGRAM_BOT_TOKEN"):
        me = telegram.call("getMe")
        print(f"✅ הבוט פעיל: @{me['username']}")
        ups = telegram.call("getUpdates", timeout=0)
        chats = {(u.get("message") or {}).get("chat", {}).get("id"): (u.get("message") or {}).get("chat", {}).get("first_name")
                 for u in ups if u.get("message")}
        chats.pop(None, None)
        if chats:
            for cid, name in chats.items():
                print(f"   צ'אט פרטי שנמצא: {name} → ADMIN_CHAT_ID = {cid}")
        else:
            print("   לא נמצאו הודעות. שלח לבוט /start בצ'אט פרטי והרץ שוב כדי לגלות את ה-ADMIN_CHAT_ID שלך.")
        ch = os.environ.get("TELEGRAM_CHANNEL_ID")
        if ch:
            try:
                info = telegram.call("getChat", chat_id=ch)
                member = telegram.call("getChatMember", chat_id=ch, user_id=me["id"])
                ok = member.get("status") == "administrator" and member.get("can_post_messages", True)
                print(f"{'✅' if ok else '❌'} ערוץ: {info.get('title')} (id {info['id']}) – סטטוס הבוט: {member.get('status')}")
                if not ok:
                    print("   יש להוסיף את הבוט כמנהל בערוץ עם הרשאת 'פרסום הודעות'.")
            except telegram.TelegramError as e:
                print(f"❌ ערוץ {ch}: {e}")
    else:
        print("❌ חסר TELEGRAM_BOT_TOKEN")

    print("\n== Claude ==")
    if os.environ.get("ANTHROPIC_API_KEY"):
        from . import llm
        try:
            llm._ask(cfg["triage_model"], "Reply with OK", "ping", max_tokens=5)
            print(f"✅ מפתח Claude תקין ({cfg['triage_model']})")
        except Exception as e:
            print(f"❌ Claude: {e}")
    else:
        print("❌ חסר ANTHROPIC_API_KEY")

    print("\n== מקורות ==")
    for f in cfg["feeds"]:
        _, items, err = feeds._fetch_one(f)
        print(f"{'✅' if items else '❌'} {f['name']}: {len(items)} כתבות" + (f" ({err})" if err else ""))


if __name__ == "__main__":
    main()
