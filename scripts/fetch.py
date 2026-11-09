"""六仙出林 数据抓取：天天基金(东方财富)公开页面 + TradingView 个股指标。输出 data/raw.json

主源失败时的备用（不编造行情）：
- 排名名单 rankhandler → https://www.1234567.com.cn 同路径
- pingzhongdata → https://fund.1234567.com.cn 同路径
- 两处都失败的单只净值日收益率 → api.fund.eastmoney.com/f10/lsjz 的 JZZZL
- TradingView 失败且已有 data/raw.json → 沿用其中 stocks，构建把结果标为数据过期
名单或净值大面积失败、以及没有缓存的个股指标失败：不写 raw，退出码 1，由 mark_stale 只打过期标记。
"""
import json, re, time, sys, os, datetime as dt, urllib.request, urllib.parse, threading
from concurrent.futures import ThreadPoolExecutor
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = {"User-Agent": "Mozilla/5.0", "Referer": "https://fundf10.eastmoney.com/"}
LIMIT = int(os.environ.get("LIMIT", "0"))
TODAY = dt.date.today()
TYPES = r"^(股票型|混合型-偏股|混合型-灵活|QDII-普通股票|QDII-混合偏股|QDII-混合灵活)$"

LOCK = threading.Lock()
FALLBACK = {}
PING_FAIL = 0
NAV_BACKUP = 0
BJ = dt.timezone(dt.timedelta(hours=8))

def backup_urls(url):
    if "fund.eastmoney.com/data/rankhandler.aspx" in url:
        return [url.replace("https://fund.eastmoney.com/", "https://www.1234567.com.cn/", 1)]
    if "fund.eastmoney.com/pingzhongdata/" in url:
        return [url.replace("https://fund.eastmoney.com/", "https://fund.1234567.com.cn/", 1)]
    return []

def note_fallback(url):
    if "rankhandler" in url:
        key = "rankhandler→www.1234567.com.cn"
    elif "pingzhongdata" in url:
        key = "pingzhongdata→fund.1234567.com.cn"
    elif "/f10/lsjz" in url:
        key = "lsjz→api.fund.eastmoney.com/f10/lsjz"
    else:
        key = url.split("?")[0]
    with LOCK:
        FALLBACK[key] = FALLBACK.get(key, 0) + 1

def get_once(url, data=None, tries=3):
    err = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "ignore")
        except Exception as e:
            err = e
            time.sleep(1.5 * (i + 1))
    raise err

def get(url, data=None, tries=3):
    err = None
    for ui, u in enumerate([url] + backup_urls(url)):
        try:
            body = get_once(u, data, tries if ui == 0 else 2)
            if ui:
                note_fallback(u)
            return body
        except Exception as e:
            err = e
    raise err

def load_pingzhong(code):
    urls = [
        f"https://fund.eastmoney.com/pingzhongdata/{code}.js",
        f"https://fund.1234567.com.cn/pingzhongdata/{code}.js",
    ]
    err = None
    for ui, u in enumerate(urls):
        try:
            t = get_once(u, tries=3 if ui == 0 else 2)
            if "Data_netWorthTrend" not in t and "fS_name" not in t:
                raise RuntimeError("pingzhongdata 正文无效")
            if ui:
                note_fallback(u)
            return t
        except Exception as e:
            err = e
    raise err

def nav_from_lsjz(code):
    """日收益率用 lsjz 的 JZZZL，时间戳对齐到北京时间 0 点，与 pingzhongdata 一致。空白涨跌幅记 0，与主源 equityReturn or 0 相同。"""
    global NAV_BACKUP
    cutoff = dt.date.today() - dt.timedelta(days=365 * 6 + 30)
    rows = []
    for page in range(1, 90):
        t = get_once(f"https://api.fund.eastmoney.com/f10/lsjz?fundCode={code}&pageIndex={page}&pageSize=20", tries=2)
        lst = (json.loads(t).get("Data") or {}).get("LSJZList") or []
        if not lst:
            break
        for x in lst:
            day = dt.date.fromisoformat(x["FSRQ"])
            zz = x.get("JZZZL")
            ret = float(zz) if zz not in (None, "") else 0.0
            ts = int(dt.datetime(day.year, day.month, day.day, tzinfo=BJ).timestamp())
            rows.append([ts, ret])
        if dt.date.fromisoformat(lst[-1]["FSRQ"]) <= cutoff:
            break
    if not rows:
        raise RuntimeError("lsjz 无净值")
    rows.sort()
    with LOCK:
        NAV_BACKUP += 1
    note_fallback("https://api.fund.eastmoney.com/f10/lsjz")
    return rows

