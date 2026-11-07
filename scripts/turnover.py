"""2025年报股票换手率：取年报 8.4.3 买入股票成本总额、卖出股票收入总额，
与资产负债表 股票投资(本期末/上年度末) 计算：换手率=(买入+卖出)/2 ÷ 期初期末股票投资均值。
结果缓存 data/turnover.json（年报为年度数据，已取到的不再重抓）。"""
import json, os, re, sys, subprocess, tempfile, urllib.request
from concurrent.futures import ThreadPoolExecutor
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
YEAR = int(os.environ.get("TO_YEAR", "2025"))
UA = {"User-Agent": "Mozilla/5.0", "Referer": "https://fundf10.eastmoney.com/"}
OUT = os.path.join(ROOT, "data", "turnover.json")
def get(u, binary=False):
    for i in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=60) as r:
                b = r.read(); return b if binary else b.decode("utf-8", "ignore")
        except Exception as e: err = e
    raise err
num = lambda s: float(s.replace(",", ""))
NUM = r"(-?[\d,]+\.\d{2})"
def one(code):
    try:
        d = json.loads(get(f"https://api.fund.eastmoney.com/f10/JJGG?fundcode={code}&pageIndex=1&pageSize=60&type=3"))
        T = lambda x: x["TITLE"].translate(str.maketrans("〇零一二三四五六七八九○O", "0012345678900"))
        ann = next((x for x in d.get("Data") or [] if f"{YEAR}年年度报告" in T(x) and "摘要" not in x["TITLE"] and "更正" not in x["TITLE"] and "英文" not in x["TITLE"]), None)
        if not ann: return code, {"err": f"未找到{YEAR}年报"}
        pdf = get(f"https://pdf.dfcfw.com/pdf/H2_{ann['ID']}_1.pdf", True)
        with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
            f.write(pdf); f.flush()
            t = subprocess.run(["pdftotext", "-layout", f.name, "-"], capture_output=True, text=True, timeout=120).stdout
        buy = re.search(r"买入(?:股票|权益投资)\S*?(?:成本|金额)\S*?总额\s+" + NUM, t)
        sell = re.search(r"卖出(?:股票|权益投资)\S*?(?:收入|金额)\S*?总额\s+" + NUM, t)
        bs = re.search(r"\n\s*(?:其中：)?(?:股票投资|权益投资)\s+(?:7\.4\.\S+\s+)?" + NUM + r"\s+" + NUM + r"\s*\n", t)
        if not (buy and sell and bs): return code, {"err": "年报字段未解析", "ann": ann["ID"]}
        b, s, e0, e1 = num(buy.group(1)), num(sell.group(1)), num(bs.group(2)), num(bs.group(1))
        avg = (e0 + e1) / 2
        if avg <= 0: return code, {"err": "股票投资为0", "ann": ann["ID"]}
        return code, {"rate": round((b + s) / 2 / avg * 100, 1), "buy": b, "sell": s, "stock_end": e1, "stock_begin": e0, "ann": ann["ID"], "year": YEAR}
    except Exception as ex:
        return code, {"err": repr(ex)[:80]}
if __name__ == "__main__":
    raw = json.load(open(os.path.join(ROOT, "data", "raw.json")))
    cache = json.load(open(OUT)) if os.path.exists(OUT) else {}
    codes = [f["code"] for f in raw["funds"] if f.get("g1") and all(f["g1"].values()) and "rate" not in cache.get(f["code"], {})]
    if os.environ.get("LIMIT"): codes = codes[:int(os.environ["LIMIT"])]
    with ThreadPoolExecutor(int(os.environ.get("WORKERS", "12"))) as ex:
        for c, v in ex.map(one, codes): cache[c] = v
    json.dump(dict(sorted(cache.items())), open(OUT, "w"), ensure_ascii=False, indent=0)
    ok = sum(1 for v in cache.values() if "rate" in v); print("turnover ok", ok, "/", len(cache), file=sys.stderr)
