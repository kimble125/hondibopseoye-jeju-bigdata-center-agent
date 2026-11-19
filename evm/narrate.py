"""Korean sentence templates (polite style) and the number guard (policy P1).
Templates only format values that already exist in computed data."""
from __future__ import annotations

import re

from .calc import to_million, MASK_THRESHOLD
from .catalog import GROUP_LABELS, MEASURE_LABELS, MEASURE_UNITS

_NUM = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")
# Fixed rule constants that may appear in text: the mask threshold and the 12-month window.
FIXED_CONSTANTS = {str(MASK_THRESHOLD), "12"}

LIMIT_TEXT = "이 자료는 비씨카드 결제분만 담고 있어 업종 전체 매출이 아닙니다."


# ---- display ------------------------------------------------------------------------------------
def month_label(m) -> str:
    if not m or len(m) < 6:
        return ""
    return f"{m[:4]}년 {int(m[4:6])}월"


def month_dash(m) -> str:
    return f"{m[:4]}-{m[4:6]}" if m and len(m) >= 6 else ""


def num(v) -> str:
    return "-" if v is None else f"{v:,}"


def value_text(v, measure) -> str:
    return num(v) + MEASURE_UNITS.get(measure, "")


def pct_text(p) -> str:
    if p is None:
        return "계산할 수 없음"
    return p.lstrip("-") + "%"


def group_label(g) -> str:
    return GROUP_LABELS.get(g, g)


def scope_text(month, biz, place) -> str:
    parts = [month_label(month)]
    if place:
        parts.append(place)
    if biz:
        parts.append(biz)
    return " ".join(p for p in parts if p)


def josa(word: str, pair: str) -> str:
    """Pick the Korean particle by the final consonant: pair is '은/는', '이/가', '을/를', '과/와'."""
    first, second = pair.split("/")
    ch = word[-1] if word else ""
    if "\uac00" <= ch <= "\ud7a3":
        has_final = (ord(ch) - 0xAC00) % 28 != 0
        return word + (first if has_final else second)
    if ch.isdigit() or ch in "%":
        return word + (first if ch in "013678" else second)
    return word + first


# ---- number guard (P1) ----------------------------------------------------------------------------
def _add_int(allowed: set, v: int) -> None:
    a = abs(v)
    allowed.add(str(a))
    allowed.add(f"{a:,}")
    mil = to_million(a)
    allowed.add(str(mil))
    allowed.add(f"{mil:,}")


def _add_month(allowed: set, m: str) -> None:
    allowed.update({m, m[:4], m[4:6], str(int(m[4:6]))})


def allowed_tokens(*objs, months=()) -> set:
    allowed = set(FIXED_CONSTANTS)

    def walk(o):
        if isinstance(o, bool) or o is None:
            return
        if isinstance(o, int):
            _add_int(allowed, o)
        elif isinstance(o, str):
            if re.fullmatch(r"\d{6}", o):
                _add_month(allowed, o)
            elif re.fullmatch(r"-?\d+(?:\.\d+)?", o):
                allowed.add(o.lstrip("-"))
            elif re.fullmatch(r"\d{4}", o):
                allowed.add(o)
            else:
                for tok in _NUM.findall(o):     # numbers embedded in labels (e.g. '2024 3분기', '20대')
                    allowed.add(tok)
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, (list, tuple)):
            for v in o:
                walk(v)
    for o in objs:
        walk(o)
    for m in months:
        if m:
            _add_month(allowed, m)
    return allowed


def number_guard(text, allowed: set) -> bool:
    """True when every numeric token in text is an allowed display form."""
    if not text:
        return True
    return all(tok in allowed for tok in _NUM.findall(text))


def guarded(text, allowed: set, fallback: str) -> str:
    return text if number_guard(text, allowed) else fallback


# ---- messages ------------------------------------------------------------------------------------
def cannot_message(limit: str) -> str:
    return {
        "total_market": "이 자료로는 업종 전체 매출을 말할 수 없습니다. 비씨카드 결제분만 담긴 자료라, '비씨카드 이용금액'으로 바꿔 쓰시면 확인해 드릴 수 있습니다.",
        "cause": "이 자료로는 원인을 알 수 없습니다. 카드 이용 수치는 무엇이 얼마나 달라졌는지만 보여 줍니다. 원인은 현장 조사나 다른 자료로 확인해 주세요.",
        "forecast": "이 자료로는 앞으로의 일을 예측할 수 없습니다. 지난 기간의 카드 이용 수치만 확인해 드릴 수 있습니다.",
        "store_count": "이 자료에는 가게 수가 없습니다. 업종별 매장 수는 센터의 '제주도 내 업종별 매장 수' 자료를 받아야 알 수 있습니다.",
    }.get(limit, "이 자료로는 답할 수 없습니다.")