def write_status(**kw):
    json.dump(kw, open(os.path.join(ROOT, "data", "fetch_status.json"), "w"), ensure_ascii=False, indent=1)

def strip(t): return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))

def rank_list(ft):
    ed = TODAY.isoformat(); sd = (TODAY - dt.timedelta(days=365)).isoformat()
    u = (f"https://fund.eastmoney.com/data/rankhandler.aspx?op=ph&dt=kf&ft={ft}&rs=&gs=0&sc=3nzf&st=desc"
         f"&sd={sd}&ed={ed}&qdii=&tabSubtype=,,,,,&pi=1&pn=20000&dx=1")
    t = get(u); arr = json.loads(re.search(r"datas:(\[.*?\])", t, re.S).group(1))
    return [s.split(",") for s in arr]

def universe():
    out = {}
    for ft in ["gp", "hh", "qdii"]:
        for f in rank_list(ft):
            code, name, estab = f[0], f[1], f[16]
            if re.search(r"[B-Z]$", name) and not name.endswith("A"): continue   # 只留A类/无后缀主份额
            if re.search(r"持有|封闭|定开|定期开放|养老|目标日期|[一二两三四五六]年|\d+年|[一二两三六九十]+个月|\d+个月", name): continue
            out[code] = {"code": code, "name": name, "ft": ft, "estab": estab}
    return list(out.values())

def jsvar(t, n):
    m = re.search(r"var %s\s*=\s*(.*?);\s*(/\*|var |$)" % n, t, re.S)
    if not m: return None
    try: return json.loads(m.group(1))
    except Exception: return None

def tenure(code):
    t = strip(get(f"https://fundf10.eastmoney.com/jjjl_{code}.html"))
    i = t.find("起始期 截止期 基金经理 任职期间 任职回报")
    seg = t[i:i + 4000]
    rows = re.findall(r"(\d{4}-\d{2}-\d{2}) (至今|\d{4}-\d{2}-\d{2}) (.*?) (?:\d+年又)?\d+天 ", seg)
    if not rows or rows[0][1] != "至今": return None, []
    names = rows[0][2].split(); best = 0; bestn = None
    for n in names:
        start = None
        for s, e, ns in rows:
            if n in ns.split(): start = s
            else: break
        d = (TODAY - dt.date.fromisoformat(start)).days / 365.25
        if d > best: best, bestn = d, n
    return round(best, 2), names

def jbgk(code):
    t = strip(get(f"https://fundf10.eastmoney.com/jbgk_{code}.html"))
    g = lambda p: (re.search(p, t) or [None, None])[1]
    return {"type": g(r"基金类型 (\S+)"), "mgmt_fee": g(r"管理费率 ([\d.]+)%"), "cust_fee": g(r"托管费率 ([\d.]+)%"),
            "nav_size": g(r"净资产规模 ([\d.]+)亿元")}

def holdings(code):
    qs = {}
    for y in range(TODAY.year - 3, TODAY.year + 1):
        t = get(f"https://fundf10.eastmoney.com/FundArchivesDatas.aspx?type=jjcc&code={code}&topline=10&year={y}")
        for blk in re.split(r"股票投资明细", strip(t))[1:]:
            d = re.search(r"截止至： (\d{4}-\d{2}-\d{2})", blk)
            if not d: continue
            items = re.findall(r" \d+ ([0-9A-Z]{4,6}) (\S+?) .*?(\d+\.\d+)% ", blk.split("显示全部")[0])
            qs[d.group(1)] = [[c, n, float(w)] for c, n, w in items][:10]
    return dict(sorted(qs.items()))

