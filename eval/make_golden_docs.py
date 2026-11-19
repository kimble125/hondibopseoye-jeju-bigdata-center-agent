"""Aside-owned reference for the document workflow (docs/build-blueprint-rev3.md section 10).
Computes the expected numbers of the two document templates from the bundled public files and writes eval/golden_docs.json.
Run: python3 eval/make_golden_docs.py   (standard library only). Product code must not import this file or copy numbers.
"""
from __future__ import annotations
import csv, hashlib, json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import make_golden_card as ref   # same folder; reuses load(), total(), summary(), GROUPS, ORDER
ROOT = Path(__file__).resolve().parent.parent
HUB, S25 = ref.HUB, ref.S25
F_SEXAGE, F_WEEK, F_TIME = "inputs/hub_card_by_biz_sex_age_quarter.csv", "inputs/hub_card_by_weekday.csv", "inputs/hub_card_by_time.csv"
WEEK = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일", "공휴일"]
TIME = ["오전", "점심", "오후", "저녁", "밤"]
AGES = ["10대", "20대", "30대", "40대", "50대", "60대", "70대 이상", "알수없음"]
SEX = ["남성", "여성", "알수없음"]

def q(x, places):
    return str(Decimal(x).quantize(Decimal(places), rounding=ROUND_HALF_UP))
def pct(num, den, places="0.01"):
    return None if den == 0 else q(Decimal(num) * 100 / Decimal(den), places)
def div_int(num, den):
    return None if den == 0 else int((Decimal(num) / Decimal(den)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
def shift(month, k):
    y, m = int(month[:4]), int(month[4:]); n = y * 12 + (m - 1) + k
    return f"{n // 12}{n % 12 + 1:02d}"
def read(f):
    with (ROOT / f).open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))

def biz_change(rows, cur, prev, group):
    names = sorted({r["biz"] for r in rows if "?" not in r["biz"]})
    items = []
    for b in names:
        c, p = ref.total(rows, cur, b, group)[0], ref.total(rows, prev, b, group)[0]
        if c > 0 and p > 0:
            items.append((Decimal(c - p) * 100 / Decimal(p), b, c, p))
    up = sorted(items, key=lambda t: (-t[0], t[1])); down = sorted(items, key=lambda t: (t[0], t[1]))
    fmt = lambda t: {"biz": t[1], "pct": q(t[0], "0.01"), "current": t[2], "previous": t[3]}
    return {"n_biz": len(items), "increase_count": sum(1 for t in items if t[2] > t[3]), "decrease_count": sum(1 for t in items if t[2] < t[3]),
            "flat_count": sum(1 for t in items if t[2] == t[3]), "top_up": [fmt(t) for t in up[:5]], "top_down": [fmt(t) for t in down[:5]]}

def consumption_trend(rows, month, group):
    pm, ym = shift(month, -1), shift(month, -12)
    amt = {k: ref.total(rows, m, None, group, "amount")[0] for k, m in (("current", month), ("previous", pm), ("year_ago", ym))}
    uses = {k: ref.total(rows, m, None, group, "uses")[0] for k, m in (("current", month), ("previous", pm), ("year_ago", ym))}
    return {"month": month, "prev_month": pm, "yoy_month": ym, "group": group,
            "headline": {"amount": amt, "pct_mom": pct(amt["current"] - amt["previous"], amt["previous"]), "pct_yoy": pct(amt["current"] - amt["year_ago"], amt["year_ago"]),
                         "uses": uses, "per_use": {k: div_int(amt[k], uses[k]) for k in amt}},
            "biz_mom": biz_change(rows, month, pm, group), "biz_yoy": biz_change(rows, month, ym, group)}

