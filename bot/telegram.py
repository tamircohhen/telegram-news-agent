"""עטיפה דקה ל-Telegram Bot API."""
import os

import requests

API = "https://api.telegram.org/bot{token}/{method}"


class TelegramError(RuntimeError):
    pass


def call(method, **params):
    url = API.format(token=os.environ["TELEGRAM_BOT_TOKEN"], method=method)
    r = requests.post(url, json=params, timeout=30)
    data = r.json()
    if not data.get("ok"):
        raise TelegramError(f"{method}: {data.get('description')}")
    return data["result"]


def send(chat_id, text, link=None, show_preview=True, buttons=None):
    params = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if link and show_preview:
        # תצוגה מקדימה גדולה של הכתבה (כולל התמונה הראשית שלה) מעל הטקסט
        params["link_preview_options"] = {"url": link, "prefer_large_media": True, "show_above_text": True}
    else:
        params["link_preview_options"] = {"is_disabled": True}
    if buttons:
        params["reply_markup"] = {"inline_keyboard": buttons}
    try:
        return call("sendMessage", **params)
    except TelegramError:
        if link and show_preview:  # אם התצוגה המקדימה נכשלה – שולחים בלעדיה
            params["link_preview_options"] = {"is_disabled": True}
            return call("sendMessage", **params)
        raise


def get_updates(offset):
    return call("getUpdates", offset=offset, timeout=0, allowed_updates=["callback_query", "message"])


def answer_callback(cb_id, text):
    try:
        call("answerCallbackQuery", callback_query_id=cb_id, text=text)
    except TelegramError:
        pass  # קריאה ישנה מדי – לא קריטי


def edit_text(chat_id, message_id, text):
    try:
        call("editMessageText", chat_id=chat_id, message_id=message_id, text=text,
             parse_mode="HTML", link_preview_options={"is_disabled": True})
    except TelegramError:
        pass
