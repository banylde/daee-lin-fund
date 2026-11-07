"""六仙出林 筛选打分：读 data/raw.json → data/latest.json + data/official.json"""
import json, os, re, sys, math, statistics as st, datetime as dt
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
C = json.load(open(os.path.join(ROOT, "config.json")))
RAW = json.load(open(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "data", "raw.json")))
S = RAW["stocks"]; STY = C["styles"]
DAY = 86400

def pct_rank(vals, higher=True):
    """返回 0~100 排名分（池内），None 视为最差"""
    idx = sorted(range(len(vals)), key=lambda i: (vals[i] is None, -(vals[i] or 0) if higher else (vals[i] or 0)))
    n = len(vals); out = [0.0] * n
    for r, i in enumerate(idx): out[i] = 100.0 if n == 1 else round(100 * (n - 1 - r) / (n - 1), 1)
    return out

def qmetrics(h):
    tot = sum(w for _, _, w in h); m = {"top10": round(tot, 2)}
    for k in ["pe", "pb", "roe", "g", "dy"]:
        num = den = 0
        for c, _, w in h:
            v = (S.get(c) or {}).get(k)
            if v is None: continue
            if k == "pe" and not (0 < v < 300): continue
            if k == "g": v = max(-100, min(300, v))
            num += v * w; den += w
        m[k] = round(num / den, 2) if den else None
        if k == "pe": m["cov"] = round(den / tot, 2) if tot else 0
    sec = {}
    for c, _, w in h:
        s = (S.get(c) or {}).get("sector") or "未知"; sec[s] = sec.get(s, 0) + w
    m["sec"] = sec
    return m

def nav_series(f):
    v = 1.0; out = []
    for t, r in f.get("ret", []): v *= 1 + (r or 0) / 100; out.append((t, v))
    return out

def at(series, t):  # 最后一个 <= t 的净值
    lo, hi, ans = 0, len(series) - 1, None
    while lo <= hi:
        m = (lo + hi) // 2
        if series[m][0] <= t: ans = series[m][1]; lo = m + 1
        else: hi = m - 1
    return ans

now_ts = max((f["ret"][-1][0] for f in RAW["funds"] if f.get("ret")), default=0)
DATA_DATE = dt.datetime.utcfromtimestamp(now_ts + 8 * 3600).date()
T3 = now_ts - 3 * 365 * DAY
LASTY = DATA_DATE.year - 1; YEARS = [LASTY - 2, LASTY - 1, LASTY]
MONTHS = []  # 近24个月月末
y, mth = DATA_DATE.year, DATA_DATE.month
for i in range(36):
    MONTHS.append(int(dt.datetime(y, mth, 1).timestamp()) - DAY + 8 * 3600)
    mth -= 1
    if mth == 0: y, mth = y - 1, 12
MONTHS = sorted(MONTHS)

def perf(f):
    s = nav_series(f)
    if not s or s[0][0] > T3 + 10 * DAY: return None
    p = {"r3y": round((s[-1][1] / at(s, T3) - 1) * 100, 2)}
    for yy in YEARS:
        a = at(s, int(dt.datetime(yy, 1, 1).timestamp())); b = at(s, int(dt.datetime(yy + 1, 1, 1).timestamp()))
        p[str(yy)] = round((b / a - 1) * 100, 2) if a and b else None
    peak = 0; mdd = 0
    for t, v in s:
        if t < T3: continue
        peak = max(peak, v); mdd = min(mdd, v / peak - 1)
    p["mdd"] = round(mdd * 100, 2)
    me = [at(s, t) for t in MONTHS] + [s[-1][1]]
    p["mret"] = [me[i + 1] / me[i] - 1 for i in range(len(me) - 1)]
    p["vol"] = round(st.pstdev(p["mret"]) * math.sqrt(12) * 100, 2)
    p["roll"] = [(me[i] / me[i - 12] - 1) for i in range(12, len(me))]  # 近24个月滚动一年
    a = at(s, now_ts - 365 * DAY); b = at(s, now_ts - 730 * DAY)
    p["r1y"] = (s[-1][1] / a - 1) if a else None; p["r1y_prev"] = (a / b - 1) if a and b else None
    return p