def need_file_message(missing: str, dataset, month, place=None) -> str:
    if missing == "region":
        if place and dataset:
            return f"넣으신 자료에는 '{place}' 지역의 행이 없습니다. 센터에서 '{dataset}' 표를 그 지역 조건으로 받아 넣어 주세요."
        return (f"지금 자료에는 지역(읍면동) 구분이 없습니다. 센터에서 '{dataset}' 표를 필요한 달로 받아 넣어 주시면 확인해 드리겠습니다.")
    ds = f"'{dataset}' 표" if dataset else "그 달이 들어 있는 자료"
    return f"지금 넣은 자료에는 {month_label(month)} 값이 없습니다. 센터에서 {ds}를 {month_label(month)}로 받아 넣어 주세요."


def ask_message(slot: str, word: str) -> str:
    if slot == "group":
        return f"'{word}'이 누구를 뜻하는지 골라 주세요. 내국인 관광객, 외국인, 관광객 전체 가운데 하나로 확인해 드립니다."
    if word:
        return f"'{word}'은 여러 업종을 함께 뜻할 수 있습니다. 어느 업종인지 골라 주세요."
    return "어느 업종을 확인할지 골라 주세요. 이 달에 이용금액이 큰 업종부터 보여 드립니다."


def summary_message(d: dict) -> str:
    scope = scope_text(d["month"], d["biz"], d["bjd"])
    if d["export"].get("masked_groups"):
        shown = [g for g in d["groups"] if not g.get("masked")]
        parts = [f"{group_label(g['group'])} {value_text(g['amount'], 'amount')}" for g in shown if g["rows"] > 0]
        head = f"{scope} 카드 이용 현황입니다. 반출 사전 점검 기준에 따라 작은 값이 있는 구분은 가렸고, 합계와 비중도 함께 가렸습니다."
        return head + (" 보이는 값: " + ", ".join(parts) + "." if parts else "")
    parts = [f"{group_label(g['group'])} {value_text(g['amount'], 'amount')}({pct_text(g['amount_share_pct'])})" for g in d["groups"]]
    tot = d["total"]["amount"] if d.get("total") else None
    return f"{scope} 카드 이용금액은 모두 {value_text(tot, 'amount')}입니다. " + ", ".join(parts) + ". " + LIMIT_TEXT


def yoy_summary_message(d: dict) -> str:
    scope = scope_text(d["month"], d["biz"], d["bjd"])
    meas = MEASURE_LABELS[d["measure"]]
    if d["export"]["masked"]:
        return f"{scope}의 전년 같은 달 비교에는 반출 사전 점검 기준보다 작은 값이 있어 수치를 가렸습니다."
    change = "늘었습니다" if d["diff"] > 0 else "줄었습니다" if d["diff"] < 0 else "같았습니다"
    return (f"{scope} {group_label(d['group'])} {josa(meas, '은/는')} {value_text(d['current'], d['measure'])}로, "
            f"{month_label(d['prev_month'])} {value_text(d['previous'], d['measure'])}보다 "
            f"{value_text(abs(d['diff']), d['measure'])}({pct_text(d['pct'])}) {change}. " + LIMIT_TEXT)


MASKED_VALUE = "10 미만(가림)"


def _rank_item(t: dict, measure: str) -> str:
    shown = MASKED_VALUE if t.get("masked") else value_text(t["value"], measure)
    return f"{t['rank']}위 {t['biz']}({shown})"


def _rank_mask_note(d: dict) -> str:
    return " 반출 사전 점검 기준에 따라 작은 값은 가렸습니다." if (d.get("export") or {}).get("masked") else ""


def rank_summary_message(d: dict) -> str:
    meas = MEASURE_LABELS[d["measure"]]
    parts = [_rank_item(t, d["measure"]) for t in d["top"]]
    scope = scope_text(d["month"], None, d.get("bjd"))
    return f"{scope} {meas} 상위 업종입니다. " + ", ".join(parts) + "." + _rank_mask_note(d) + " " + LIMIT_TEXT


def masked_claim_message(d: dict) -> str:
    scope = scope_text(d["month"], d.get("biz"), d.get("bjd"))
    return (f"{scope} 자료에는 반출 사전 점검 기준보다 작은 값이 있어, 이 문장의 판정과 수치를 싣지 않았습니다. "
            "기간이나 지역을 넓혀 다시 확인해 보세요.")


