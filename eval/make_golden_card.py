"""Aside-owned reference for the Evidence Mate calculation rules (docs/build-blueprint.md rev 3, section 3.3).
Independent of the product code: it does not parse Korean. Each fixed claim below carries a hand-written spec;
this script computes the expected numbers from the input files and writes eval/golden_card.json.
Run: python3 eval/make_golden_card.py   (standard library only)
Product code must not import this file or copy numbers from the golden file.
"""
from __future__ import annotations
import csv, hashlib, json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
HUB = "inputs/hub_card_by_biz_sex.csv"
S24 = "samples/SYNTHETIC_card_emd_v02_202406.csv"
S25 = "samples/SYNTHETIC_card_emd_v02_202506.csv"
CANON = {"base_year_month": "month", "biz_nm": "biz", "user_count": "users", "user_cnt": "users",
         "use_count": "uses", "use_cnt": "uses", "use_amount": "amount", "use_amt": "amount"}
GROUPS = {"resident": ["제주도민"], "domestic": ["내국인"], "foreign": ["중국", "일본", "동남아", "기타외국"], "corporate": ["법인"]}
GROUPS["visitors"] = GROUPS["domestic"] + GROUPS["foreign"]
GROUPS["all"] = sum((GROUPS[g] for g in ("resident", "domestic", "foreign", "corporate")), [])
ORDER = ["resident", "domestic", "foreign", "corporate"]