# ---------- 准入 & 风格 ----------
funds = [f for f in RAW["funds"] if "error" not in f]
F = {}
for f in funds:
    g1 = f.get("g1") or {}
    rec = {"code": f["code"], "name": f["name"], "type": f.get("type"), "tenure": f.get("tenure"), "mgr": f.get("mgr_now"),
           "size": float(f["nav_size"]) if f.get("nav_size") else None,
           "fee": round(float(f["mgmt_fee"]) + float(f["cust_fee"]), 2) if f.get("mgmt_fee") and f.get("cust_fee") else None,
           "g1": all(g1.values()) if g1 else False, "g1_fail": [k for k, v in g1.items() if not v]}
    sc = (f.get("scale") or {}).get("series") or []
    rec["scale_mom"] = sc[-1].get("mom") if sc else None
    q = list(f.get("hold", {}).items())[-C["gate2"]["quarters"]:]
    rec["quarters"] = [d for d, _ in q]; rec["qm"] = [qmetrics(h) for _, h in q]
    if rec["g1"] and q: F[f["code"]] = rec | {"_raw": f}
    F.setdefault(f["code"], rec)

def style_of(r):
    if (r["type"] or "").startswith("QDII"): return "海外"
    last = r["qm"][-1]; top3 = sum(sorted(last["sec"].values(), reverse=True)[:3])
    r["top3_sector"] = round(top3, 1)
    if top3 > 50: return "主题"
    return None

pool = [r for r in F.values() if r["g1"] and r["qm"]]
for r in pool:
    r["style"] = style_of(r)
    q4 = r["qm"][-4:]
    avg = lambda k: (lambda v: sum(v) / len(v) if v else None)([m[k] for m in q4 if m[k] is not None])
    r["feat"] = {k: avg(k) for k in ["pe", "pb", "roe", "g", "dy"]}
    hs = [set(c for c, _, _ in h) for _, h in list(r["_raw"]["hold"].items())[-C["gate2"]["quarters"]:]]
    ov = [len(hs[i] & hs[i - 1]) / 10 for i in range(1, len(hs))]
    r["overlap"] = round(sum(ov) / len(ov), 3) if ov else None; r["ov_list"] = ov
rest = [r for r in pool if r["style"] is None]
if rest:
    fe = lambda k: [r["feat"][k] for r in rest]
    peg = [(r["feat"]["pe"] / r["feat"]["g"]) if r["feat"]["pe"] and r["feat"]["g"] and r["feat"]["g"] > 0 else None for r in rest]
    P = {"g": pct_rank(fe("g")), "peg": pct_rank(peg, False), "roe": pct_rank(fe("roe")), "pb": pct_rank(fe("pb"), False),
         "pe": pct_rank(fe("pe"), False), "dy": pct_rank(fe("dy")), "ov": pct_rank([r["overlap"] for r in rest], False)}
    for i, r in enumerate(rest):
        aff = {"成长": (P["g"][i] + P["peg"][i]) / 2, "质量": P["roe"][i], "价值": (P["pb"][i] + P["pe"][i] + P["dy"][i]) / 3, "趋势": P["ov"][i]}
        r["aff"] = {k: round(v, 1) for k, v in aff.items()}; r["style"] = max(aff, key=aff.get)

# ---------- 四关 ----------
QUANT = re.compile(C["gate2"]["quant_pat"])
TO = json.load(open(os.path.join(ROOT, "data", "turnover.json"))) if os.path.exists(os.path.join(ROOT, "data", "turnover.json")) else {}
def gate2(r):
    if r["style"] in C["gate2"]["exempt"]: return True, f"{r['style']}类免除", None
    if len(r["ov_list"]) < C["gate2"]["quarters"] - 1: return False, f"季报仅{len(r['ov_list']) + 1}期", None
    r["purity"] = round(1 - r["overlap"], 3)
    if r["overlap"] < C["gate2"]["min_overlap"]: return False, f"前十大重合度<{C['gate2']['min_overlap']:.0%}", None
    return True, "", None
