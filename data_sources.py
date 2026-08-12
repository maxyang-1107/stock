# -*- coding: utf-8 -*-
"""
資料來源模組
------------
負責從 Yahoo Finance (透過 yfinance) 抓股價,
以及從 Google News RSS 抓相關新聞。
"""

import datetime

import yfinance as yf
import feedparser
import requests

# 抓法人資料時共用的 header,加 User-Agent 避免被證交所/櫃買擋掉
_HTTP_HEADERS = {"User-Agent": "Mozilla/5.0"}

# 模組層級快取:一次執行只抓一次法人資料(避免每檔股票都打 API)
_inst_cache = None


def get_quote(ticker: str):
    """回傳 {price, change, pct} 或 None(抓取失敗時)"""
    try:
        t = yf.Ticker(ticker)
        info = t.fast_info
        # 用屬性存取而非 .get():不同 yfinance 版本 fast_info 內部 key 命名
        # 可能是駝峰式 (lastPrice),.get('last_price') 會對不上而回傳 None。
        price = info.last_price
        prev_close = info.previous_close
        if price is None or prev_close is None:
            return None
        change = price - prev_close
        pct = (change / prev_close) * 100 if prev_close else 0.0
        return {"price": price, "change": change, "pct": pct}
    except Exception:
        return None


def get_tw_quote(code: str):
    """台股代號查詢。先試 .TW(上市),抓不到再 fallback .TWO(上櫃)。"""
    q = get_quote(f"{code}.TW")
    if q is None:
        q = get_quote(f"{code}.TWO")
    return q


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


def _to_int(s):
    """把 '1,234' / '-56' / '' 轉成 int,失敗回 None"""
    s = (s or "").replace(",", "").strip()
    try:
        return int(s)
    except (ValueError, TypeError):
        return None


def _to_lots(shares):
    """股數 -> 張(1張=1000股),四捨五入。None 就原樣回 None"""
    return None if shares is None else round(shares / 1000)


def _fetch_twse_institutional(result):
    """證交所 T86:上市股票三大法人買賣超。今天往回試最多 6 天以避開假日/未出表。"""
    for back in range(0, 6):
        date = (datetime.date.today() - datetime.timedelta(days=back)).strftime("%Y%m%d")
        url = (
            "https://www.twse.com.tw/rwd/zh/fund/T86"
            f"?date={date}&selectType=ALL&response=json"
        )
        resp = requests.get(url, timeout=20, headers=_HTTP_HEADERS)
        data = resp.json()
        if data.get("stat") != "OK" or not data.get("data"):
            continue
        fields = data["fields"]
        i_foreign = fields.index("外陸資買賣超股數(不含外資自營商)")
        i_trust = fields.index("投信買賣超股數")
        for row in data["data"]:
            code = row[0].strip()
            result[code] = {
                "foreign": _to_lots(_to_int(row[i_foreign])),
                "trust": _to_lots(_to_int(row[i_trust])),
            }
        return


def _fetch_tpex_institutional(result):
    """櫃買 OpenAPI:上櫃股票三大法人買賣明細。欄位名有不一致空格,先正規化再取。"""
    url = "https://www.tpex.org.tw/openapi/v1/tpex_3insti_daily_trading"
    resp = requests.get(url, timeout=25, headers=_HTTP_HEADERS)
    for row in resp.json():
        norm = {k.replace(" ", ""): v for k, v in row.items()}
        code = (row.get("SecuritiesCompanyCode") or "").strip()
        if not code:
            continue
        result[code] = {
            "foreign": _to_lots(_to_int(
                norm.get("ForeignInvestorsIncludeMainlandAreaInvestors-Difference"))),
            "trust": _to_lots(_to_int(
                norm.get("SecuritiesInvestmentTrustCompanies-Difference"))),
        }


def get_tw_institutional():
    """
    回傳 {代號: {"foreign": 外資買賣超張數, "trust": 投信買賣超張數}}。
    一次執行只抓一次(模組層級快取)。任一來源失敗就略過該來源,
    整體失敗回傳已取得的部分(最差是空 dict),確保推播不會因此中斷。
    """
    global _inst_cache
    if _inst_cache is not None:
        return _inst_cache

    result = {}
    for fetch in (_fetch_twse_institutional, _fetch_tpex_institutional):
        try:
            fetch(result)
        except Exception:
            pass  # 單一來源失敗不影響另一來源與整體推播

    _inst_cache = result
    return result
