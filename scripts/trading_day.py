"""最近 A 股交易日：上证指数（000001）日 K 最后一根的日期。

主源 push2his.eastmoney.com，备用 91.push2his.eastmoney.com。
取不到就返回 None，不编造日期。
"""
import json
import urllib.request

URLS = [
    "https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=1.000001&klt=101&fqt=1&lmt=5&end=20500101&fields1=f1&fields2=f51",
    "https://91.push2his.eastmoney.com/api/qt/stock/kline/get?secid=1.000001&klt=101&fqt=1&lmt=5&end=20500101&fields1=f1&fields2=f51",
]
UA = {"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"}


def latest_trading_day():
    for url in URLS:
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=20) as r:
                payload = json.loads(r.read().decode("utf-8", "ignore"))
            klines = ((payload.get("data") or {}).get("klines") or [])
            if not klines:
                continue
            day = str(klines[-1]).split(",")[0]
            if len(day) == 10 and day[4] == "-" and day[7] == "-":
                return day
        except Exception:
            continue
    return None