def gate3(r):
    t = TO.get(r["code"]) or {}; r["turnover"] = t.get("rate")
    if r["turnover"] is None: return False, "缺换手率"
    if r["turnover"] > C["turnover_cap"][r["style"]]: return False, "换手率超限"
    return True, ""
OVD = sorted(r["overlap"] for r in pool if r["overlap"] is not None and r["style"] not in C["gate2"]["exempt"])
for r in pool:
    if r["style"] == "趋势" and QUANT.search(r["name"] + (r["type"] or "")): r["style"] = None; r["quant_out"] = True
EXCL = sum(1 for r in pool if r.get("quant_out")); pool = [r for r in pool if r["style"]]
for r in pool:
    r["perf"] = perf(r["_raw"]); r["g2"], r["g2_why"], _ = gate2(r)
    r["g3"], r["g3_why"] = gate3(r)
FUNNEL, CANDS = {}, {}
for s in STY:
    grp = [r for r in pool if r["style"] == s]
    peers = [r for r in grp if r["perf"]]
    n = len(peers)
    def rk(key, higher=True):
        vals = [r["perf"][key] if key in r["perf"] else None for r in peers]
        sc = pct_rank(vals, higher); return {r["code"]: sc[i] for i, r in enumerate(peers)}
    r3 = rk("r3y"); yr = {y: rk(str(y)) for y in YEARS}; mdd_med = st.median([r["perf"]["mdd"] for r in peers]) if peers else None
    roll = {}
    for m in range(24):
        vals = [r["perf"]["roll"][m] for r in peers]; sc = pct_rank(vals)
        for i, r in enumerate(peers): roll.setdefault(r["code"], []).append(sc[i] >= 50)
    top = 100 * (1 - C["gate4"]["top_frac"])
    for r in grp:
        if not r["perf"]: r["g4"], r["g4_why"] = False, "净值不足三年"; continue
        c = r["code"]; r["roll_win"] = round(sum(roll[c]) / len(roll[c]), 3)
        why = []
        if r3[c] < top: why.append("近三年未进前1/3")
        if any(yr[y][c] is not None and yr[y][c] < 100 - top for y in YEARS if r["perf"][str(y)] is not None): why.append("有自然年落后1/3")
        if r["perf"]["mdd"] < mdd_med: why.append("回撤差于中位数")
        if r["roll_win"] < C["gate4"]["roll_win_min"]: why.append("滚动胜率<60%")
        r["g4"] = not why; r["g4_why"] = "；".join(why); r["rank3y"] = r3[c]
        r["rank1y_bad"] = None
    # 近一年 / 前一年 同类排名（替换触发用）
    for key in ["r1y", "r1y_prev"]:
        vals = [r["perf"][key] for r in peers]; sc = pct_rank(vals)
        for i, r in enumerate(peers): r[key + "_pct"] = sc[i]
    a = len(grp); b = sum(1 for r in grp if r["g2"]); c3 = sum(1 for r in grp if r["g2"] and r["g3"])
    to_cov = sum(1 for r in grp if r.get("turnover") is not None)
    ok = [r for r in grp if r["g2"] and r["g3"] and r.get("g4")]
    FUNNEL[s] = {"准入": a, "风格稳定": b, "换手率": c3, "业绩": len(ok), "mdd_median": mdd_med, "peers": n, "换手率覆盖": f"{to_cov}/{a}"}
    # 打分
    if ok:
        W = C["score_w"]
        stab = pct_rank([r["purity"] for r in ok], False) if s not in C["gate2"]["exempt"] else [50.0] * len(ok)
        win = pct_rank([r["roll_win"] for r in ok]); dd = pct_rank([r["perf"]["mdd"] for r in ok])
        ten = pct_rank([r["tenure"] for r in ok]); fee = pct_rank([r["fee"] for r in ok], False)
        for i, r in enumerate(ok):
            r["sub"] = {"stability": stab[i], "roll_win": win[i], "drawdown": dd[i], "tenure": ten[i], "fee": fee[i]}
            r["score"] = round(sum(r["sub"][k] * W[k] for k in W) / 100, 1)
        def scale_stab(r):
            ser = (r["_raw"].get("scale") or {}).get("series") or []
            mv = [abs(float(x["mom"].strip("%"))) for x in ser if x.get("mom")]
            return st.mean(mv) if mv else 999
        ok.sort(key=lambda r: -r["score"])
        if len(ok) > 1 and ok[0]["score"] - ok[1]["score"] < C["tie_gap"]:
            a0, a1 = ok[0], ok[1]
            k0 = (a0.get("purity") or 9, scale_stab(a0)); k1 = (a1.get("purity") or 9, scale_stab(a1))
            if k1 < k0: ok[0], ok[1] = a1, a0
            ok[0]["tie_note"] = f"与第二名差<{C['tie_gap']}分，按风格纯度/规模稳定择优"
    CANDS[s] = ok

