"""林部基金公司硬门槛：仅混合型基金管理规模前二十名的基金公司可入选。"""
import json, re

def norm(name):
    if not name:
        return ""
    s = str(name).strip()
    s = s.replace("（", "(").replace("）", ")")
    s = re.sub(r"\s+", "", s)
    return s

def load_whitelist(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    rows = data.get("top20") or []
    if len(rows) != 20:
        raise ValueError("白名单 top20 条数不是 20，而是 %s" % len(rows))
    ranks = [r.get("rank") for r in rows]
    if ranks != list(range(1, 21)):
        raise ValueError("白名单 rank 必须是 1 到 20 连续")
    index = {}
    for row in rows:
        names = [row.get("company")] + list(row.get("aliases") or [])
        for n in names:
            key = norm(n)
            if not key:
                continue
            prev = index.get(key)
            if prev and prev.get("company") != row.get("company"):
                raise ValueError("别名冲突：%s 同时指向 %s 与 %s" % (n, prev.get("company"), row.get("company")))
            index[key] = row
    data["_index"] = index
    return data

def check(company, whitelist):
    """返回 {pass, reason, matched, rank, mixed_yi}。缺公司名或不在前二十一律不通过。"""
    if whitelist is None:
        return {"pass": False, "reason": "白名单未加载", "matched": None, "rank": None, "mixed_yi": None}
    key = norm(company)
    if not key:
        return {"pass": False, "reason": "缺基金管理人", "matched": None, "rank": None, "mixed_yi": None}
    index = whitelist.get("_index") or {}
    row = index.get(key)
    if row is None and not key.endswith("基金"):
        row = index.get(key + "基金")
    if row is None:
        return {
            "pass": False,
            "reason": "基金公司不在混合型规模前二十",
            "matched": None,
            "rank": None,
            "mixed_yi": None,
        }
    return {
        "pass": True,
        "reason": "",
        "matched": row.get("company"),
        "rank": row.get("rank"),
        "mixed_yi": row.get("mixed_yi"),
    }
