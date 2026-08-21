# -*- coding: utf-8 -*-
"""
資料來源模組
------------
台股股價:改用 TWSE 官方「每日收盤行情」API(不再用 yfinance),
         因為 Yahoo Finance 近年對雲端/GitHub Actions 的 IP 封鎖越來越嚴重,
         2026-08-20 實測已出現整批「資料取得失敗」,改用證交所自己的資料源更穩定。
美股/日股/韓股:仍使用 yfinance(目前沒有同樣好用、免費、涵蓋國際市場的替代來源),
         但加上重試與延遲,降低被 Yahoo 判定為異常流量的機率。
新聞:從 Google News RSS 抓相關新聞。
"""

import random
import time
from datetime import datetime, timedelta

import requests
import yfinance as yf
import feedparser

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

# ---------------------------------------------------------------------------
# 台股:TWSE 官方「每日收盤行情」(MI_INDEX),取代 yfinance
# ---------------------------------------------------------------------------
# 一次呼叫可以拿到當天「全部台股」的收盤價/漲跌/成交量,還有加權指數本身,
# 比逐檔呼叫 yfinance 穩定、也快得多。缺點是只有「收盤後」才有當天資料,
# 適合 22:00 之後執行的 night_tw 使用;盤中即時價不適用這支 API。

_twse_daily_cache = {}


def _twse_sign_to_multiplier(sign: str) -> int:
    sign = (sign or "").strip()
    if sign == "+":
        return 1
    if sign == "-":
        return -1
    return 0  # "X"(平盤)或空白


def _twse_to_float(value):
    try:
        return float(str(value).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def get_twse_daily_all(date_str=None):
    """抓 TWSE 當天(或指定日期 yyyyMMdd)的「每日收盤行情」,回傳:
    {"index": {"price":..,"change":..,"pct":..} 或 None,
     "stocks": {股票代號: {"price":..,"change":..,"pct":..,"volume":..}}}
    有快取,同一次程式執行內同一個日期只會真的打一次 API。
    """
    if date_str is None:
        date_str = datetime.now().strftime("%Y%m%d")

    if date_str in _twse_daily_cache:
        return _twse_daily_cache[date_str]

    result = {"index": None, "stocks": {}}

    try:
        resp = requests.get(
            "https://www.twse.com.tw/exchangeReport/MI_INDEX",
            params={"response": "json", "date": date_str, "type": "ALLBUT0999"},
            headers=_HEADERS,
            timeout=30,
        )
        data = resp.json()
    except Exception:
        _twse_daily_cache[date_str] = result
        return result

    if data.get("stat") != "OK":
        _twse_daily_cache[date_str] = result
        return result

    tables = data.get("tables") or []

    # 找出「每日收盤行情」個股表格,以及「價格指數」表格(裡面含加權指數)
    quotes_table = None
    index_table = None
    for t in tables:
        title = t.get("title", "")
        fields = t.get("fields", [])
        if quotes_table is None and "證券代號" in fields and "收盤價" in fields:
            quotes_table = t
        if index_table is None and "指數" in fields and "收盤指數" in fields:
            index_table = t

    if quotes_table:
        fields = quotes_table["fields"]
        idx = {name: i for i, name in enumerate(fields)}
        code_i = idx.get("證券代號")
        close_i = idx.get("收盤價")
        sign_i = idx.get("漲跌(+/-)")
        diff_i = idx.get("漲跌價差")
        vol_i = idx.get("成交股數")

        for row in quotes_table.get("data", []):
            if code_i is None or close_i is None:
                continue
            code = str(row[code_i]).strip()
            price = _twse_to_float(row[close_i])
            if price is None:
                continue
            diff = _twse_to_float(row[diff_i]) if diff_i is not None else None
            sign = _twse_sign_to_multiplier(row[sign_i]) if sign_i is not None else 0
            change = (diff or 0.0) * sign
            prev_close = price - change
            pct = (change / prev_close) * 100 if prev_close else 0.0
            volume = _twse_to_float(row[vol_i]) if vol_i is not None else None
            result["stocks"][code] = {
                "price": price,
                "change": change,
                "pct": pct,
                "volume": volume,
            }

    if index_table:
        fields = index_table["fields"]
        idx = {name: i for i, name in enumerate(fields)}
        name_i = idx.get("指數")
        close_i = idx.get("收盤指數")
        sign_i = idx.get("漲跌(+/-)")
        diff_i = idx.get("漲跌點數")
        pct_i = idx.get("漲跌百分比(%)")

        for row in index_table.get("data", []):
            if name_i is None or str(row[name_i]).strip() != "發行量加權股價指數":
                continue
            price = _twse_to_float(row[close_i]) if close_i is not None else None
            diff = _twse_to_float(row[diff_i]) if diff_i is not None else None
            sign = _twse_sign_to_multiplier(row[sign_i]) if sign_i is not None else 0
            pct = _twse_to_float(row[pct_i]) if pct_i is not None else None
            if price is None:
                continue
            change = (diff or 0.0) * sign
            if pct is not None:
                pct = pct * sign if sign != 0 else 0.0
            result["index"] = {"price": price, "change": change, "pct": pct or 0.0}

    _twse_daily_cache[date_str] = result
    return result


def get_tw_quote_from_twse(code: str):
    """從 TWSE 每日收盤行情拿單一股票的資料,拿不到回傳 None"""
    daily = get_twse_daily_all()
    return daily["stocks"].get(code)


def get_tw_index_from_twse():
    """從 TWSE 每日收盤行情拿加權指數,拿不到回傳 None"""
    daily = get_twse_daily_all()
    return daily["index"]


# ---------------------------------------------------------------------------
# 美股 / 日股 / 韓股:yfinance(加上簡單重試 + 隨機延遲,降低被 Yahoo 擋的機率)
# ---------------------------------------------------------------------------

def get_quote(ticker: str, retries: int = 2):
    """回傳 {price, change, pct} 或 None(抓取失敗時)"""
    for attempt in range(retries + 1):
        try:
            t = yf.Ticker(ticker)
            info = t.fast_info
            price = info.get("last_price")
            prev_close = info.get("previous_close")
            if price is None or prev_close is None:
                raise ValueError("empty price")
            change = price - prev_close
            pct = (change / prev_close) * 100 if prev_close else 0.0
            return {"price": price, "change": change, "pct": pct}
        except Exception:
            if attempt < retries:
                time.sleep(1.5 + random.uniform(0, 1.5))
                continue
            return None


def get_tw_quote(code: str):
    """台股改走 TWSE 官方每日收盤行情,不再用 yfinance"""
    return get_tw_quote_from_twse(code)


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