# ---------- 组合体检 ----------
def top10(r): return {c: w for c, _, w in r["_raw"]["hold"][r["quarters"][-1]]}
def corr(a, b):
    ma, mb = st.mean(a), st.mean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b)); den = math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))
    return num / den if den else 0
pick = {s: 0 for s in STY if CANDS[s]}
LOG = []
def cur(): return {s: CANDS[s][i] for s, i in pick.items() if i < len(CANDS[s])}
def bump(s, why):
    pick[s] += 1; LOG.append(f"{s}：{why}" + ("，换为下一名" if pick[s] < len(CANDS[s]) else "，本类无替补，空缺"))
for it in range(20):
    P_ = cur(); ks = list(P_); changed = False
    for i in range(len(ks)):
        for j in range(i + 1, len(ks)):
            a, b = P_[ks[i]], P_[ks[j]]; ta, tb = top10(a), top10(b)
            ov = sum(min(ta[c], tb[c]) for c in ta if c in tb)
            sa, sb = a["qm"][-1]["sec"], b["qm"][-1]["sec"]
            iv = max([min(sa[x], sb[x]) for x in sa if x in sb and x != "未知"] or [0])
            if ov > C["check"]["overlap_max"] or iv > C["check"]["industry_max"]:
                lo = ks[i] if a["score"] < b["score"] else ks[j]
                bump(lo, f"与{(b if lo == ks[i] else a)['name']}重仓重合{ov:.1f}%/单一行业重合{iv:.1f}%，超20%（得分较低）"); changed = True; break
        if changed: break
    if changed: continue
    break
P_ = cur(); ks = list(P_); CM = {}
pairs = []
for i in range(len(ks)):
    for j in range(i + 1, len(ks)):
        c = corr(P_[ks[i]]["perf"]["mret"], P_[ks[j]]["perf"]["mret"]); pairs.append(c)
        CM[f"{ks[i]}-{ks[j]}"] = round(c, 3)
avgc = round(st.mean(pairs), 3) if pairs else None
if avgc is not None and avgc >= C["check"]["corr_max"]:
    worst = max(ks, key=lambda s: st.mean([v for k, v in CM.items() if s in k.split("-")]))
    bump(worst, f"六只平均相关{avgc}≥0.8，该只平均相关最高")
    P_ = cur(); ks = list(P_)
    pairs = [corr(P_[a]["perf"]["mret"], P_[b]["perf"]["mret"]) for i, a in enumerate(ks) for b in ks[i + 1:]]
    CM = {f"{a}-{b}": round(corr(P_[a]["perf"]["mret"], P_[b]["perf"]["mret"]), 3) for i, a in enumerate(ks) for b in ks[i + 1:]}
    avgc = round(st.mean(pairs), 3) if pairs else None