def bizplan_market(rows, biz, sexage, week, time, local=None):
    month = max(r["month"] for r in rows)
    win = [shift(month, -k) for k in range(11, -1, -1)]; prev_win = [shift(m, -12) for m in win]
    series = [{"month": m, "amount": ref.total(rows, m, biz)[0]} for m in win]
    a12 = sum(s["amount"] for s in series); p12 = sum(ref.total(rows, m, biz)[0] for m in prev_win)
    mix_amt = {g: sum(ref.total(rows, m, biz, g)[0] for m in win) for g in ref.ORDER}; mt = sum(mix_amt.values())
    cur, prev = ref.total(rows, month, biz)[0], ref.total(rows, shift(month, -12), biz)[0]
    mx = max(series, key=lambda s: (s["amount"], -int(s["month"]))); mn = min(series, key=lambda s: (s["amount"], int(s["month"])))
    out = {"biz": biz, "month": month, "window": {"start": win[0], "end": win[-1]},
           "size": {"amount_12m": a12, "monthly_avg": div_int(a12, 12), "prev_amount_12m": p12, "pct_12m": pct(a12 - p12, p12, "0.1")},
           "series": series, "yoy": {"current": cur, "previous": prev, "pct": pct(cur - prev, prev, "0.1")},
           "mix": [{"group": g, "amount": mix_amt[g], "share_pct": pct(mix_amt[g], mt, "0.1")} for g in ref.ORDER],
           "per_use": div_int(cur, ref.total(rows, month, biz, "all", "uses")[0]),
           "season": {"max": mx, "min": mn}}
    qs = sorted({(r["base_year"], r["base_quarter"]) for r in sexage})[-4:]
    sub = [r for r in sexage if r["biz_name"] == biz and (r["base_year"], r["base_quarter"]) in qs]
    if sub:
        tot = sum(int(r["use_amout_by_million"]) for r in sub)
        by_age = [{"age": a, "amount_million": sum(int(r["use_amout_by_million"]) for r in sub if r["age_range"] == a)} for a in AGES]
        by_sex = [{"sex": s, "amount_million": sum(int(r["use_amout_by_million"]) for r in sub if r["sex"] == s)} for s in SEX]
        for x in by_age + by_sex:
            x["share_pct"] = pct(x["amount_million"], tot, "0.1")
        out["sex_age"] = {"quarters": [f"{y} {qq}" for y, qq in qs], "by_age": by_age, "by_sex": by_sex}
    else:
        out["sex_age"] = None
    wm = max(r["base_year_month"] for r in week); wt = {d: sum(int(r["use_count"]) for r in week if r["base_year_month"] == wm and r["day_of_week"] == d) for d in WEEK}
    tm = max(r["base_year_month"] for r in time); tt = {t: sum(int(r["use_amout_by_million"]) for r in time if r["base_year_month"] == tm and r["time_type"] == t) for t in TIME}
    out["context"] = {"weekday": {"month": wm, "shares": [{"day": d, "uses": wt[d], "share_pct": pct(wt[d], sum(wt.values()), "0.1")} for d in WEEK]},
                      "time": {"month": tm, "shares": [{"time": t, "amount_million": tt[t], "share_pct": pct(tt[t], sum(tt.values()), "0.1")} for t in TIME]}}
    out["local"] = local
    return out

