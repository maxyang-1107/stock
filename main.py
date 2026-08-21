# -*- coding: utf-8 -*-
"""
主程式
------
用法: python main.py [night_tw | us_morning | jpkr_morning | weekly_tw]

night_tw     -> 台灣時間 22:00 執行,今日台股收盤總結
jpkr_morning -> 台灣時間 08:00 執行,日韓龍頭股開盤前資訊
us_morning   -> 台灣時間 09:00 執行,美股收盤總結
weekly_tw    -> 每週日 12:00 執行,本週自選股新聞 + 三大法人/外資買賣超回顧
"""

import argparse
import random
import time
from datetime import datetime

import config
import data_sources as ds
import notifier


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
        if name == "台灣加權指數":
            q = ds.get_tw_index_from_twse()
        else:
            ticker = config.INDICES[name]
            q = ds.get_quote(ticker)
        lines.append(fmt_quote(name, name, q))
    return "\n".join(lines)


def build_tw_section():
    lines = ["\n📈 *台股自選*"]
    results = []
    for code, name in config.TW_STOCKS.items():
        q = ds.get_tw_quote(code)
        results.append((name, code, q))

    valid = [r for r in results if r[2] is not None]
    valid.sort(key=lambda x: x[2]["pct"], reverse=True)

    for name, code, q in valid:
        lines.append(fmt_quote(name, code, q))

    failed = [r for r in results if r[2] is None]
    for name, code, _ in failed:
        lines.append(fmt_quote(name, code, None))

    if valid:
        top = valid[0]
        bottom = valid[-1]
        avg = sum(r[2]["pct"] for r in valid) / len(valid)
        lines.append(f"\n🏆 漲幅最大: {top[0]} {top[2]['pct']:+.2f}%")
        lines.append(f"🥶 跌幅最大: {bottom[0]} {bottom[2]['pct']:+.2f}%")
        lines.append(f"📐 自選股平均漲跌幅: {avg:+.2f}%")

    return "\n".join(lines)


def build_us_section():
    lines = ["\n📈 *美股自選*"]
    results = []
    for i, ticker in enumerate(config.US_STOCKS):
        if i > 0:
            time.sleep(0.6 + random.uniform(0, 0.6))  # 降低短時間內連續打 Yahoo 的機率
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
    for i, (ticker, name) in enumerate(combined.items()):
        if i > 0:
            time.sleep(0.6 + random.uniform(0, 0.6))
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


def build_market_institutional_section(week_dates):
    m = ds.get_market_institutional_week(week_dates)
    lines = ["\n💰 *大盤三大法人買賣超(本週合計,單位:億元)*"]
    if m["days_counted"] == 0:
        lines.append("資料取得失敗(可能是 TWSE API 格式異動或本週無交易日)")
        return "\n".join(lines)

    def to_yi(v):
        return v / 100_000_000

    lines.append(f"外資及陸資: {to_yi(m['foreign']):+.2f} 億")
    lines.append(f"投信: {to_yi(m['trust']):+.2f} 億")
    lines.append(f"自營商: {to_yi(m['dealer']):+.2f} 億")
    lines.append(f"三大法人合計: {to_yi(m['total']):+.2f} 億")
    return "\n".join(lines)


def build_tw_weekly_section(week_dates):
    lines = ["\n📊 *自選股本週三大法人買賣超 + 新聞*"]
    codes = list(config.TW_STOCKS.keys())
    inst = ds.get_weekly_institutional(codes, week_dates)

    for code, name in config.TW_STOCKS.items():
        d = inst.get(code, {})
        lines.append(f"\n■ {name}({code})")
        if not d or d.get("days_counted", 0) == 0:
            lines.append("  三大法人資料取得失敗(可能為上櫃股或本週休市)")
        else:
            foreign_lots = round(d["foreign"] / 1000)
            total_lots = round(d["total_inst"] / 1000)
            lines.append(f"  外資買賣超: {foreign_lots:+,}張 | 三大法人合計: {total_lots:+,}張")

        news = ds.get_news(name, limit=1)
        if news:
            n = news[0]
            lines.append(f"  📰 [{n['title']}]({n['link']})")

    return "\n".join(lines)


def run_weekly_tw():
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    week_dates = ds.get_past_week_weekdays()
    week_range = f"{week_dates[0].strftime('%m/%d')} - {week_dates[-1].strftime('%m/%d')}"
    text = f"🗓️ *本週回顧* ({week_range})\n產生時間: {now}\n"
    text += build_market_institutional_section(week_dates)
    text += build_tw_weekly_section(week_dates)
    notifier.send_telegram_message(text)


def run_night_tw():
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    text = f"🌙 *台股今日收盤總結* ({now})\n"
    text += build_index_section(["台灣加權指數"]) + "\n"
    text += build_tw_section()
    text += build_news_section("台股", 5)
    notifier.send_telegram_message(text)


def run_us_morning():
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    text = f"🌅 *美股收盤總結* ({now})\n"
    text += build_index_section(["美國S&P500", "美國那斯達克", "美國道瓊"]) + "\n"
    text += build_us_section()
    text += build_news_section("美股 半導體", 5)
    notifier.send_telegram_message(text)


def run_jpkr_morning():
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    text = f"🗾 *日韓股市開盤前資訊* ({now})\n"
    text += build_index_section(["日本日經225", "韓國KOSPI"]) + "\n"
    text += build_jpkr_section()
    notifier.send_telegram_message(text)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["night_tw", "us_morning", "jpkr_morning", "weekly_tw"])
    args = parser.parse_args()

    if args.mode == "night_tw":
        run_night_tw()
    elif args.mode == "us_morning":
        run_us_morning()
    elif args.mode == "jpkr_morning":
        run_jpkr_morning()
    elif args.mode == "weekly_tw":
        run_weekly_tw()