def load(files):
    rows = []
    for f in files:
        with (ROOT / f).open(encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                row = {CANON.get(k, k): v for k, v in r.items()}
                try:
                    row["users"], row["uses"], row["amount"] = int(row["users"]), int(row["uses"]), int(row["amount"])
                except (ValueError, TypeError):
                    continue
                rows.append(row)
    return rows

def pct(num, den):
    if den == 0:
        return None
    return str((Decimal(num) * 100 / Decimal(den)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))

def total(rows, month, biz=None, group="all", measure="amount", bjd=None):
    t, n = 0, 0
    for r in rows:
        if r["month"] != month or (biz and r["biz"] != biz) or (bjd and r.get("bjd") != bjd) or r["user_type"] not in GROUPS[group]:
            continue
        t += r[measure]; n += 1
    return t, n

def prev_year(month):
    return f"{int(month[:4]) - 1}{month[4:]}"

def summary(rows, month, biz, bjd=None, export_check=False):
    groups = []
    for g in ORDER:
        vals = {m: total(rows, month, biz, g, m, bjd)[0] for m in ("users", "uses", "amount")}
        n = total(rows, month, biz, g, "amount", bjd)[1]
        groups.append({"group": g, "rows": n, **vals})
    tot = {m: sum(g[m] for g in groups) for m in ("users", "uses", "amount")}
    for g in groups:
        g["amount_share_pct"] = pct(g["amount"], tot["amount"])
    out = {"month": month, "biz": biz, "bjd": bjd, "groups": groups, "total": tot}
    exp = {"applied": export_check, "masked_groups": [], "totals_hidden": False}
    if export_check:
        for g in groups:
            if g["rows"] > 0 and min(g["users"], g["uses"], g["amount"]) < 10:
                exp["masked_groups"].append(g["group"])
                g.update({"users": None, "uses": None, "amount": None, "masked": True})
        if exp["masked_groups"]:
            exp["totals_hidden"] = True
            out["total"] = None
            for g in groups:
                g["amount_share_pct"] = None
    out["export"] = exp
    return out

def compare(rows, month, biz, a, b, measure, bjd=None, export_check=False):
    va, vb = total(rows, month, biz, a, measure, bjd)[0], total(rows, month, biz, b, measure, bjd)[0]
    out = {"month": month, "biz": biz, "bjd": bjd, "measure": measure, "a": {"group": a, "value": va}, "b": {"group": b, "value": vb},
           "diff": va - vb, "pct_vs_b": pct(va - vb, vb), "export": {"applied": export_check, "masked": False}}
    verdict = "supported" if va > vb else "revise"
    if export_check and min(va, vb) < 10:
        out["a"]["value"] = out["b"]["value"] = out["diff"] = out["pct_vs_b"] = None
        out["export"]["masked"] = True; verdict = "none"
    return out, verdict

def yoy(rows, month, biz, group, measure, direction, bjd=None, export_check=False):
    pm = prev_year(month)
    cur, prev = total(rows, month, biz, group, measure, bjd)[0], total(rows, pm, biz, group, measure, bjd)[0]
    out = {"month": month, "prev_month": pm, "biz": biz, "bjd": bjd, "group": group, "measure": measure, "current": cur, "previous": prev,
           "diff": cur - prev, "pct": pct(cur - prev, prev), "export": {"applied": export_check, "masked": False}}
    actual = "increase" if cur > prev else "decrease" if cur < prev else "flat"
    verdict = "supported" if actual == direction else "revise"
    if export_check and min(cur, prev) < 10:
        out["current"] = out["previous"] = out["diff"] = out["pct"] = None
        out["export"]["masked"] = True; verdict = "none"
    return out, verdict

def rank(rows, month, measure, asked_biz, asked_rank=1, group="all"):
    sums = {}
    for r in rows:
        if r["month"] == month and r["user_type"] in GROUPS[group]:
            sums[r["biz"]] = sums.get(r["biz"], 0) + r[measure]
    order = sorted(sums.items(), key=lambda kv: (-kv[1], kv[0]))
    top = [{"rank": i + 1, "biz": b, "value": v} for i, (b, v) in enumerate(order[:5])]
    actual = next(i + 1 for i, (b, _) in enumerate(order) if b == asked_biz)
    out = {"month": month, "group": group, "measure": measure, "top": top, "asked": {"biz": asked_biz, "rank": actual}}
    return out, ("supported" if actual == asked_rank else "revise")

def sha(f):
    return hashlib.sha256((ROOT / f).read_bytes()).hexdigest()

def build():
    hub, c25, c2425 = load([HUB]), load([S25]), load([S24, S25])
    items = []
    def add(i, files, q, behavior, verdict, expect, note=""):
        items.append({"id": i, "files": files, "question": q, "behavior": behavior, "verdict": verdict, "expect": expect, "note": note})
    add("H01", [HUB], "2025년 6월 한식 음식점업 카드 이용 현황을 알려 주세요", "summary", "none", summary(hub, "202506", "한식 음식점업"))
    d, v = compare(hub, "202506", "한식 음식점업", "domestic", "resident", "amount"); add("H02", [HUB], "한식 음식점업은 내국인 관광객이 도민보다 카드를 더 많이 썼다", "claim_check", v, d, "month defaults to the latest month in the file")
    d, v = compare(hub, "202506", "자동차 임대업", "domestic", "resident", "amount"); add("H03", [HUB], "자동차 임대업은 내국인 관광객이 도민보다 이용금액이 많다", "claim_check", v, d)
    d, v = compare(hub, "202506", "호텔업", "foreign", "domestic", "amount"); add("H04", [HUB], "호텔업은 외국인이 내국인 관광객보다 많이 썼다", "claim_check", v, d)
    add("H05", [HUB], "한식당은 관광객이 도민보다 많이 쓴다", "ask_scope", "none", {"slot": "group", "choices": ["내국인 관광객", "외국인", "관광객 전체"]}, "'관광객' alone is ambiguous; '한식당' is an alias of 한식 음식점업")
    d, v = yoy(hub, "202506", "면세점", "all", "amount", "increase"); add("H06", [HUB], "면세점 카드 이용금액이 작년 같은 달보다 늘었다", "claim_check", v, d)
    d, v = yoy(hub, "202506", "체인화 편의점", "all", "amount", "increase"); add("H07", [HUB], "2025년 6월 체인화 편의점 카드 이용금액은 작년 같은 달보다 늘었다", "claim_check", v, d)
    d, v = rank(hub, "202506", "amount", "한식 음식점업"); add("H08", [HUB], "2025년 6월 카드 이용금액이 가장 큰 업종은 한식 음식점업이다", "claim_check", v, d)
    d, v = rank(hub, "202506", "amount", "호텔업"); add("H09", [HUB], "2025년 6월 카드 이용금액 1위 업종은 호텔업이다", "claim_check", v, d)
    add("H10", [HUB], "노형동 한식 음식점업 카드 이용금액을 알려 주세요", "need_file", "none", {"missing": "region", "dataset": "카드 이용 현황(읍면동)_v02", "month": None}, "the public file has no region column")
    add("H11", [HUB], "2025년 9월 한식 음식점업 카드 이용 현황", "need_file", "none", {"missing": "month", "dataset": None, "month": "202509"}, "the loaded file ends at 202506")
    add("H12", [HUB], "한식 음식점업 전체 매출은 얼마인가요", "cannot", "none", {"limit": "total_market"})
    add("H13", [HUB], "면세점 카드 이용금액은 왜 줄었나요", "cannot", "none", {"limit": "cause"})
    add("H14", [HUB], "내년에 호텔업 카드 이용금액이 늘까요", "cannot", "none", {"limit": "forecast"})
    add("H15", [HUB], "제주에 한식 음식점이 몇 곳인가요", "cannot", "none", {"limit": "store_count"})
    add("H16", [HUB], "식당 카드 이용 현황을 알려 주세요", "ask_scope", "none", {"slot": "biz", "choices": ["한식 음식점업", "중식 음식점업", "일식 음식점업", "서양식 음식점업", "기타 외국식 음식점업", "피자 햄버거 샌드위치 및 유사 음식점업"]})
    d, v = compare(hub, "202506", "비알콜 음료점업", "resident", "domestic", "uses"); add("H17", [HUB], "비알콜 음료점업 이용건수는 도민이 내국인 관광객보다 많다", "claim_check", v, d)
    d, v = compare(hub, "202406", "골프장 운영업", "corporate", "resident", "amount"); add("H18", [HUB], "2024년 6월 골프장 운영업은 법인이 도민보다 많이 썼다", "claim_check", v, d)
    d, v = compare(hub, "202506", "슈퍼마켓", "resident", "domestic", "users"); add("H19", [HUB], "슈퍼마켓 이용자 수는 도민이 내국인 관광객보다 많다", "claim_check", v, d, "measure users: notice users_not_unique is required")
    d, v = yoy(hub, "202506", "한식 음식점업", "resident", "amount", "decrease"); add("H20", [HUB], "한식 음식점업의 도민 카드 이용금액은 작년 같은 달보다 줄었다", "claim_check", v, d)
    add("C01", [S25], "노형동 한식 음식점업 카드 이용 현황을 알려 주세요", "summary", "none", summary(c25, "202506", "한식 음식점업", "노형동", True), "center format: export pre-check on")
    add("C02", [S25], "성산읍 스포츠 및 레크레이션 용품 임대업 카드 이용 현황", "summary", "none", summary(c25, "202506", "스포츠 및 레크레이션 용품 임대업", "성산읍", True), "small cells must be masked and totals hidden")
    d, v = compare(c25, "202506", "한식 음식점업", "domestic", "resident", "amount", "노형동", True); add("C03", [S25], "노형동 한식 음식점업은 내국인 관광객이 도민보다 많이 썼다", "claim_check", v, d)
    add("C04", [S25], "한림읍 체인화 편의점 카드 이용금액이 작년 같은 달보다 늘었다", "need_file", "none", {"missing": "month", "dataset": "카드 이용 현황(읍면동)_v02", "month": "202406"}, "only 202506 is loaded")
    d, v = yoy(c2425, "202506", "체인화 편의점", "all", "amount", "increase", "한림읍", True); add("C05", [S24, S25], "한림읍 체인화 편의점 카드 이용금액이 작년 같은 달보다 늘었다", "claim_check", v, d, "both months loaded")
    d, v = compare(c25, "202506", "일식 음식점업", "foreign", "resident", "users", "대정읍", True); add("C06", [S25], "대정읍 일식 음식점업 이용자 수는 외국인이 도민보다 많다", "claim_check", v, d)
    gold = {"title": "Evidence Mate golden (card data)", "generated_by": "eval/make_golden_card.py", "rules": "docs/build-blueprint.md rev 3 section 3.3",
            "sources": {f: sha(f) for f in (HUB, S24, S25)}, "items": items}
    (ROOT / "eval/golden_card.json").write_text(json.dumps(gold, ensure_ascii=False, indent=1), encoding="utf-8")
    return gold

if __name__ == "__main__":
    g = build()
    for it in g["items"]:
        e = it["expect"]; brief = {k: e[k] for k in list(e)[:0]}
        if it["behavior"] == "claim_check":
            brief = {k: (e[k] if not isinstance(e[k], dict) else e[k].get("value", e[k].get("rank"))) for k in ("a", "b", "pct_vs_b", "current", "previous", "pct", "asked") if k in e}
        elif it["behavior"] == "summary":
            brief = {"groups": [(x["group"], x["amount"], x["amount_share_pct"]) for x in e["groups"]], "export": e["export"]}
        else:
            brief = e
        print(it["id"], it["behavior"], it["verdict"], json.dumps(brief, ensure_ascii=False))
