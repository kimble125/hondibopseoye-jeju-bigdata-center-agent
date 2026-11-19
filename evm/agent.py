"""The agent loop: understand -> check file -> choose month -> plan -> compute -> pre-check -> verdict -> compose.
`answer` never raises; it returns a JSON-serialisable AgentResult (section 3.4)."""
from __future__ import annotations

from . import calc, catalog as cat, narrate
from .understand import understand, build_vocab, resolve_biz  # re-exported (B5)

__all__ = ["answer", "understand", "build_vocab"]

SOURCE_SHORT = {"제주데이터허브(공개)": "제주데이터허브", "제주빅데이터센터": "제주빅데이터센터"}


# ---- result skeleton ------------------------------------------------------------------------------
def new_result(behavior="error", verdict="none", intent=None, message="", data=None):
    return {"behavior": behavior, "verdict": verdict,
            "intent": intent or {"analysis": "none", "month": None, "biz": None, "bjd": None, "measure": None,
                                 "groups": [], "claim": None},
            "message": message, "rewrite": None, "notices": [], "data": data if data is not None else {},
            "decisions": [], "evidence": None, "choices": [], "suggestions": []}


def decide(res, step, decided, reason):
    res["decisions"].append({"step": step, "decided": decided, "reason": reason})


def _intent_from(u):
    return {"analysis": "none", "month": u.get("month"), "biz": u.get("biz"),
            "bjd": (u.get("place") or {}).get("value"), "measure": u.get("measure"),
            "groups": [g["group"] for g in u.get("groups", [])], "claim": u.get("claim")}


def _table_vocab(active, rows):
    biz = sorted({r.get("biz", "") for r in rows if r.get("biz")})
    places = None
    if active and active.get("has", {}).get("bjd"):
        places = {"bjd": sorted({r.get("bjd", "") for r in rows if r.get("bjd")}),
                  "dstrct_se": sorted({r.get("dstrct_se", "") for r in rows if r.get("dstrct_se")})}
    return build_vocab(active, biz, places)


def months_span(months):
    ms = sorted(m for m in months if m)
    if not ms:
        return ""
    return ms[0] if ms[0] == ms[-1] else f"{ms[0]}–{ms[-1]}"


def citation(active, months):
    src = SOURCE_SHORT.get(active["source"], active["source"])
    ms = ", ".join(narrate.month_dash(m) for m in sorted(set(months)) if m)
    return f"출처: {src}, {active['label']}({ms})"


def evidence(active, months_used, rows_used, formula):
    return {"dataset": active["label"], "source": active["source"], "files": list(active["files"]),
            "months": months_span(active["months"]), "rows_used": rows_used, "formula": formula,
            "citation": citation(active, months_used)}


def base_notices(res, active, *, numeric, month_default=False, measure=None, biz=None, masked=False, extra_biz=()):
    codes = []
    if active and active.get("synthetic"):
        codes.append("synthetic")
    if numeric:
        codes.append("card_only")
    if month_default:
        codes.append("default_month")
    if measure == "users":
        codes.append("users_not_unique")
    if masked:
        codes.append("export_masked")
    names = [biz] + list(extra_biz)
    if any(n and "?" in n for n in names):
        codes.append("data_quality")
    for c in codes:
        if not any(n["code"] == c for n in res["notices"]):
            res["notices"].append(narrate.notice(c))


def suggestions_for(month, biz, place=None):
    ml = narrate.month_label(month)
    where = (place + " ") if place else ""
    if not biz:
        return [f"{ml} 카드 이용금액이 가장 큰 업종은 한식 음식점업이다".strip(),
                f"{where}한식 음식점업은 내국인 관광객이 도민보다 많이 썼다",
                f"{where}한식 음식점업 카드 이용금액이 작년 같은 달보다 늘었다"]
    return [f"{where}{biz}은 내국인 관광객이 도민보다 많이 썼다",
            f"{where}{biz} 카드 이용금액이 작년 같은 달보다 늘었다",
            f"{ml} 카드 이용금액이 가장 큰 업종은 {biz}이다".strip()]


def _guard(res, months):
    allowed = narrate.allowed_tokens(res["data"], months=months)
    if not narrate.number_guard(res["message"], allowed):
        res["message"] = "확인한 값은 아래 표에 있습니다. 표의 수치를 그대로 옮겨 쓰세요."
    if res.get("rewrite") and not narrate.number_guard(res["rewrite"], allowed):
        res["rewrite"] = None