def build():
    hub = ref.load([HUB]); sexage, week, time = read(F_SEXAGE), read(F_WEEK), read(F_TIME); c25 = ref.load([S25])
    items = []
    def add(i, files, request, template, params, expect, note=""):
        items.append({"id": i, "files": files, "request": request, "template": template, "params": params, "expect": expect, "note": note})
    add("D01", [], "2025년 6월 소비동향 현황자료를 만들어 주세요", "consumption_trend", {"month": "202506", "group": "all"}, consumption_trend(hub, "202506", "all"))
    add("D02", [], "2025년 6월 내국인 관광객 소비동향 현황자료를 만들어 주세요", "consumption_trend", {"month": "202506", "group": "domestic"}, consumption_trend(hub, "202506", "domestic"))
    add("D03", [], "한식 음식점업으로 사업계획서 시장 현황을 써 주세요", "bizplan_market", {"biz": "한식 음식점업"}, bizplan_market(hub, "한식 음식점업", sexage, week, time))
    add("D04", [], "렌터카 사업계획서에 넣을 시장 현황을 써 주세요", "bizplan_market", {"biz": "자동차 임대업"}, bizplan_market(hub, "자동차 임대업", sexage, week, time), "alias 렌터카")
    local = {"bjd": "노형동", "month": "202506", "summary": ref.summary(c25, "202506", "한식 음식점업", "노형동", True),
             "need": [{"dataset": "카드 이용 현황(읍면동)_v02", "month": "202406", "why": "전년 동월 비교"}]}
    add("D05", [S25], "노형동 한식 음식점업 사업계획서 시장 현황을 써 주세요", "bizplan_market", {"biz": "한식 음식점업", "bjd": "노형동"}, bizplan_market(hub, "한식 음식점업", sexage, week, time, local),
        "province-level sections come from the bundled public files; the local section comes from the loaded center-format file (synthetic here) with the export pre-check")
    add("D06", [], "사업계획서 시장 현황을 써 주세요", "ask_scope", {}, {"slot": "biz"}, "no business named: ask which business")
    srcs = [HUB, F_SEXAGE, F_WEEK, F_TIME, S25]
    gold = {"title": "Evidence Mate golden (documents)", "generated_by": "eval/make_golden_docs.py", "rules": "docs/build-blueprint-rev3.md section 10",
            "sources": {f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest() for f in srcs}, "items": items}
    (ROOT / "eval/golden_docs.json").write_text(json.dumps(gold, ensure_ascii=False, indent=1), encoding="utf-8")
    return gold

if __name__ == "__main__":
    g = build()
    d1 = g["items"][0]["expect"]; print("D01", d1["headline"], d1["biz_mom"]["n_biz"], d1["biz_mom"]["increase_count"], d1["biz_mom"]["decrease_count"], [x["biz"] + " " + x["pct"] for x in d1["biz_mom"]["top_up"][:3]])
    d2 = g["items"][1]["expect"]; print("D02", d2["headline"]["pct_mom"], d2["headline"]["pct_yoy"])
    for k in (2, 3):
        d = g["items"][k]["expect"]; print(g["items"][k]["id"], d["size"], d["yoy"], [(m["group"], m["share_pct"]) for m in d["mix"]], d["per_use"], d["season"], d["sex_age"] and [(a["age"], a["share_pct"]) for a in d["sex_age"]["by_age"]], d["sex_age"] and d["sex_age"]["quarters"])
    print("ctx", [(s["day"], s["share_pct"]) for s in d["context"]["weekday"]["shares"]], [(s["time"], s["share_pct"]) for s in d["context"]["time"]["shares"]])


# ---- rev 3.3 additions: data_brief, generic profile, dataset recommendation (blueprint section 10.8) ----
CATEGORY_SUFFIX = ("_id", "_cd", "_code", "_no", "_hour", "_nm", "_name")
CATEGORY_NAMES = {"age", "sex", "week", "time", "grid"}

def profile(path):
    with (ROOT / path).open(encoding="utf-8-sig", newline="") as fh:
        rd = csv.reader(fh); header = [h.strip() for h in next(rd)]; rows = [r for r in rd if r]
    cols, period = [], None
    for i, name in enumerate(header):
        vals = [r[i].strip() for r in rows if i < len(r) and r[i].strip() not in ("", "NA", "NULL")]
        low = name.lower(); distinct = sorted(set(vals))
        def top():
            cnt = {}
            for v in vals:
                cnt[v] = cnt.get(v, 0) + 1
            return [{"value": v, "count": c} for v, c in sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0]))[:5]]
        col = {"name": name, "non_empty": len(vals), "distinct": len(distinct)}
        if any(k in low for k in ("date", "month", "year")) and vals and all(v.isdigit() and len(v) in (4, 6, 8) for v in vals):
            col.update({"type": "date", "min": distinct[0], "max": distinct[-1]})
            if period is None:
                period = {"column": name, "min": distinct[0], "max": distinct[-1]}
        elif low.endswith(CATEGORY_SUFFIX) or low in CATEGORY_NAMES:
            col.update({"type": "category", "top": top()})
        else:
            try:
                nums = [Decimal(v) for v in vals]
                if not nums:
                    raise ValueError
                col.update({"type": "number", "sum": format(sum(nums), "f"), "min": format(min(nums), "f"), "max": format(max(nums), "f")})
            except Exception:
                col.update({"type": "category", "top": top()} if len(distinct) <= 50 else {"type": "text"})
        cols.append(col)
    return {"rows": len(rows), "columns": cols, "period": period}

