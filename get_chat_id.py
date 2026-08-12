# -*- coding: utf-8 -*-
"""
查 Chat ID 小工具
------------------
申請完 Bot、並且在跟 Bot 的對話視窗傳過任意一句話之後,
執行這支程式就會自動幫你把 chat id 印出來。

用法:
    TELEGRAM_BOT_TOKEN=你的token python get_chat_id.py

或先 export 再執行:
    export TELEGRAM_BOT_TOKEN=你的token
    python get_chat_id.py
"""

import os
import sys
import requests


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("請先設定環境變數 TELEGRAM_BOT_TOKEN,例如:")
        print("  export TELEGRAM_BOT_TOKEN=123456789:AAxxxx")
        sys.exit(1)

    url = f"https://api.telegram.org/bot{token}/getUpdates"
    resp = requests.get(url, timeout=15)
    data = resp.json()

    if not data.get("ok"):
        print("Telegram 回傳錯誤,請確認 Token 是否正確:")
        print(data)
        sys.exit(1)

    results = data.get("result", [])
    if not results:
        print("目前查不到任何訊息。請先在 Telegram 跟你的 Bot 傳一句話(例如「hi」),")
        print("再重新執行這支程式。")
        sys.exit(1)

    seen = {}
    for item in results:
        msg = item.get("message") or item.get("edited_message") or {}
        chat = msg.get("chat") or {}
        chat_id = chat.get("id")
        if chat_id is not None and chat_id not in seen:
            name = chat.get("title") or chat.get("username") or chat.get("first_name") or ""
            seen[chat_id] = name

    print("找到以下 chat id:")
    for chat_id, name in seen.items():
        print(f"  TELEGRAM_CHAT_ID = {chat_id}    ({name})")


if __name__ == "__main__":
    main()
