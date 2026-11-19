"""Calculation rules R1-R9 (section 3.3) and D-rules (section 10.3, 10.8).
Every number shown by the product comes from this module. Sums are int; percentages are
decimal strings rounded once with ROUND_HALF_UP; "cannot be computed" / "hidden" is None."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

from .catalog import GROUP_SETS, ORDER, MEASURES

MASK_THRESHOLD = 10


# ---- helpers ---------------------------------------------------------------------------------------
def quant(x, places: str = "0.1") -> str:
    return str(Decimal(x).quantize(Decimal(places), rounding=ROUND_HALF_UP))


def pct(num, den, places: str = "0.1"):
    if den == 0:
        return None
    return quant(Decimal(num) * 100 / Decimal(den), places)


def div_int(num, den):
    if den == 0:
        return None
    return int((Decimal(num) / Decimal(den)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def to_million(value):
    """Whole million won (display helper, ROUND_HALF_UP)."""
    if value is None:
        return None
    return int((Decimal(value) / Decimal(1000000)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def shift(month: str, k: int) -> str:
    y, m = int(month[:4]), int(month[4:6])
    n = y * 12 + (m - 1) + k
    return f"{n // 12}{n % 12 + 1:02d}"


def prev_year(month: str) -> str:
    return shift(month, -12)


def _match(r, month, biz, place, gset):
    if r.get("month") != month:
        return False
    if biz is not None and r.get("biz") != biz:
        return False
    if place is not None and r.get(place[0]) != place[1]:
        return False
    return r.get("user_type") in gset


def total(rows, month, biz=None, group="all", measure="amount", place=None):
    """R1: (sum, number of source rows)."""
    gset = GROUP_SETS[group]
    t = n = 0
    for r in rows:
        if _match(r, month, biz, place, gset):
            t += r[measure]
            n += 1
    return t, n


def totals(rows, month, biz=None, group="all", place=None):
    """All three measures and the row count in one pass."""
    gset = GROUP_SETS[group]
    out = {"users": 0, "uses": 0, "amount": 0, "rows": 0}
    for r in rows:
        if _match(r, month, biz, place, gset):
            out["users"] += r["users"]
            out["uses"] += r["uses"]
            out["amount"] += r["amount"]
            out["rows"] += 1
    return out


def place_value(place):
    return place[1] if place else None


# ---- R3 summary + R8 -------------------------------------------------------------------------------
def summary(rows, month, biz, place=None, export_check=False):
    groups = []
    for g in ORDER:
        t = totals(rows, month, biz, g, place)
        groups.append({"group": g, "rows": t["rows"], "users": t["users"], "uses": t["uses"], "amount": t["amount"]})
    tot = {m: sum(g[m] for g in groups) for m in MEASURES}
    for g in groups:
        g["amount_share_pct"] = pct(g["amount"], tot["amount"])
    out = {"month": month, "biz": biz, "bjd": place_value(place), "groups": groups, "total": tot}
    exp = {"applied": bool(export_check), "masked_groups": [], "totals_hidden": False}
    if export_check:
        for g in groups:
            if g["rows"] > 0 and min(g["users"], g["uses"], g["amount"]) < MASK_THRESHOLD:
                exp["masked_groups"].append(g["group"])
                g.update({"users": None, "uses": None, "amount": None, "masked": True})
        if exp["masked_groups"]:
            exp["totals_hidden"] = True
            out["total"] = None
            for g in groups:
                g["amount_share_pct"] = None
    out["export"] = exp
    rows_used = sum(g["rows"] for g in groups)
    return out, rows_used


# ---- R4 comparison ---------------------------------------------------------------------------------
def compare(rows, month, biz, a, b, measure, place=None, export_check=False, claim="greater"):
    va, na = total(rows, month, biz, a, measure, place)
    vb, nb = total(rows, month, biz, b, measure, place)
    out = {"month": month, "biz": biz, "bjd": place_value(place), "measure": measure,
           "a": {"group": a, "value": va}, "b": {"group": b, "value": vb},
           "diff": va - vb, "pct_vs_b": pct(va - vb, vb), "export": {"applied": bool(export_check), "masked": False}}
    if claim == "less":
        verdict = "supported" if va < vb else "revise"
    else:
        verdict = "supported" if va > vb else "revise"
    if export_check and min(va, vb) < MASK_THRESHOLD:
        out["a"]["value"] = out["b"]["value"] = out["diff"] = out["pct_vs_b"] = None
        out["export"]["masked"] = True
        verdict = "none"
    return out, verdict, na + nb


def actual_order(data):
    """'greater' | 'less' | 'equal' of a vs b (None when masked)."""
    va, vb = data["a"]["value"], data["b"]["value"]
    if va is None or vb is None:
        return None
    return "greater" if va > vb else "less" if va < vb else "equal"


# ---- R5 year-over-year -----------------------------------------------------------------------------
def yoy(rows, month, biz, group, measure, place=None, export_check=False, direction=None):
    pm = prev_year(month)
    cur, nc = total(rows, month, biz, group, measure, place)
    prev, np_ = total(rows, pm, biz, group, measure, place)
    out = {"month": month, "prev_month": pm, "biz": biz, "bjd": place_value(place), "group": group, "measure": measure,
           "current": cur, "previous": prev, "diff": cur - prev, "pct": pct(cur - prev, prev),
           "export": {"applied": bool(export_check), "masked": False}}
    actual = "increase" if cur > prev else "decrease" if cur < prev else "flat"
    verdict = "none" if direction is None else ("supported" if actual == direction else "revise")
    if export_check and min(cur, prev) < MASK_THRESHOLD:
        out["current"] = out["previous"] = out["diff"] = out["pct"] = None
        out["export"]["masked"] = True
        verdict = "none"
        actual = None
    return out, verdict, nc + np_, actual


# ---- R6 rank ---------------------------------------------------------------------------------------
def rank(rows, month, measure, asked_biz=None, asked_rank=1, group="all", place=None, export_check=False):
    """R6. `place` and `export_check` are used for center tables only; with their defaults the
    result is exactly the public-table shape (no `bjd`, no `export`, B3)."""
    gset = GROUP_SETS[group]
    sums: dict = {}
    n = 0
    for r in rows:
        if (r.get("month") == month and r.get("user_type") in gset
                and (place is None or r.get(place[0]) == place[1])):
            sums[r["biz"]] = sums.get(r["biz"], 0) + r[measure]
            n += 1
    order = sorted(sums.items(), key=lambda kv: (-kv[1], kv[0]))
    top = [{"rank": i + 1, "biz": b, "value": v} for i, (b, v) in enumerate(order[:5])]
    asked = None
    verdict = "none"
    if asked_biz is not None:
        actual = next((i + 1 for i, (b, _) in enumerate(order) if b == asked_biz), None)
        asked = {"biz": asked_biz, "rank": actual}
        verdict = "supported" if actual == asked_rank else "revise"
    out = {"month": month, "group": group, "measure": measure, "top": top, "asked": asked}
    if place is not None:
        out["bjd"] = place[1]
    if export_check:
        # R8 applied to rank: a business whose summed value is below the threshold is hidden;
        # ranks stay (the center's export policy allows ranks).
        small = {b for b, v in sums.items() if v < MASK_THRESHOLD}
        masked = False
        for t in top:
            if t["biz"] in small:
                t["value"] = None
                t["masked"] = True
                masked = True
        if asked is not None and asked_biz in small:
            asked["masked"] = True
            verdict = "none"
            masked = True
        out["export"] = {"applied": True, "masked": masked}
    return out, verdict, n


def rows_in(rows, month, place) -> bool:
    """True when at least one row of that month falls in the place."""
    return any(r.get("month") == month and r.get(place[0]) == place[1] for r in rows)


def top_businesses(rows, month, k=6, measure="amount"):
    sums: dict = {}
    for r in rows:
        if r.get("month") == month and "?" not in r.get("biz", ""):
            sums[r["biz"]] = sums.get(r["biz"], 0) + r[measure]
    return [b for b, _ in sorted(sums.items(), key=lambda kv: (-kv[1], kv[0]))[:k]]


def place_has_rows(rows, place) -> bool:
    return any(r.get(place[0]) == place[1] for r in rows)


# ---- section 10.3: documents ---------------------------------------------------------------------
def _month_biz_sums(rows, group, measure="amount"):
    gset = GROUP_SETS[group]
    out: dict = {}
    for r in rows:
        if r.get("user_type") in gset:
            key = (r["month"], r["biz"])
            out[key] = out.get(key, 0) + r[measure]
    return out


def _month_sums(rows, group, measure, biz=None):
    gset = GROUP_SETS[group]
    out: dict = {}
    for r in rows:
        if r.get("user_type") in gset and (biz is None or r.get("biz") == biz):
            out[r["month"]] = out.get(r["month"], 0) + r[measure]
    return out


def biz_change(sums, names, cur, prev):
    items = []
    for b in names:
        c, p = sums.get((cur, b), 0), sums.get((prev, b), 0)
        if c > 0 and p > 0:
            items.append((Decimal(c - p) * 100 / Decimal(p), b, c, p))
    up = sorted(items, key=lambda t: (-t[0], t[1]))
    down = sorted(items, key=lambda t: (t[0], t[1]))

    def fmt(t):
        return {"biz": t[1], "pct": quant(t[0], "0.01"), "current": t[2], "previous": t[3]}
    return {"n_biz": len(items), "increase_count": sum(1 for t in items if t[2] > t[3]),
            "decrease_count": sum(1 for t in items if t[2] < t[3]), "flat_count": sum(1 for t in items if t[2] == t[3]),
            "top_up": [fmt(t) for t in up[:5]], "top_down": [fmt(t) for t in down[:5]]}


def consumption_trend(rows, month, group):
    pm, ym = shift(month, -1), shift(month, -12)
    amt_m = _month_sums(rows, group, "amount")
    uses_m = _month_sums(rows, group, "uses")
    keys = (("current", month), ("previous", pm), ("year_ago", ym))
    amt = {k: amt_m.get(m, 0) for k, m in keys}
    uses = {k: uses_m.get(m, 0) for k, m in keys}
    sums = _month_biz_sums(rows, group)
    names = sorted({r["biz"] for r in rows if "?" not in r["biz"]})
    return {"month": month, "prev_month": pm, "yoy_month": ym, "group": group,
            "headline": {"amount": amt, "pct_mom": pct(amt["current"] - amt["previous"], amt["previous"], "0.01"),
                         "pct_yoy": pct(amt["current"] - amt["year_ago"], amt["year_ago"], "0.01"),
                         "uses": uses, "per_use": {k: div_int(amt[k], uses[k]) for k in amt}},
            "biz_mom": biz_change(sums, names, month, pm), "biz_yoy": biz_change(sums, names, month, ym)}


WEEK = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일", "공휴일"]
TIMES = ["오전", "점심", "오후", "저녁", "밤"]
AGES = ["10대", "20대", "30대", "40대", "50대", "60대", "70대 이상", "알수없음"]
SEXES = ["남성", "여성", "알수없음"]


def latest_month(rows):
    ms = [r.get("month") for r in rows if r.get("month")]
    return max(ms) if ms else None


def bizplan_market(rows, biz, sexage, week, time, local=None):
    month = latest_month(rows)
    win = [shift(month, -k) for k in range(11, -1, -1)]
    prev_win = [shift(m, -12) for m in win]
    amt_m = _month_sums(rows, "all", "amount", biz)
    uses_m = _month_sums(rows, "all", "uses", biz)
    series = [{"month": m, "amount": amt_m.get(m, 0)} for m in win]
    a12 = sum(s["amount"] for s in series)
    p12 = sum(amt_m.get(m, 0) for m in prev_win)
    mix_amt = {}
    for g in ORDER:
        gm = _month_sums(rows, g, "amount", biz)
        mix_amt[g] = sum(gm.get(m, 0) for m in win)
    mt = sum(mix_amt.values())
    cur, prev = amt_m.get(month, 0), amt_m.get(shift(month, -12), 0)
    mx = max(series, key=lambda s: (s["amount"], -int(s["month"])))
    mn = min(series, key=lambda s: (s["amount"], int(s["month"])))
    out = {"biz": biz, "month": month, "window": {"start": win[0], "end": win[-1]},
           "size": {"amount_12m": a12, "monthly_avg": div_int(a12, 12), "prev_amount_12m": p12,
                    "pct_12m": pct(a12 - p12, p12, "0.1")},
           "series": series, "yoy": {"current": cur, "previous": prev, "pct": pct(cur - prev, prev, "0.1")},
           "mix": [{"group": g, "amount": mix_amt[g], "share_pct": pct(mix_amt[g], mt, "0.1")} for g in ORDER],
           "per_use": div_int(cur, uses_m.get(month, 0)),
           "season": {"max": dict(mx), "min": dict(mn)}}
    out["sex_age"] = sex_age(sexage, biz)
    out["context"] = context(week, time)
    out["local"] = local
    return out


def sex_age(sexage, biz):
    qs = sorted({(r["base_year"], r["base_quarter"]) for r in sexage})[-4:]
    qset = set(qs)
    sub = [r for r in sexage if r.get("biz_name") == biz and (r["base_year"], r["base_quarter"]) in qset]
    if not sub:
        return None
    col = "use_amout_by_million"
    tot = sum(r[col] for r in sub)
    by_age = [{"age": a, "amount_million": sum(r[col] for r in sub if r["age_range"] == a)} for a in AGES]
    by_sex = [{"sex": s, "amount_million": sum(r[col] for r in sub if r["sex"] == s)} for s in SEXES]
    for x in by_age + by_sex:
        x["share_pct"] = pct(x["amount_million"], tot, "0.1")
    return {"quarters": [f"{y} {q}" for y, q in qs], "by_age": by_age, "by_sex": by_sex}


def context(week, time):
    out = {}
    if week:
        wm = max(r["base_year_month"] for r in week)
        wt = {d: 0 for d in WEEK}
        for r in week:
            if r["base_year_month"] == wm and r["day_of_week"] in wt:
                wt[r["day_of_week"]] += r["use_count"]
        ws = sum(wt.values())
        out["weekday"] = {"month": wm, "shares": [{"day": d, "uses": wt[d], "share_pct": pct(wt[d], ws, "0.1")} for d in WEEK]}
    else:
        out["weekday"] = None
    if time:
        tm = max(r["base_year_month"] for r in time)
        tt = {t: 0 for t in TIMES}
        for r in time:
            if r["base_year_month"] == tm and r["time_type"] in tt:
                tt[r["time_type"]] += r["use_amout_by_million"]
        ts = sum(tt.values())
        out["time"] = {"month": tm, "shares": [{"time": t, "amount_million": tt[t], "share_pct": pct(tt[t], ts, "0.1")} for t in TIMES]}
    else:
        out["time"] = None
    return out


def data_brief(rows, month, biz, place=None, export_check=False, dataset=None):
    summ, used = summary(rows, month, biz, place, export_check)
    pm = prev_year(month)
    have_prev = any(r.get("month") == pm for r in rows)
    y = None
    if have_prev:
        y, _v, used2, _a = yoy(rows, month, biz, "all", "amount", place, export_check, direction="increase")
        used = max(used, used2)
    out = {"summary": summ, "yoy": y,
           "need": [] if have_prev else [{"dataset": dataset, "month": pm, "why": "전년 동월 비교"}]}
    return out, used


# ---- section 10.8: profile and recommendation -----------------------------------------------------
CATEGORY_SUFFIX = ("_id", "_cd", "_code", "_no", "_hour", "_nm", "_name")
CATEGORY_NAMES = {"age", "sex", "week", "time", "grid"}
EMPTY = ("", "NA", "NULL")


def profile(header, rows):
    cols, period = [], None
    for i, name in enumerate(header):
        vals = [r[i].strip() for r in rows if i < len(r) and r[i].strip() not in EMPTY]
        low = name.lower()
        distinct = sorted(set(vals))

        def top(vals=vals):
            cnt: dict = {}
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
            nums = None
            try:
                nums = [Decimal(v) for v in vals]
                if not nums or any(not n.is_finite() for n in nums):
                    nums = None
            except (InvalidOperation, ValueError):
                nums = None
            if nums:
                col.update({"type": "number", "sum": format(sum(nums), "f"), "min": format(min(nums), "f"),
                            "max": format(max(nums), "f")})
            elif len(distinct) <= 50:
                col.update({"type": "category", "top": top()})
            else:
                col.update({"type": "text"})
        cols.append(col)
    return {"rows": len(rows), "columns": cols, "period": period}


def recommend(sentence, catalog_data):
    datasets = catalog_data.get("datasets", [])
    scored = [(sum(1 for k in d.get("keywords", []) if k in sentence), i, d) for i, d in enumerate(datasets)]
    keep = sorted([s for s in scored if s[0] > 0], key=lambda s: (-s[0], s[1]))
    return {"datasets": [{"id": d["id"], "label": d["label"], "score": sc} for sc, _, d in keep]}


# ---- EDA helpers (10.4) ----------------------------------------------------------------------------
def months_missing(months):
    if not months:
        return []
    ms = sorted(set(months))
    out, m = [], ms[0]
    have = set(ms)
    while m <= ms[-1]:
        if m not in have:
            out.append(m)
        m = shift(m, 1)
    return out


def small_user_share(rows):
    if not rows:
        return None
    return pct(sum(1 for r in rows if r.get("users", MASK_THRESHOLD) < MASK_THRESHOLD), len(rows), "0.1")


def last3_direction(series):
    """'increase' | 'decrease' | 'mixed' over the last three months of a series."""
    vals = [s["amount"] for s in series[-3:]]
    if len(vals) < 3:
        return "mixed"
    if vals[0] < vals[1] < vals[2]:
        return "increase"
    if vals[0] > vals[1] > vals[2]:
        return "decrease"
    return "mixed"