def compare_message(d: dict, verdict: str, claim: str) -> tuple:
    """Returns (message, rewrite)."""
    if verdict == "none":
        return masked_claim_message(d), None
    meas, unit = d["measure"], d["measure"]
    a, b = d["a"], d["b"]
    scope = scope_text(d["month"], d["biz"], d["bjd"])
    la, lb = group_label(a["group"]), group_label(b["group"])
    word = "네," if verdict == "supported" else "아니요,"
    va, vb = value_text(a["value"], unit), value_text(b["value"], unit)
    diff = value_text(abs(d["diff"]), unit)
    if a["value"] > b["value"]:
        big, small, rel = la, lb, "많습니다"
    elif a["value"] < b["value"]:
        big, small, rel = lb, la, "많습니다"
    else:
        big, small, rel = la, lb, None
    pct_part = f", {lb} 대비 {pct_text(d['pct_vs_b'])} {'많습니다' if d['diff'] > 0 else '적습니다'}" if d["pct_vs_b"] is not None and d["diff"] != 0 else ""
    msg = (f"{word} {scope} {josa(MEASURE_LABELS[meas], '은/는')} {la} {va}, {lb} {vb}입니다. "
           f"차이는 {diff}{pct_part}. {LIMIT_TEXT}")
    if rel is None:
        rewrite = f"{scope} {josa(MEASURE_LABELS[meas], '은/는')} {josa(la, '과/와')} {josa(lb, '이/가')} 같았습니다(비씨카드 기준)."
    else:
        rewrite = f"{scope} {josa(MEASURE_LABELS[meas], '은/는')} {josa(big, '이/가')} {small}보다 {diff} 더 많았습니다(비씨카드 기준)."
    if verdict == "supported":
        msg += " 아래처럼 근거를 붙여 쓰시면 됩니다."
    else:
        msg += " 실제 순서에 맞게 아래처럼 고쳐 쓰세요."
    return msg, rewrite


def yoy_claim_message(d: dict, verdict: str, actual) -> tuple:
    if verdict == "none":
        return masked_claim_message(d), None
    scope = scope_text(d["month"], d["biz"], d["bjd"])
    meas = MEASURE_LABELS[d["measure"]]
    word = "네," if verdict == "supported" else "아니요,"
    dirw = {"increase": "늘었습니다", "decrease": "줄었습니다", "flat": "같았습니다"}[actual].rstrip(".")
    diff = value_text(abs(d["diff"]), d["measure"])
    g = group_label(d["group"])
    msg = (f"{word} {scope} {g} {josa(meas, '은/는')} {value_text(d['current'], d['measure'])}이고, "
           f"{month_label(d['prev_month'])}에는 {value_text(d['previous'], d['measure'])}이었습니다. "
           f"{diff}({pct_text(d['pct'])}) {dirw}. {LIMIT_TEXT}")
    if actual == "flat":
        rewrite = f"{scope} {g} {josa(meas, '은/는')} 전년 같은 달과 같았습니다(비씨카드 기준)."
    else:
        rewrite = (f"{scope} {g} {josa(meas, '은/는')} 전년 같은 달보다 {pct_text(d['pct'])} "
                   f"{'늘었' if actual == 'increase' else '줄었'}습니다(비씨카드 기준).")
    msg += " 아래처럼 근거를 붙여 쓰시면 됩니다." if verdict == "supported" else " 실제 방향에 맞게 아래처럼 고쳐 쓰세요."
    return msg, rewrite


def rank_claim_message(d: dict, verdict: str, claimed: int) -> tuple:
    meas = MEASURE_LABELS[d["measure"]]
    asked = d["asked"]
    scope = scope_text(d["month"], None, d.get("bjd"))
    if asked.get("masked"):
        return masked_claim_message({"month": d["month"], "biz": asked["biz"], "bjd": d.get("bjd")}), None
    word = "네," if verdict == "supported" else "아니요,"
    top = ", ".join(_rank_item(t, d["measure"]) for t in d["top"])
    if asked["rank"] is None:
        msg = f"{word} {scope} 자료에서 {asked['biz']}의 값을 찾지 못했습니다. 상위 업종은 {top}입니다."
        return msg + _rank_mask_note(d), None
    msg = (f"{word} {scope} {meas} 기준으로 {josa(asked['biz'], '은/는')} {asked['rank']}위입니다. "
           f"상위 업종은 {top}입니다.{_rank_mask_note(d)} {LIMIT_TEXT}")
    rewrite = f"{scope} {meas} 기준으로 {josa(asked['biz'], '은/는')} 업종 가운데 {asked['rank']}위였습니다(비씨카드 기준)."
    msg += " 아래처럼 근거를 붙여 쓰시면 됩니다." if verdict == "supported" else " 실제 순위에 맞게 아래처럼 고쳐 쓰세요."
    return msg, rewrite


def notice(code: str, extra: str = "") -> dict:
    texts = {
        "card_only": LIMIT_TEXT,
        "users_not_unique": "이용자 수는 같은 사람이 여러 행에 함께 셀 수 있어, 더한 값이 실제 사람 수는 아닙니다.",
        "synthetic": "가상 데이터 시연(실제 수치가 아닙니다)",
        "data_quality": "자료에 글자가 깨진 업종 이름이 있어 따로 셌습니다. 원래 이름과 합쳐지지 않았을 수 있습니다.",
        "export_masked": "반출 사전 점검: 작은 값(반출 기준 미만)을 가렸습니다. 반출 여부는 신청 후 센터가 정합니다.",
        "default_month": "달을 적지 않으셔서 자료의 가장 최근 달로 확인했습니다.",
        "no_export_check": ("이 자료 요약에는 반출 사전 점검(작은 값 가림, 역산 점검)이 적용되지 않습니다. "
                            "센터 자료라면 이 요약을 그대로 반출 신청에 쓰지 마시고 센터 기준을 직접 확인해 주세요."),
    }
    return {"code": code, "text": extra or texts.get(code, "")}
