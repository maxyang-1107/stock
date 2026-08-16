# -*- coding: utf-8 -*-
"""
資料來源模組
------------
負責從 Yahoo Finance (透過 yfinance) 抓股價,
以及從 Google News RSS 抓相關新聞。
"""

from datetime import datetime, timedelta

import requests
import yfinance as yf
import feedparser


def get_quote(ticker: str):
    """回傳 {price, change, pct} 或 None(抓取失敗時)"""
    try:
        t = yf.Ticker(ticker)
        info = t.fast_info
        price = info.get("last_price")
        prev_close = info.get("previous_close")
        if price is None or prev_close is None:
            return None
        change = price - prev_close
        pct = (change / prev_close) * 100 if prev_close else 0.0
        return {"price": price, "change": change, "pct": pct}
    except Exception:
        return None


def get_tw_quote(code: str):
    """台股代號自動補上 .TW 後查詢"""
    return get_quote(f"{code}.TW")


def get_news(query: str, limit: int = 3):
    """用 Google News RSS 搜尋相關新聞標題與連結"""
    url = f"https://news.google.com/rss/search?q={query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    try:
        feed = feedparser.parse(url)
        items = []
        for entry in feed.entries[:limit]:
            items.append({"title": entry.title, "link": entry.link})
        return items
    except Exception:
        return []


# ---------------------------------------------------------------------------
# 三大法人買賣超(台灣證交所 TWSE 公開資料)
# ---------------------------------------------------------------------------
# 以下欄位名稱已經用 web_fetch 實際打過一次 TWSE 的正式 API 驗證過(2026-08-14),
# 不是憑文件推測。重點修正紀錄:
#   1. TWSE 回傳的是「繁體中文」欄位名稱,之前版本誤用簡體字比對,完全抓不到資料
#   2. T86 的 selectType 要用 "ALLBUT0999"(全部,不含權證/牛熊證),不是 "ALL"
#   3. BFI82U 正確路徑是 https://www.twse.com.tw/fund/BFI82U(不是 /rwd/zh/fund/)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

# T86 三大法人買賣超日報 —— 個股欄位對照(2026-08-14 實測確認)
_T86_FOREIGN_FIELD = "外陸資買賣超股數(不含外資自營商)"
_T86_TRUST_FIELD = "投信買賣超股數"
_T86_DEALER_FIELD = "自營商買賣超股數"
_T86_TOTAL_FIELD = "三大法人買賣超股數"


def _to_int(value):
    try:
        return int(str(value).replace(",", "").strip())
    except (ValueError, TypeError):
        return 0


def get_past_week_weekdays():
    """回傳「上一個完整交易週」的週一到週五日期(datetime 物件列表)
    設計上是給每週日中午執行的排程用,所以用今天往前推 6 天當週一"""
    today = datetime.now()
    monday = today - timedelta(days=6)
    return [monday + timedelta(days=i) for i in range(5)]


def get_weekly_institutional(stock_codes, week_dates):
    """回傳 {股票代號: {"foreign":股數, "trust":股數, "dealer":股數,
    "total_inst":股數, "days_counted":有抓到資料的天數}}
    單位是「股數」(不是張數),買賣超為正代表買超,負代表賣超。

    注意:T86 只涵蓋上市(TWSE)股票,上櫃(TPEx)股票查不到資料是正常現象。
    """
    totals = {
        code: {"foreign": 0, "trust": 0, "dealer": 0, "total_inst": 0, "days_counted": 0}
        for code in stock_codes
    }

    for d in week_dates:
        date_str = d.strftime("%Y%m%d")
        try:
            resp = requests.get(
                "https://www.twse.com.tw/rwd/zh/fund/T86",
                params={"date": date_str, "selectType": "ALLBUT0999", "response": "json"},
                headers=_HEADERS,
                timeout=20,
            )
            data = resp.json()
        except Exception:
            continue

        if data.get("stat") != "OK" or not data.get("data"):
            continue

        fields = data.get("fields", [])
        # 用「精確欄位名稱」查索引,格式對不上時會回傳 None 並優雅跳過,不會誤植錯誤數字
        field_index = {name: idx for idx, name in enumerate(fields)}
        foreign_idx = field_index.get(_T86_FOREIGN_FIELD)
        trust_idx = field_index.get(_T86_TRUST_FIELD)
        dealer_idx = field_index.get(_T86_DEALER_FIELD)
        total_idx = field_index.get(_T86_TOTAL_FIELD)

        for row in data["data"]:
            code = str(row[0]).strip()
            if code not in totals:
                continue
            if foreign_idx is not None:
                totals[code]["foreign"] += _to_int(row[foreign_idx])
            if trust_idx is not None:
                totals[code]["trust"] += _to_int(row[trust_idx])
            if dealer_idx is not None:
                totals[code]["dealer"] += _to_int(row[dealer_idx])
            if total_idx is not None:
                totals[code]["total_inst"] += _to_int(row[total_idx])
            totals[code]["days_counted"] += 1

    return totals


def get_market_institutional_week(week_dates):
    """回傳大盤整體三大法人買賣「金額」(單位:元)本週合計,
    {"foreign":..,"trust":..,"dealer":..,"total":..,"days_counted":..}

    資料來源: TWSE BFI82U(三大法人買賣金額統計表)
    回傳資料的「單位名稱」欄位固定會出現這幾個分類:
    自營商(自行買賣) / 自營商(避險) / 投信 / 外資及陸資(不含外資自營商) /
    外資自營商(僅供參考,官方說明已計入自營商金額,故不重複計入合計) / 合計
    """
    totals = {"foreign": 0, "trust": 0, "dealer": 0, "total": 0, "days_counted": 0}

    for d in week_dates:
        date_str = d.strftime("%Y%m%d")
        try:
            resp = requests.get(
                "https://www.twse.com.tw/fund/BFI82U",
                params={"response": "json", "dayDate": date_str, "type": "day"},
                headers=_HEADERS,
                timeout=20,
            )
            data = resp.json()
        except Exception:
            continue

        if data.get("stat") != "OK" or not data.get("data"):
            continue

        fields = data.get("fields", [])
        net_idx = fields.index("買賣差額") if "買賣差額" in fields else None
        if net_idx is None:
            continue

        day_hit = False
        for row in data["data"]:
            category = str(row[0])
            net_val = _to_int(row[net_idx])
            if category in ("自營商(自行買賣)", "自營商(避險)"):
                totals["dealer"] += net_val
                day_hit = True
            elif category == "投信":
                totals["trust"] += net_val
                day_hit = True
            elif category == "外資及陸資(不含外資自營商)":
                totals["foreign"] += net_val
                day_hit = True
            elif category == "合計":
                totals["total"] += net_val
                day_hit = True
            # "外資自營商" 這行刻意跳過:官方註記其金額已計入自營商,
            # 重複加總會讓「合計」對不起來(已用真實資料驗證過加總邏輯)

        if day_hit:
            totals["days_counted"] += 1

    return totals