# 全市场相关分布（各类第一名候选池前5两两）
allc = []
sample = [r for s in STY for r in CANDS[s][:5]]
for i in range(len(sample)):
    for j in range(i + 1, len(sample)): allc.append(corr(sample[i]["perf"]["mret"], sample[j]["perf"]["mret"]))
allc.sort()
qd = lambda p: round(allc[int(p * (len(allc) - 1))], 3) if allc else None
CHECK = {"log": LOG, "corr_matrix": CM, "avg_corr": avgc, "corr_dist": {"n": len(allc), "min": qd(0), "p25": qd(.25), "median": qd(.5), "p75": qd(.75), "max": qd(1)},
         "fx": "海外基金业绩未扣汇率（缺数据：缺持仓币种拆分），溢价率仅适用场内LOF，缺数据"}

# ---------- 权重 ----------
def weights(P_):
    iv = {s: 1 / max(r["perf"]["vol"], 1e-6) for s, r in P_.items()}
    tot = sum(iv.values()); w = {s: 100 * v / tot for s, v in iv.items()}
    lo, hi = C["weight"]["min"], C["weight"]["max"]
    for _ in range(50):
        fixed = {s: min(max(v, lo), hi) for s, v in w.items()}
        free = [s for s in w if lo < w[s] < hi]; diff = 100 - sum(fixed.values())
        if abs(diff) < 1e-6 or not free: w = fixed; break
        ft = sum(fixed[s] for s in free); w = {s: fixed[s] + (diff * fixed[s] / ft if s in free else 0) for s in w}
    return {s: round(v, 1) for s, v in w.items()}

# ---------- 正式名单（季度） ----------
OP = os.path.join(ROOT, "data", "official.json")
old = json.load(open(OP)) if os.path.exists(OP) else None
RB = C["rebalance"]
def qkey(d): 
    m = [x for x in RB["months"] if (d.month, d.day) >= (x, RB["day"])]
    return f"{d.year}Q{len(m)}" if m else f"{d.year - 1}Q4"
qk = qkey(DATA_DATE)
def trig(r, o=None):
    t = []
    if o and set(o.get("mgr") or []) != set(r["mgr"] or []): t.append("经理变更")
    if r["scale_mom"] and abs(float(r["scale_mom"].strip("%"))) > 50: t.append(f"规模单季变动{r['scale_mom']}")
    if r["style"] not in C["gate2"]["exempt"] and len(r["ov_list"]) >= 2 and all(x < C["gate2"]["min_overlap"] for x in r["ov_list"][-2:]): t.append("前十大重合度连续两季低于阈值")
    if r.get("turnover") is not None and r["turnover"] > C["turnover_cap"][r["style"]]: t.append("换手率超限")
    if r.get("r1y_pct") is not None and r["r1y_pct"] < 33.3 and (r.get("r1y_prev_pct") or 100) < 33.3: t.append("近一年同类后1/3且持续两年")
    return t
newsel = cur()
if old is None or old.get("quarter") != qk:
    full = old is None or DATA_DATE.month == RB["annual_full_month"]
    picks, changes = {}, []
    for s in STY:
        inc = next((p for p in (old or {}).get("picks", []) if p["style"] == s), None) if not full else None
        incr = F.get(inc["code"]) if inc else None
        keep = incr and incr.get("g2") and incr.get("g4") and not trig(incr, inc)
        r = incr if keep else newsel.get(s)
        if r: picks[s] = {"style": s, "code": r["code"], "name": r["name"], "mgr": r["mgr"]}
        if inc and (not r or r["code"] != inc["code"]): changes.append(f"{s}：{inc['name']}→{r['name'] if r else '空缺'}")
    old = {"quarter": qk, "rebalance_date": DATA_DATE.isoformat(), "full_rerun": full,
           "picks": [picks[s] for s in STY if s in picks], "changes": changes or (["首次建立"] if full and not old else [])}
    json.dump(old, open(OP, "w"), ensure_ascii=False, indent=1)