def recommend(sentence):
    cat = json.loads((ROOT / "inputs/report_catalog.json").read_text(encoding="utf-8"))
    scored = [(sum(1 for k in d["keywords"] if k in sentence), i, d) for i, d in enumerate(cat["datasets"])]
    keep = sorted([s for s in scored if s[0] > 0], key=lambda s: (-s[0], s[1]))
    return {"datasets": [{"id": d["id"], "label": d["label"], "score": sc} for sc, _, d in keep]}

def data_brief(rows, month, biz, bjd=None, export_check=False, dataset=None):
    y, v = ref.yoy(rows, month, biz, "all", "amount", "increase", bjd, export_check)
    have_prev = any(r["month"] == ref.prev_year(month) for r in rows)
    out = {"summary": ref.summary(rows, month, biz, bjd, export_check), "yoy": y if have_prev else None,
           "need": [] if have_prev else [{"dataset": dataset, "month": ref.prev_year(month), "why": "전년 동월 비교"}]}
    return out

def build_more():
    gold = json.loads((ROOT / "eval/golden_docs.json").read_text(encoding="utf-8"))
    hub, c25 = ref.load([HUB]), ref.load([S25]); BUS = "samples/SYNTHETIC_bus_station_usage_202611.csv"
    def add(i, files, request, template, params, expect, note=""):
        gold["items"].append({"id": i, "files": files, "request": request, "template": template, "params": params, "expect": expect, "note": note})
    add("D07", [], "한식 음식점업 자료 요약을 만들어 주세요", "data_brief", {"biz": "한식 음식점업"}, data_brief(hub, "202506", "한식 음식점업"), "trigger words: 자료 요약, 요약 자료, 요약해")
    add("D08", [S25], "노형동 한식 음식점업 자료 요약을 만들어 주세요", "data_brief", {"biz": "한식 음식점업", "bjd": "노형동"}, data_brief(c25, "202506", "한식 음식점업", "노형동", True, "카드 이용 현황(읍면동)_v02"), "active center-format table; previous-year month not loaded")
    add("P01", [BUS], "이 자료를 요약해 주세요", "profile", {}, profile(BUS), "unknown header -> generic table -> profile only")
    add("R01", [], "카페 창업 사업계획서를 쓰려는데 어떤 데이터를 받아야 하나요", "recommend_data", {}, recommend("카페 창업 사업계획서를 쓰려는데 어떤 데이터를 받아야 하나요"))
    add("R02", [], "우리 마을 버스 정류소 이용 현황을 보려면 무슨 자료가 필요한가요", "recommend_data", {}, recommend("우리 마을 버스 정류소 이용 현황을 보려면 무슨 자료가 필요한가요"))
    gold["sources"][BUS] = hashlib.sha256((ROOT / BUS).read_bytes()).hexdigest()
    gold["sources"]["inputs/report_catalog.json"] = hashlib.sha256((ROOT / "inputs/report_catalog.json").read_bytes()).hexdigest()
    (ROOT / "eval/golden_docs.json").write_text(json.dumps(gold, ensure_ascii=False, indent=1), encoding="utf-8")
    return gold

if __name__ == "__main__":
    g = build_more()
    for it in g["items"][6:]:
        e = it["expect"]
        print(it["id"], it["template"], json.dumps(e if it["template"] == "recommend_data" else ({"rows": e["rows"], "cols": [(c["name"], c["type"]) for c in e["columns"]], "period": e["period"]} if it["template"] == "profile" else {"yoy": e["yoy"] and e["yoy"]["pct"], "need": e["need"]}), ensure_ascii=False)[:420])
    print("items", len(g["items"]))
