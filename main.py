# -*- coding: utf-8 -*-
"""
主程式
------
用法: python main.py [night_tw | us_morning | jpkr_morning]

night_tw     -> 台灣時間 22:00 執行,今日台股收盤總結
jpkr_morning -> 台灣時間 09:00 執行,日韓龍頭股早盤資訊(開盤後約1小時)
us_morning   -> 台灣時間 09:00 執行,美股收盤總結(前一晚)
"""

import argparse
from datetime import datetime, timezone, timedelta

import config
import data_sources as ds
import notifier

# 台灣時間(UTC+8,無日光節約)。用固定 offset 讓標題時間不受執行機器時區影響——
# GitHub Actions runner 跑在 UTC,若直接用 datetime.now() 標題會慢 8 小時。
TW_TZ = timezone(timedelta(hours=8))


def now_tw():
    return datetime.now(TW_TZ).strftime("%Y-%m-%d %H:%M")


def fmt_quote(name: str, label: str, q):
    if q is None:
        return f"• {name}({label}): 資料取得失敗"
    if q["change"] > 0:
        arrow = "🔴"
    elif q["change"] < 0:
        arrow = "🟢"
    else:
        arrow = "⚪️"
    return f"{arrow} {name} {q['price']:.2f} ({q['change']:+.2f}, {q['pct']:+.2f}%)"


def build_index_section(index_names):
    lines = ["📊 *大盤指數*"]
    for name in index_names:
        ticker = config.INDICES[name]
        q = ds.get_quote(ticker)
        lines.append(fmt_quote(name, ticker, q))
    return "\n".join(lines)


def fmt_inst(inst):
    """把法人買賣超接在股價後面,例: ' | 外資+2,627張 投信+587張'。查無資料回空字串。"""
    if not inst:
        return ""
    foreign = inst.get("foreign")
    trust = inst.get("trust")
    parts = []
    if foreign is not None:
        parts.append(f"外資{foreign:+,}張")
    if trust is not None:
        parts.append(f"投信{trust:+,}張")
    return " | " + " ".join(parts) if parts else ""


def build_tw_section():
    lines = ["\n📈 *台股自選*"]
    inst_map = ds.get_tw_institutional()

    all_valid = []  # 跨族群蒐集,供全域統計用
    for group, stocks in config.TW_STOCKS.items():
        lines.append(f"\n─ *{group}*")

        results = []
        for code, name in stocks.items():
            q = ds.get_tw_quote(code)
            results.append((name, code, q))

        valid = [r for r in results if r[2] is not None]
        valid.sort(key=lambda x: x[2]["pct"], reverse=True)
        for name, code, q in valid:
            lines.append(fmt_quote(name, code, q) + fmt_inst(inst_map.get(code)))
            all_valid.append((name, q))

        for name, code, _ in (r for r in results if r[2] is None):
            lines.append(fmt_quote(name, code, None))

    if all_valid:
        all_valid.sort(key=lambda x: x[1]["pct"], reverse=True)
        top = all_valid[0]
        bottom = all_valid[-1]
        avg = sum(v["pct"] for _, v in all_valid) / len(all_valid)
        lines.append(f"\n🏆 漲幅最大: {top[0]} {top[1]['pct']:+.2f}%")
        lines.append(f"🥶 跌幅最大: {bottom[0]} {bottom[1]['pct']:+.2f}%")
        lines.append(f"📐 自選股平均漲跌幅: {avg:+.2f}%")

    return "\n".join(lines)


def build_us_section():
    lines = ["\n📈 *美股自選*"]
    results = []
    for ticker in config.US_STOCKS:
        q = ds.get_quote(ticker)
        results.append((ticker, q))

    valid = [r for r in results if r[1] is not None]
    valid.sort(key=lambda x: x[1]["pct"], reverse=True)

    for ticker, q in valid:
        lines.append(fmt_quote(ticker, ticker, q))

    if valid:
        top = valid[0]
        bottom = valid[-1]
        lines.append(f"\n🏆 漲幅最大: {top[0]} {top[1]['pct']:+.2f}%")
        lines.append(f"🥶 跌幅最大: {bottom[0]} {bottom[1]['pct']:+.2f}%")

    return "\n".join(lines)


def build_jpkr_section():
    lines = ["\n📈 *日韓龍頭股*"]
    combined = {**config.JP_STOCKS, **config.KR_STOCKS}
    for ticker, name in combined.items():
        q = ds.get_quote(ticker)
        lines.append(fmt_quote(name, ticker, q))
    return "\n".join(lines)


def build_news_section(query: str, limit: int = 5):
    news = ds.get_news(query, limit)
    if not news:
        return ""
    lines = ["\n📰 *相關新聞*"]
    for n in news:
        lines.append(f"• [{n['title']}]({n['link']})")
    return "\n".join(lines)


def run_night_tw():
    now = now_tw()
    text = f"🌙 *台股今日收盤總結* ({now})\n"
    text += build_index_section(["台灣加權指數"]) + "\n"
    text += build_tw_section()
    text += build_news_section("台股", 5)
    notifier.send_telegram_message(text)


def run_us_morning():
    now = now_tw()
    text = f"🌅 *美股收盤總結* ({now})\n"
    text += build_index_section(["美國S&P500", "美國那斯達克", "美國道瓊"]) + "\n"
    text += build_us_section()
    text += build_news_section("美股 半導體", 5)
    notifier.send_telegram_message(text)


def run_jpkr_morning():
    now = now_tw()
    text = f"🗾 *日韓股市早盤資訊* ({now})\n"
    text += build_index_section(["日本日經225", "韓國KOSPI"]) + "\n"
    text += build_jpkr_section()
    notifier.send_telegram_message(text)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["night_tw", "us_morning", "jpkr_morning"])
    args = parser.parse_args()

    if args.mode == "night_tw":
        run_night_tw()
    elif args.mode == "us_morning":
        run_us_morning()
    elif args.mode == "jpkr_morning":
        run_jpkr_morning()
