"""抓取或打分失败时，只把 data/latest.json 标成数据过期。

不改净值、得分、名单或权重，也不编造行情。没有 latest.json 时直接退出。
"""
import datetime as dt
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from trading_day import latest_trading_day

LATEST = os.path.join(ROOT, "data", "latest.json")
STATUS = os.path.join(ROOT, "data", "fetch_status.json")


def main():
    if not os.path.exists(LATEST):
        print("no latest.json", file=sys.stderr)
        return
    data = json.load(open(LATEST))
    reason = "更新失败，沿用上次公布的数字"
    if os.path.exists(STATUS):
        try:
            status = json.load(open(STATUS))
        except Exception:
            status = {}
        err = (status.get("error") or "").strip()
        if err:
            reason = "更新失败，沿用上次公布的数字：" + err[:180]
    day = latest_trading_day()
    data_date = data.get("data_date") or ""
    if day and data_date and data_date < day:
        reason += f"；净值日期 {data_date} 落后于最近A股交易日 {day}"
    elif not day:
        reason += "；未能取得上证指数最近交易日"
    data["stale"] = True
    data["stale_reason"] = reason
    if day:
        data["latest_trading_day"] = day
    data["stale_marked_at"] = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    json.dump(data, open(LATEST, "w"), ensure_ascii=False, indent=1)
    print(json.dumps({"stale": True, "latest_trading_day": day, "data_date": data_date}, ensure_ascii=False))


if __name__ == "__main__":
    main()
