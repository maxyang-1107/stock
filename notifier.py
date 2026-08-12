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

    # Telegram 單則訊息上限約 4096 字元,超過就分段送出。
    # 按「整行」切而非硬切字元:避免把 Markdown(粗體、[標題](連結))切成兩半,
    # 那會讓 Telegram 解析失敗回 400。單行本身超長時才退回硬切。
    max_len = 3800
    chunks = []
    current = ""
    for line in text.split("\n"):
        while len(line) > max_len:  # 極端情況:單行就超過上限
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:max_len])
            line = line[max_len:]
        candidate = line if not current else current + "\n" + line
        if len(candidate) > max_len:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    if not chunks:
        chunks = [text]

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