# ---- main -----------------------------------------------------------------------------------------
def answer(sentence: str, *, store, llm=None) -> dict:
    try:
        return _answer(sentence, store=store, llm=llm)
    except Exception:  # never raise to the caller
        return new_result("error", "none", message="죄송합니다. 이 문장을 처리하는 중에 문제가 생겼습니다. 문장을 조금 바꿔 다시 적어 주세요.")


def _answer(sentence, *, store, llm=None):
    sentence = (sentence or "").strip()
    if not sentence:
        return new_result("error", "none", message="확인할 문장을 적어 주세요.")
    active, rows = store.card_view()
    vocab = _table_vocab(active, rows)
    u = understand(sentence, active=active, vocab=vocab)
    if (llm is not None and active and active["kind"] == "hub_biz_sex" and store.active() is None
            and u["biz"] is None and u["analysis"] == "summary" and not u["limit"]):
        try:   # optional rewrite hook (3.5-9, A6): only with the bundled public table and no user file
            rewritten = llm.rewrite(sentence, {"biz": sorted(vocab["biz_preferred"].values()),
                                               "groups": list(cat.GROUP_LABELS.values())})
        except Exception:
            rewritten = None
        if rewritten:
            u = understand(rewritten, active=active, vocab=vocab)
    intent = _intent_from(u)
    res = new_result("error", "none", intent)
    decide(res, "understand", "문장에서 업종·지역·달·구분·지표를 읽었습니다.",
           f"업종 {u['biz'] or '없음'}, 지역 {intent['bjd'] or '없음'}, 분석 {u['analysis']}")

    # 1. limits end the turn first
    if u["limit"]:
        res.update(behavior="cannot", data={"limit": u["limit"]}, message=narrate.cannot_message(u["limit"]))
        decide(res, "verdict", "이 자료로는 답할 수 없는 질문으로 판단했습니다.", f"한계 유형: {u['limit']}")
        res["suggestions"] = suggestions_for(None, u["biz"])
        return res

    # F1: profile, recommendation and documents are decided before any check against the active table
    from . import docflow
    gen = store.generic()
    if gen is not None:
        return docflow.profile_result(res, store, gen)
    if u["recommend"]:
        return docflow.recommend_result(res, sentence)
    if u["doc"] or u["brief"]:
        out = docflow.document_result(res, u, store, vocab)
        if out is not None:
            return out

    # P2: check the file before any calculation
    if not active:
        res.update(behavior="need_file", data={"missing": "month", "dataset": None, "month": u["month"]},
                   message="아직 넣은 자료가 없습니다. 카드 이용 CSV 파일을 넣어 주세요.")
        return res
    decide(res, "check_file", f"'{active['label']}' 자료({months_span(active['months'])})로 확인합니다.",
           "계산 전에 자료 종류·달·지역 열을 먼저 봅니다.")
    center = active["kind"] in ("c108", "c112", "c114")
    if u["biz_ambiguous"]:
        res.update(behavior="ask_scope", data={"slot": "biz", "choices": list(cat.FOOD_CHOICES)},
                   choices=list(cat.FOOD_CHOICES), message=narrate.ask_message("biz", u["biz_ambiguous"]["word"]))
        res["intent"]["ambiguous"] = u["biz_ambiguous"]
        decide(res, "understand", "업종을 되물었습니다.", f"'{u['biz_ambiguous']['word']}'은 여러 업종을 뜻합니다.")
        return res
    place = None
    if u["place"]:
        if not active["has"].get("bjd"):
            res.update(behavior="need_file", data={"missing": "region", "dataset": cat.REGION_DATASET, "month": None},
                       message=narrate.need_file_message("region", cat.REGION_DATASET, None))
            decide(res, "check_file", "지역 자료가 필요하다고 알렸습니다.", "지금 자료에는 지역 열이 없습니다.")
            return res
        place = (u["place"]["field"], u["place"]["value"])
        if not calc.place_has_rows(rows, place):
            res.update(behavior="need_file", data={"missing": "region", "dataset": active["label"], "month": None},
                       message=narrate.need_file_message("region", active["label"], None, place[1]))
            decide(res, "check_file", "해당 지역의 자료가 없습니다.", "넣은 파일에 그 지역의 행이 없습니다.")
            return res
    months = active["months"]
    dataset_for_month = active["label"] if center else None
    if u["month_explicit"]:
        if u["month"] not in months:
            res.update(behavior="need_file", data={"missing": "month", "dataset": dataset_for_month, "month": u["month"]},
                       message=narrate.need_file_message("month", dataset_for_month, u["month"]))
            decide(res, "choose_month", "그 달의 자료가 필요하다고 알렸습니다.", "넣은 자료에 그 달이 없습니다.")
            return res
        month, month_default = u["month"], False
    else:
        month, month_default = months[-1], True
    res["intent"]["month"] = month
    decide(res, "choose_month", narrate.month_label(month), "문장에 적힌 달" if not month_default else "자료의 가장 최근 달")
    if u["group_ambiguous"]:
        res.update(behavior="ask_scope", data={"slot": "group", "choices": list(cat.GROUP_CHOICES)},
                   choices=list(cat.GROUP_CHOICES), message=narrate.ask_message("group", u["group_ambiguous"]["word"]))
        res["intent"]["ambiguous"] = u["group_ambiguous"]
        decide(res, "understand", "누구를 뜻하는지 되물었습니다.", "'관광객'만으로는 내국인·외국인을 가를 수 없습니다.")
        return res

    export_check = active["export_check"]
    biz = u["biz"]
    analysis = u["analysis"]
    measure = u["measure"]
    res["intent"]["analysis"] = analysis
    pval = place[1] if place else None

    if analysis == "group_compare":
        a, b = u["compare"]["a"], u["compare"]["b"]
        claim = u["claim"]["type"]
        decide(res, "plan", f"{narrate.group_label(a)}와 {narrate.group_label(b)}의 {cat.MEASURE_LABELS[measure]} 비교",
               "두 구분과 '보다'가 있는 문장입니다.")
        data, verdict, used = calc.compare(rows, month, biz, a, b, measure, place, export_check, claim)
        res["intent"]["groups"] = [a, b]
        msg, rw = narrate.compare_message(data, verdict, claim)
        res.update(behavior="claim_check", verdict=verdict, data=data, message=msg, rewrite=rw)
        formula = f"{narrate.month_label(month)} {biz or '전체 업종'} 행을 구분별로 더해 비교({cat.MEASURE_LABELS[measure]})"
        res["evidence"] = evidence(active, [month], used, formula)
        masked = data["export"]["masked"]
        _finish(res, active, [month], numeric=True, month_default=month_default, measure=measure, biz=biz,
                masked=masked, export_check=export_check, verdict=verdict)
        res["suggestions"] = suggestions_for(month, biz, pval)
        return res

    if analysis == "yoy":
        group = u["groups"][0]["group"] if len(u["groups"]) == 1 else "all"
        pm = calc.prev_year(month)
        res["intent"]["groups"] = [group]
        if pm not in months:
            res.update(behavior="need_file", data={"missing": "month", "dataset": dataset_for_month, "month": pm},
                       message=narrate.need_file_message("month", dataset_for_month, pm))
            decide(res, "check_file", "전년 같은 달 자료가 필요하다고 알렸습니다.", f"{narrate.month_label(pm)} 자료가 없습니다.")
            return res
        direction = u["yoy_direction"]
        data, verdict, used, actual = calc.yoy(rows, month, biz, group, measure, place, export_check, direction)
        decide(res, "plan", "전년 같은 달과 비교", "'작년·전년·지난해'가 있는 문장입니다.")
        if direction:
            msg, rw = narrate.yoy_claim_message(data, verdict, actual)
            res.update(behavior="claim_check", verdict=verdict, data=data, message=msg, rewrite=rw)
        else:
            res.update(behavior="summary", verdict="none", data=data, message=narrate.yoy_summary_message(data))
        formula = f"{narrate.month_label(month)}와 {narrate.month_label(pm)}의 {cat.MEASURE_LABELS[measure]} 합계 비교"
        res["evidence"] = evidence(active, [pm, month], used, formula)
        _finish(res, active, [month, pm], numeric=True, month_default=month_default, measure=measure, biz=biz,
                masked=data["export"]["masked"], export_check=export_check, verdict=verdict)
        res["suggestions"] = suggestions_for(month, biz, pval)
        return res

    if analysis == "rank":
        n = u["rank_n"] or 1
        rplace = place if center else None        # public table: unchanged R6 (B3)
        rexport = bool(export_check) if center else False
        if rplace and not calc.rows_in(rows, month, rplace):
            res.update(behavior="need_file", data={"missing": "region", "dataset": active["label"], "month": None},
                       message=narrate.need_file_message("region", active["label"], None, rplace[1]))
            decide(res, "check_file", "해당 지역의 자료가 없습니다.", "넣은 파일에 그 달·그 지역의 행이 없습니다.")
            return res
        data, verdict, used = calc.rank(rows, month, measure, biz, n, place=rplace, export_check=rexport)
        res["intent"]["groups"] = ["all"]
        decide(res, "plan", "업종 순위" + (f"({rplace[1]})" if rplace else ""), "'가장·제일·최고·N위'가 있는 문장입니다.")
        if biz:
            msg, rw = narrate.rank_claim_message(data, verdict, n)
            res.update(behavior="claim_check", verdict=verdict, data=data, message=msg, rewrite=rw)
        else:
            res.update(behavior="summary", verdict="none", data=data, message=narrate.rank_summary_message(data))
        where = f" {rplace[1]}" if rplace else ""
        res["evidence"] = evidence(active, [month], used, f"{narrate.month_label(month)}{where} 업종별 {cat.MEASURE_LABELS[measure]} 합계를 큰 순서로 정렬")
        rmasked = bool((data.get("export") or {}).get("masked"))
        _finish(res, active, [month], numeric=True, month_default=month_default, measure=measure, biz=biz,
                masked=rmasked, export_check=rexport, verdict=res["verdict"], extra_biz=[t["biz"] for t in data["top"]])
        res["suggestions"] = suggestions_for(month, biz or (data["top"][0]["biz"] if data["top"] else None), pval)
        return res

    # summary
    if not biz:
        choices = calc.top_businesses(rows, month, 6)
        res.update(behavior="ask_scope", data={"slot": "biz", "choices": choices}, choices=list(choices),
                   message=narrate.ask_message("biz", ""))
        decide(res, "understand", "업종을 되물었습니다.", "문장에 업종이 없습니다.")
        return res
    data, used = calc.summary(rows, month, biz, place, export_check)
    decide(res, "plan", "구분별 카드 이용 현황", "업종이 있고 비교·순위 말이 없는 문장입니다.")
    res.update(behavior="summary", verdict="none", data=data, message=narrate.summary_message(data))
    res["intent"]["analysis"] = "summary"
    res["evidence"] = evidence(active, [month], used, f"{narrate.month_label(month)} {biz} 행을 도민·내국인 관광객·외국인·법인으로 나눠 합계")
    _finish(res, active, [month], numeric=True, month_default=month_default, measure="amount", biz=biz,
            masked=bool(data["export"]["masked_groups"]), export_check=export_check, verdict="none")
    res["suggestions"] = suggestions_for(month, biz, pval)
    return res


def _finish(res, active, months, *, numeric, month_default, measure, biz, masked, export_check, verdict, extra_biz=()):
    if export_check:
        decide(res, "precheck", "반출 사전 점검을 적용했습니다." + (" 작은 값을 가렸습니다." if masked else " 가릴 값은 없었습니다."),
               "센터 자료는 반출 신청 전에 작은 값을 점검합니다(승인은 센터가 정합니다).")
    decide(res, "verdict", {"supported": "써도 됩니다", "revise": "이렇게 고쳐 쓰세요", "none": "판정 없음"}[verdict],
           "계산한 값과 문장을 견주었습니다." if verdict != "none" else ("가린 값이 있어 판정하지 않았습니다." if masked else "현황 요청입니다."))
    base_notices(res, active, numeric=numeric, month_default=month_default, measure=measure, biz=biz, masked=masked,
                 extra_biz=extra_biz)
    if res["verdict"] not in ("supported", "revise"):
        res["rewrite"] = None
    _guard(res, months)
    decide(res, "compose", "정해진 문장 틀로 답을 만들었습니다.", "숫자는 계산한 값만 씁니다(숫자 점검 통과).")
