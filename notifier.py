# -*- coding: utf-8 -*-
"""
Telegram 推播模組
------------------
從環境變數讀取 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID,
這兩個值要設定在 GitHub repo 的 Secrets 裡,不要寫死在程式碼中。
"""

import os
import requests


def send_telegram_message(text: str, parse_mode: str = "Markdown"):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError(
            "找不到 TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID 環境變數,"
            "請確認 GitHub Secrets 是否已設定。"
        )

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    # Telegram 單則訊息上限約 4096 字元,超過就分段送出
    max_len = 3800
    chunks = [text[i:i + max_len] for i in range(0, len(text), max_len)] or [text]

    for chunk in chunks:
        resp = requests.post(
            url,
            data={
                "chat_id": chat_id,
                "text": chunk,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            },
            timeout=15,
        )
        if resp.status_code != 200:
            print(f"[警告] Telegram 傳送失敗: {resp.status_code} {resp.text}")
        resp.raise_for_status()