OFF = {p["style"]: p for p in old["picks"]}
offr = {s: F[p["code"]] for s, p in OFF.items() if p["code"] in F and F[p["code"]].get("perf")}
W8 = weights(offr)
nq = [(DATA_DATE.year + (1 if m <= DATA_DATE.month and (m, RB["day"]) <= (DATA_DATE.month, DATA_DATE.day) else 0), m) for m in RB["months"]]
nxt = min(dt.date(y, m, RB["day"]) for y, m in nq if dt.date(y, m, RB["day"]) > DATA_DATE)

def card(r, s):
    o = OFF.get(s) if OFF.get(s, {}).get("code") == r["code"] else None
    return {"style": s, "code": r["code"], "name": r["name"], "type": r["type"], "mgr": r["mgr"], "tenure": r["tenure"], "size": r["size"],
            "fee": r["fee"], "score": r.get("score"), "sub": r.get("sub"), "r3y": r["perf"]["r3y"], "mdd": r["perf"]["mdd"], "vol": r["perf"]["vol"],
            "roll_win": r.get("roll_win"), "years": {str(y): r["perf"][str(y)] for y in YEARS}, "purity": r.get("purity"), "dev": r.get("dev"),
            "overlap": r.get("overlap"), "turnover": r.get("turnover"), "feat": {k: (round(v, 2) if v is not None else None) for k, v in r["feat"].items()},
            "top3_sector": r.get("top3_sector"), "last_q": r["quarters"][-1], "nq": len(r["quarters"]), "scale_mom": r["scale_mom"],
            "triggers": trig(r, o) if o else None, "tie_note": r.get("tie_note"), "g4_why": r.get("g4_why")}
out = {
    "data_date": DATA_DATE.isoformat(), "updated_at": dt.datetime.utcnow().replace(microsecond=0) .__add__(dt.timedelta(hours=8)).strftime("%Y-%m-%d %H:%M"),
    "fetched_at": RAW["fetched_at"], "sources": ["天天基金/东方财富基金F10", "TradingView个股指标"],
    "universe": RAW.get("counts", {}), "funnel": FUNNEL, "years": YEARS,
    "official": old | {"next_rebalance": nxt.isoformat(), "weights": W8,
        "cards": [card(offr[s], s) for s in STY if s in offr]},
    "candidates": {s: [card(r, s) for r in CANDS[s][:5]] for s in STY},
    "check": CHECK, "empty": [s for s in STY if not CANDS[s]],
    "fails": {s: {} for s in STY}, "quant_excluded": EXCL,
    "overlap_dist": {k: OVD[int(q * (len(OVD) - 1))] for k, q in [("p10", .1), ("p25", .25), ("median", .5), ("p75", .75), ("p90", .9)]} | {"n": len(OVD)},
    "turnover_cov": {"有换手率": sum(1 for r in pool if r.get("turnover") is not None), "过准入": len(pool) + EXCL, "年报": 2025},
    "config": C,
}
for r in pool:
    if r["style"] and not (r["g2"] and r["g3"] and r.get("g4")):
        why = r["g2_why"] if not r["g2"] else (r["g3_why"] if not r["g3"] else r["g4_why"])
        for w in why.split("；"):
            k = w.split("：")[0][:14]; out["fails"][r["style"]][k] = out["fails"][r["style"]].get(k, 0) + 1
json.dump(out, open(os.path.join(ROOT, "data", "latest.json"), "w"), ensure_ascii=False, indent=1)
print(json.dumps({"funnel": FUNNEL, "empty": out["empty"], "official": [(c["style"], c["code"], c["name"], c["score"], W8.get(c["style"])) for c in out["official"]["cards"]], "check": {k: CHECK[k] for k in ["log", "avg_corr", "corr_dist"]}, "fails": out["fails"], "ovd": out["overlap_dist"], "cov": out["turnover_cov"], "quant": EXCL}, ensure_ascii=False, indent=1))