def one(f):
    global PING_FAIL
    code = f["code"]
    try:
        with LOCK:
            blown = PING_FAIL > 25
        if blown:
            raise RuntimeError("净值主备连续失败，停止单只备用")
        try:
            t = load_pingzhong(code)
            nav = jsvar(t, "Data_netWorthTrend") or []
            f["ret"] = [[x["x"] // 1000, x.get("equityReturn") or 0] for x in nav if x["x"] / 1000 > time.time() - 86400 * 365 * 6]
            f["scale"] = jsvar(t, "Data_fluctuationScale")
            f["mgr_now"] = [m["name"] for m in (jsvar(t, "Data_currentFundManager") or [])]
        except Exception:
            with LOCK:
                PING_FAIL += 1
                blown = PING_FAIL > 25
            if blown:
                raise RuntimeError("净值主备连续失败，停止单只备用")
            f["ret"] = nav_from_lsjz(code)
            f["scale"] = None
            f["mgr_now"] = []
            f["nav_backup"] = "lsjz"
        f.update(jbgk(code))
        f["tenure"], f["mgr_tbl"] = tenure(code)
        sz = float(f["nav_size"]) if f.get("nav_size") else None
        f["g1"] = {"type": bool(f.get("type") and re.match(TYPES, f["type"])),
                   "tenure": (f["tenure"] or 0) >= 3, "size": sz is not None and 2 <= sz <= 100}
        f["hold"] = holdings(code) if all(f["g1"].values()) else {}
    except Exception as e:
        f["error"] = repr(e)[:120]
    return f

def tv(markets_syms):
    cols = ["name", "price_earnings_ttm", "price_book_fq", "return_on_equity", "dividend_yield_recent",
            "earnings_per_share_diluted_yoy_growth_ttm", "sector"]
    out = {}
    for m in ["china", "hongkong"]:
        body = json.dumps({"columns": cols, "range": [0, 20000]}).encode()
        for r in json.loads(get(f"https://scanner.tradingview.com/{m}/scan", body))["data"]:
            k = r["s"].split(":")[1]; k = k.zfill(5) if m == "hongkong" else k
            out[k] = dict(zip(["pe", "pb", "roe", "dy", "g", "sector"], r["d"][1:]))
    return out

if __name__ == "__main__":
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        U = universe()
    except Exception as e:
        write_status(ok=False, stale=True, error=f"名单主备都失败: {e}"[:300], fallback=FALLBACK, fetched_at=now)
        print("universe failed", e, file=sys.stderr)
        sys.exit(1)
    CNT = {"主份额去长持有": len(U)}; print("universe", len(U), file=sys.stderr)
    cut = (TODAY.replace(year=TODAY.year - 5)).isoformat()
    U = [f for f in U if f["estab"] and f["estab"] <= cut]   # 准入①先过成立满5年，减少抓取量
    CNT["成立满5年"] = len(U)
    if LIMIT: U = U[:: max(1, len(U) // LIMIT)][:LIMIT]
    print("estab>=5y", len(U), file=sys.stderr)
    with ThreadPoolExecutor(int(os.environ.get("WORKERS", "8"))) as ex: R = list(ex.map(one, U))
    with_ret = sum(1 for f in R if f.get("ret"))
    if PING_FAIL > 25 and with_ret * 2 < max(len(R), 1):
        write_status(ok=False, stale=True, error=f"净值主备失败 {PING_FAIL} 只，有效净值 {with_ret}/{len(R)}，不写入 raw",
                     fallback=FALLBACK, nav_backup=NAV_BACKUP, fetched_at=now)
        print("nav backup aborted", PING_FAIL, with_ret, file=sys.stderr)
        sys.exit(1)
    raw_path = os.path.join(ROOT, "data", "raw.json")
    stocks_reused = False
    try:
        stocks = tv(None)
    except Exception as e:
        prev = {}
        if os.path.exists(raw_path):
            try:
                prev = json.load(open(raw_path)).get("stocks") or {}
            except Exception:
                prev = {}
        if not prev:
            write_status(ok=False, stale=True, error=f"TradingView失败且无缓存: {e}"[:300], fallback=FALLBACK,
                         nav_backup=NAV_BACKUP, fetched_at=now)
            print("tradingview failed", e, file=sys.stderr)
            sys.exit(1)
        stocks = prev
        stocks_reused = True
        print("tradingview reused previous stocks", len(stocks), file=sys.stderr)
    payload = {"fetched_at": now, "counts": CNT, "funds": R, "stocks": stocks,
               "fetch": {"fallback": FALLBACK, "nav_backup": NAV_BACKUP, "stocks_reused": stocks_reused}}
    json.dump(payload, open(raw_path, "w"), ensure_ascii=False)
    write_status(ok=True, stale=bool(stocks_reused),
                 error="TradingView失败，沿用上次个股指标" if stocks_reused else "",
                 fallback=FALLBACK, nav_backup=NAV_BACKUP, stocks_reused=stocks_reused, fetched_at=now)
    print("done errors", sum(1 for f in R if "error" in f), "fallback", FALLBACK, file=sys.stderr)
