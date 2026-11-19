"""Document workflow (section 10, 10.7, 10.8): generic profile, dataset recommendation, the two document
templates and the data brief. Produces AgentResults with `data` (numbers from calc), `eda` and `draft`
(plain text blocks and tables; HTML is the app's job)."""
from __future__ import annotations

from . import calc, catalog as cat, narrate

PUBLIC_SOURCE = "제주데이터허브(공개)"
MASKED_CELL = "10 미만(가림)"


# ---- shared helpers --------------------------------------------------------------------------------
def _agent():
    from . import agent
    return agent


def mil(v) -> str:
    """Display helper: whole million won with thousands separators."""
    m = calc.to_million(v)
    return "-" if m is None else f"{m:,}"


def _span(months):
    ms = sorted(m for m in months if m)
    if not ms:
        return ""
    return narrate.month_dash(ms[0]) if ms[0] == ms[-1] else f"{narrate.month_dash(ms[0])}–{narrate.month_dash(ms[-1])}"


def _change_word(p, up="증가", down="감소"):
    if p is None:
        return "비교할 수 없음"
    if p.startswith("-"):
        return down
    return up if p.strip("0.") else "변동 없음"


def _guard_texts(texts, allowed):
    return [t if narrate.number_guard(t, allowed)
            else "이 문장은 수치 점검을 통과하지 못해 싣지 않았습니다. 아래 표를 확인해 주세요." for t in texts]


def _ensure_library(store):
    if not store.has_library("hub_biz_sex"):
        store.load_library()


def _top_lib_biz(store, k=6):
    hub = store.library("hub_biz_sex")
    m = calc.latest_month(hub)
    return calc.top_businesses(hub, m, k) if m else []


def template_info(tpl):
    t = cat.doc_templates().get("templates", {}).get(tpl, {})
    forms = [{"form": m.get("form", ""), "url": m.get("url", "")} for m in t.get("modelled_on", [])]
    basis = ("본뜬 양식과 출처: " + "; ".join(f"{f['form']} ({f['url']})" for f in forms)) if forms else ""
    return t, forms, basis


def formats(family=None):
    """10.8-2: catalog formats of a data family (default: all families), each with its basis line."""
    fams = cat.report_catalog().get("families", {})
    keys = [family] if family else list(fams)
    out = []
    for k in keys:
        for f in fams.get(k, {}).get("formats", []):
            b = f.get("basis", {})
            line = (f"본뜬 양식: {b.get('form', '')} ({b.get('url', '')})" if b.get("type") == "public_form"
                    else f"자체 제작: {b.get('note', '')}")
            out.append({"family": k, "id": f.get("id"), "title": f.get("title"), "for_whom": f.get("for_whom"),
                        "blocks": list(f.get("blocks", [])), "basis_line": line, "status": f.get("status")})
    return out


def eda_table(label, source, rows, months, *, has_users, biz_key="biz", span=None):
    garbled = sorted({r.get(biz_key, "") for r in rows if "?" in r.get(biz_key, "")})
    entry = {"label": label, "source": source, "months": span if span is not None else _span(months), "rows": len(rows),
             "small_user_share_pct": calc.small_user_share(rows) if has_users else None,
             "garbled_names": garbled, "missing_months": calc.months_missing(months)}
    line = f"{label}({source}): {entry['months'] or '기간 표시 없음'}, {len(rows):,}행"
    if has_users and entry["small_user_share_pct"] is not None:
        line += f", 이용자 수가 기준(10명)보다 작은 행 {entry['small_user_share_pct']}%"
    if garbled:
        line += ", 글자가 깨진 이름: " + ", ".join(garbled)
    if months:
        line += ", 빠진 달: " + (", ".join(narrate.month_dash(m) for m in entry["missing_months"]) if entry["missing_months"] else "없음")
    entry["text"] = line
    return entry


def _lib_active(store):
    info = store.library_info("hub_biz_sex")
    spec = cat.KINDS["hub_biz_sex"]
    return {"kind": "hub_biz_sex", "label": spec["label"], "source": spec["source"],
            "files": [info["name"]] if info else [], "months": info["months"] if info else [], "synthetic": False}


def _doc_result(res, tpl, data, eda, draft, *, active_like, months_used, rows_used, formula,
                synthetic=False, masked=False, month_default=False):
    ag = _agent()
    res.update(behavior="document", verdict="none", data=data)
    res["intent"]["analysis"] = "document"
    res["intent"]["template"] = tpl
    res["eda"] = eda
    res["draft"] = draft
    res["message"] = draft["summary"]
    res["evidence"] = ag.evidence(active_like, months_used, rows_used, formula)
    codes = (["synthetic"] if synthetic else []) + ["card_only"] + (["default_month"] if month_default else []) \
        + (["export_masked"] if masked else [])
    for c in codes:
        res["notices"].append(narrate.notice(c))
    ag.decide(res, "plan", f"문서 틀 '{draft['title']}'에 맞춰 필요한 표를 정했습니다.", "공개 표는 늘 들어 있고, 센터 표는 넣었을 때만 씁니다.")
    ag.decide(res, "compute", "표마다 탐색(EDA)과 계산을 했습니다.", "숫자는 계산 규칙으로만 냅니다.")
    if masked:
        ag.decide(res, "precheck", "반출 사전 점검으로 작은 값을 가렸습니다.", "승인 여부는 센터가 정합니다.")
    ag.decide(res, "compose", "문서 초안을 정해진 틀로 만들었습니다.", "모든 문장은 숫자 점검을 거쳤습니다.")
    res["suggestions"] = list(draft.get("check_sentences", []))[:3]
    return res


def _ask_group(res, u):
    res.update(behavior="ask_scope", data={"slot": "group", "choices": list(cat.GROUP_CHOICES)},
               choices=list(cat.GROUP_CHOICES), message=narrate.ask_message("group", u["group_ambiguous"]["word"]))
    return res


def _need_month(res, month, dataset):
    res.update(behavior="need_file", data={"missing": "month", "dataset": dataset, "month": month},
               message=narrate.need_file_message("month", dataset, month))
    return res


# ---- 10.8-4 generic profile ------------------------------------------------------------------------
def profile_result(res, store, gen):
    ag = _agent()
    data = calc.profile(gen["header"], gen["rows"])
    res.update(behavior="profile", verdict="none", data=data)
    res["intent"]["template"] = "profile"
    parts = []
    if data["period"]:
        parts.append(f"기간은 {data['period']['min']}부터 {data['period']['max']}까지({data['period']['column']} 열)입니다")
    parts.append(f"모두 {data['rows']:,}행입니다")
    nums = [c for c in data["columns"] if c["type"] == "number"]
    if nums:
        parts.append("숫자 열을 모두 더하면 " + ", ".join(f"{c['name']} {c['sum']}" for c in nums) + "입니다")
    cats = [c for c in data["columns"] if c["type"] == "category" and c.get("top")]
    if cats:
        parts.append("주요 구분은 " + "; ".join(f"{c['name']}({', '.join(t['value'] for t in c['top'][:3])})" for c in cats[:4]) + "입니다")
    msg = "넣으신 표는 카드 이용 표가 아니라서 내용만 정리했습니다. " + ". ".join(parts) + ". 문장 검산은 지금은 카드 이용 표에서만 됩니다."
    allowed = narrate.allowed_tokens(data)
    res["message"] = narrate.guarded(msg, allowed, "넣으신 표의 내용을 아래 표로 정리했습니다. 문장 검산은 지금은 카드 이용 표에서만 됩니다.")
    if gen.get("synthetic"):
        res["notices"].append(narrate.notice("synthetic"))
    # 10.8-4: no export claim is made for a generic table; say so on every profile result
    res["notices"].append(narrate.notice("no_export_check"))
    res["evidence"] = {"dataset": "그 밖의 CSV 표", "source": "사용자가 넣은 파일", "files": [gen["name"]],
                       "months": (f"{data['period']['min']}–{data['period']['max']}" if data["period"] else ""),
                       "rows_used": data["rows"],
                       "formula": "열마다 빈 값이 아닌 수, 서로 다른 값의 수, 숫자 열의 합계·최솟값·최댓값, 자주 나오는 값",
                       "citation": f"출처: 사용자가 넣은 파일({gen['name']})"}
    ag.decide(res, "check_file", "카드 표가 아닌 표를 열 정보로 정리했습니다.", "열 이름이 아는 표와 맞지 않습니다.")
    return res


# ---- 10.8-1 recommendation -------------------------------------------------------------------------
def recommend_result(res, sentence):
    ag = _agent()
    catalog = cat.report_catalog()
    data = calc.recommend(sentence, catalog)
    res.update(behavior="recommend_data", verdict="none", data=data)
    res["intent"]["template"] = "recommend_data"
    by_id = {d["id"]: d for d in catalog.get("datasets", [])}
    if data["datasets"]:
        lines = [f"'{d['label']}': {by_id[d['id']].get('why', '')} (받는 법: {by_id[d['id']].get('menu_hint', '')})"
                 for d in data["datasets"]]
        msg = ("적어 주신 목적에는 다음 자료가 맞습니다. " + " / ".join(lines)
               + ". 센터에서 받은 CSV 파일을 여기에 넣어 주시면 이어서 초안과 검산을 도와 드립니다.")
        res["choices"] = [d["label"] for d in data["datasets"]]
    else:
        fams = [f.get("label", k) for k, f in catalog.get("families", {}).items()]
        msg = "어떤 주제의 자료가 필요한지 조금 더 알려 주세요. 센터 자료는 이런 주제로 나뉩니다: " + ", ".join(fams) + "."
        res["choices"] = fams
    allowed = narrate.allowed_tokens(data, catalog.get("datasets", []))
    res["message"] = narrate.guarded(msg, allowed, "필요한 자료 목록을 아래에 정리했습니다.")
    ag.decide(res, "plan", "받을 자료를 추천했습니다.", "자료 목록의 낱말과 문장을 견주어 점수를 매겼습니다.")
    return res


# ---- 10.2 document dispatcher ------------------------------------------------------------------------
def document_result(res, u, store, vocab):
    _ensure_library(store)
    if not store.has_library("hub_biz_sex"):
        return None
    tpl = u["doc"] or ("data_brief" if u["brief"] else None)
    if tpl is None:
        return None
    ag = _agent()
    ag.decide(res, "understand", f"문서 요청으로 읽었습니다({tpl}).", "문서 이름 낱말이 있는 문장입니다.")
    res["intent"]["template"] = tpl
    if tpl in ("bizplan_market", "data_brief") and u["biz"] is None:
        choices = list(cat.FOOD_CHOICES) if u["biz_ambiguous"] else _top_lib_biz(store)
        res.update(behavior="ask_scope", data={"slot": "biz", "choices": choices}, choices=list(choices),
                   message=narrate.ask_message("biz", (u["biz_ambiguous"] or {}).get("word", "")))
        return res
    if tpl == "consumption_trend":
        return trend_result(res, u, store)
    if tpl == "bizplan_market":
        return bizplan_result(res, u, store)
    return brief_result(res, u, store)


# ---- consumption_trend -------------------------------------------------------------------------------
def trend_result(res, u, store):
    hub = store.library("hub_biz_sex")
    months = store.library_info("hub_biz_sex")["months"]
    if u["month_explicit"]:
        if u["month"] not in months:
            return _need_month(res, u["month"], None)
        month, default = u["month"], False
    else:
        month, default = months[-1], True
    if u["group_ambiguous"]:
        return _ask_group(res, u)
    group = u["groups"][0]["group"] if u["groups"] else "all"
    res["intent"].update(month=month, groups=[group])
    data = calc.consumption_trend(hub, month, group)
    used_months = [month, data["prev_month"], data["yoy_month"]]
    gset = cat.GROUP_SETS[group]
    rows_used = sum(1 for r in hub if r["month"] in used_months and r["user_type"] in gset)
    tables = [eda_table(cat.KINDS["hub_biz_sex"]["label"], PUBLIC_SOURCE, hub, months, has_users=True)]
    allowed = narrate.allowed_tokens(data, tables, months=used_months)
    eda = {"tables": tables, "reading": None, "lines": _guard_texts([t["text"] for t in tables], allowed)}
    draft = trend_draft(data, allowed)
    return _doc_result(res, "consumption_trend", data, eda, draft, active_like=_lib_active(store), months_used=used_months,
                       rows_used=rows_used, formula="금월·전월·전년 동월의 비씨카드 이용금액 합계와 업종별 증감률(일수 보정 없음)",
                       month_default=default)


def trend_draft(d, allowed):
    t, forms, basis = template_info("consumption_trend")
    h = d["headline"]
    who = "제주도 전체" if d["group"] == "all" else narrate.GROUP_LABELS.get(d["group"], d["group"])
    ml, pl, yl = narrate.month_label(d["month"]), narrate.month_label(d["prev_month"]), narrate.month_label(d["yoy_month"])
    head = (f"{ml} {who}의 BC카드 이용금액은 전월 대비 {narrate.pct_text(h['pct_mom'])} {_change_word(h['pct_mom'])}했고, "
            f"전년 동기 대비해서는 {narrate.pct_text(h['pct_yoy'])} {_change_word(h['pct_yoy'])}한 것으로 나타남")
    pu = h["per_use"]
    per = (f"건당 이용금액은 {narrate.num(pu['current'])}원(전월 {narrate.num(pu['previous'])}원, "
           f"전년 동기 {narrate.num(pu['year_ago'])}원)임")
    blocks = [{"id": "cover", "title": "표지 정보", "text": "", "table": {
        "title": "표지 정보", "columns": ["항목", "내용"],
        "rows": [["분석 주체", "(직접 적어 주세요)"], ["분석 목적", "(직접 적어 주세요)"],
                 ["분석 활용 데이터", f"{cat.KINDS['hub_biz_sex']['label']}(제주데이터허브, 제공처 제주빅데이터센터·비씨카드)"],
                 ["분석 범위", f"{ml}, 비교 {pl}·{yl}, 대상 {who}"],
                 ["분석 방법", "비씨카드 이용금액 합계 비교, 업종별 증감률(일수 보정 없음)"],
                 ["데이터기준일", ml]]}, "user_fields": ["분석 주체", "분석 목적"]}]
    blocks.append({"id": "headline", "title": "전체 카드 이용금액 비교(금월·전월·전년 동기)", "text": head + ". " + per + ".",
                   "table": {"title": "전체 카드 이용 비교", "columns": ["구분", "금월", "전월", "전년 동기"],
                             "rows": [["이용금액(백만원)", mil(h["amount"]["current"]), mil(h["amount"]["previous"]), mil(h["amount"]["year_ago"])],
                                      ["이용건수", narrate.num(h["uses"]["current"]), narrate.num(h["uses"]["previous"]), narrate.num(h["uses"]["year_ago"])],
                                      ["건당 이용금액(원)", narrate.num(pu["current"]), narrate.num(pu["previous"]), narrate.num(pu["year_ago"])]]}})
    for key, title, base in (("biz_mom", "전월 대비 주요 업종별 증감", pl), ("biz_yoy", "전년 동기 대비 주요 업종별 증감", yl)):
        b = d[key]
        up = ", ".join(f"{x['biz']}({x['pct']}%)" for x in b["top_up"][:3])
        down = ", ".join(f"{x['biz']}({x['pct']}%)" for x in b["top_down"][:3])
        text = (f"{b['n_biz']}개 업종 중 증가 {b['increase_count']}개, 감소 {b['decrease_count']}개임. "
                f"증가 폭이 큰 업종은 {up or '없음'}, 감소 폭이 큰 업종은 {down or '없음'}임.")
        rows = [["증가 상위", x["biz"], x["pct"], mil(x["current"]), mil(x["previous"])] for x in b["top_up"]]
        rows += [["감소 상위", x["biz"], x["pct"], mil(x["current"]), mil(x["previous"])] for x in b["top_down"]]
        blocks.append({"id": key, "title": title, "text": text,
                       "table": {"title": f"{title}({base} 대비)", "columns": ["구분", "업종", "증감률(%)", "금월(백만원)", "비교 달(백만원)"],
                                 "rows": rows}})
    for bl in blocks:
        if bl["text"]:
            bl["text"] = _guard_texts([bl["text"]], allowed)[0]
    summary = _guard_texts([head + "."], allowed)[0] + " 현황자료 초안을 아래에 만들었습니다."
    return {"template": "consumption_trend", "title": t.get("label", "현황자료: 월간 소비동향"), "modelled_on": forms,
            "basis_line": basis, "official_note": "이 초안은 공개 양식을 본떠 만든 것이며 공식 양식 자체가 아닙니다.",
            "blocks": blocks, "footnotes": list(t.get("footnotes", [])),
            "sources": [f"출처: 제주데이터허브, {cat.KINDS['hub_biz_sex']['label']}({_span([d['yoy_month'], d['month']])})"],
            "limits": [narrate.LIMIT_TEXT], "cannot_fill": [], "summary": summary,
            "check_sentences": [f"{ml} 카드 이용금액이 가장 큰 업종은 한식 음식점업이다"]}


# ---- bizplan_market --------------------------------------------------------------------------------
def bizplan_result(res, u, store):
    hub = store.library("hub_biz_sex")
    info = store.library_info("hub_biz_sex")
    biz = u["biz"]
    lib_month = calc.latest_month(hub)
    local, synthetic, masked = None, False, False
    act = store.active()
    center_used = False
    if u["place"]:
        place = (u["place"]["field"], u["place"]["value"])
        if act and act["kind"] in ("c108", "c112", "c114") and act["has"].get("bjd"):
            rows = store.rows()
            lm = act["months"][-1]
            summ, _ = calc.summary(rows, lm, biz, place, act["export_check"])
            pm = calc.prev_year(lm)
            need = [] if pm in act["months"] else [{"dataset": act["label"], "month": pm, "why": "전년 동월 비교"}]
            local = {"bjd": place[1], "month": lm, "summary": summ, "need": need}
            synthetic = act["synthetic"]
            masked = bool(summ["export"]["masked_groups"])
            center_used = True
        else:
            local = {"bjd": place[1], "month": None, "summary": None,
                     "need": [{"dataset": cat.REGION_DATASET, "month": lib_month, "why": "지역 상세"}]}
    data = calc.bizplan_market(hub, biz, store.library("hub_sexage"), store.library("hub_weekday"),
                               store.library("hub_time"), local)
    res["intent"].update(month=data["month"], biz=biz, groups=list(cat.ORDER))
    win24 = [calc.shift(data["month"], -k) for k in range(23, -1, -1)]
    wset = set(win24)
    rows_used = sum(1 for r in hub if r["biz"] == biz and r["month"] in wset)
    tables = [eda_table(cat.KINDS["hub_biz_sex"]["label"], PUBLIC_SOURCE, hub, info["months"], has_users=True)]
    sexage = store.library("hub_sexage")
    qs = sorted({(r["base_year"], r["base_quarter"]) for r in sexage})
    tables.append(eda_table(cat.LIBRARY_KINDS["hub_sexage"]["label"], PUBLIC_SOURCE, sexage, [], has_users=False,
                            biz_key="biz_name", span=(f"{qs[0][0]} {qs[0][1]}–{qs[-1][0]} {qs[-1][1]}" if qs else "")))
    for kind in ("hub_weekday", "hub_time"):
        lrows = store.library(kind)
        tables.append(eda_table(cat.LIBRARY_KINDS[kind]["label"], PUBLIC_SOURCE, lrows,
                                sorted({r["base_year_month"] for r in lrows}), has_users=False))
    if center_used:
        tables.append(eda_table(act["label"], act["source"], store.rows(), act["months"], has_users=True))
    reading = {"last3": calc.last3_direction(data["series"]), "peak": data["season"]["max"]["month"]}
    rtext = {"increase": "최근 석 달은 계속 늘었습니다", "decrease": "최근 석 달은 계속 줄었습니다",
             "mixed": "최근 석 달은 오르내렸습니다"}[reading["last3"]]
    reading["text"] = f"{biz}의 12개월 흐름: {rtext}. 가장 많은 달은 {narrate.month_label(reading['peak'])}입니다."
    allowed = narrate.allowed_tokens(data, tables, months=win24)
    eda = {"tables": tables, "reading": reading, "lines": _guard_texts([t["text"] for t in tables] + [reading["text"]], allowed)}
    draft = bizplan_draft(data, allowed, act if center_used else None)
    out = _doc_result(res, "bizplan_market", data, eda, draft, active_like=_lib_active(store),
                      months_used=[data["window"]["start"], data["month"]], rows_used=rows_used,
                      formula="최근 12개월과 그 전 12개월의 업종 이용금액 합계, 고객 구분별 비중, 분기별 성별·연령 비중",
                      synthetic=synthetic, masked=masked)
    # The window is a contiguous 12-month range: cite it as start–end (en dash), not as two months.
    ev = out.get("evidence") or {}
    if ev.get("citation"):
        lib = _lib_active(store)
        src = _agent().SOURCE_SHORT.get(lib["source"], lib["source"])
        ev["citation"] = (f"출처: {src}, {lib['label']}"
                          f"({narrate.month_dash(data['window']['start'])}–{narrate.month_dash(data['month'])})")
    return out


def _local_block(d, biz):
    loc = d["local"]
    title = "지역 상세(센터 자료를 넣었을 때)"
    if loc is None:
        return {"id": "local", "title": title, "text": f"지역 상세는 센터의 '{cat.REGION_DATASET}' 표를 받아 넣으면 채울 수 있습니다.", "table": None}
    if loc["summary"] is None:
        return {"id": "local", "title": title,
                "text": f"{loc['bjd']} 상세는 센터의 '{cat.REGION_DATASET}' 표를 받아 넣으면 채울 수 있습니다.", "table": None}
    sm = loc["summary"]
    if sm["export"]["masked_groups"]:
        txt = (f"{loc['bjd']} {biz}의 {narrate.month_label(loc['month'])} 자료에는 작은 값이 있어 반출 사전 점검 기준에 따라 "
               "일부 구분과 합계, 비중을 가렸습니다.")
    else:
        txt = (f"{loc['bjd']} {biz}의 {narrate.month_label(loc['month'])} 카드 이용금액은 "
               f"{narrate.value_text(sm['total']['amount'], 'amount')}이며, "
               + ", ".join(f"{narrate.GROUP_LABELS[g['group']]} {narrate.pct_text(g['amount_share_pct'])}" for g in sm["groups"]) + "입니다.")
    if loc["need"]:
        txt += (" 전년 같은 달과 비교하려면 " + ", ".join(f"'{n['dataset']}' {narrate.month_label(n['month'])}" for n in loc["need"])
                + " 자료를 더 받아 넣어 주세요.")
    rows = [[narrate.GROUP_LABELS[g["group"]], MASKED_CELL if g.get("masked") else narrate.num(g["amount"]),
             "-" if g["amount_share_pct"] is None else g["amount_share_pct"]] for g in sm["groups"]]
    return {"id": "local", "title": title, "text": txt,
            "table": {"title": "읍면동 이용자 구분별 표(반출 사전 점검 적용)", "columns": ["구분", "이용금액(원)", "비중(%)"], "rows": rows}}


def bizplan_draft(d, allowed, center):
    t, forms, basis = template_info("bizplan_market")
    biz = d["biz"]
    s, y = d["size"], d["yoy"]
    start, end = narrate.month_label(d["window"]["start"]), narrate.month_label(d["window"]["end"])
    blocks = [{"id": "size", "title": "시장 규모와 추이",
               "text": (f"{biz}의 최근 12개월({start}–{end}) 비씨카드 이용금액은 {mil(s['amount_12m'])}백만원으로, "
                        f"월평균 {mil(s['monthly_avg'])}백만원입니다. 그 전 12개월({mil(s['prev_amount_12m'])}백만원)보다 "
                        f"{narrate.pct_text(s['pct_12m'])} {_change_word(s['pct_12m'])}했습니다."),
               "table": {"title": "최근 12개월 월별 카드 이용금액", "columns": ["달", "이용금액(백만원)"],
                         "rows": [[narrate.month_label(x["month"]), mil(x["amount"])] for x in d["series"]]}},
              {"id": "yoy", "title": "전년 동월 대비",
               "text": (f"{end} 이용금액은 {mil(y['current'])}백만원으로 전년 같은 달({mil(y['previous'])}백만원)보다 "
                        f"{narrate.pct_text(y['pct'])} {_change_word(y['pct'])}했습니다. 건당 이용금액은 {narrate.num(d['per_use'])}원입니다."),
               "table": None}]
    mix = d["mix"]
    blocks.append({"id": "mix", "title": "고객 구성(도민·내국인 관광객·외국인·법인)",
                   "text": "12개월 이용금액 비중은 " + ", ".join(f"{narrate.GROUP_LABELS[m['group']]} {narrate.pct_text(m['share_pct'])}" for m in mix) + "입니다.",
                   "table": {"title": "12개월 이용금액 비중", "columns": ["구분", "이용금액(백만원)", "비중(%)"],
                             "rows": [[narrate.GROUP_LABELS[m["group"]], mil(m["amount"]), m["share_pct"] or "-"] for m in mix]}})
    sa = d["sex_age"]
    if sa:
        known = [a for a in sa["by_age"] if a["age"] != "알수없음"]
        topa = sorted(known, key=lambda a: -a["amount_million"])[0] if known else None
        sex = {x["sex"]: x for x in sa["by_sex"]}
        text = ""
        if topa:
            text = (f"최근 분기({sa['quarters'][0]}–{sa['quarters'][-1]}) 이용금액은 {topa['age']}가 "
                    f"{narrate.pct_text(topa['share_pct'])}로 가장 많고, 남성 {narrate.pct_text(sex['남성']['share_pct'])}, "
                    f"여성 {narrate.pct_text(sex['여성']['share_pct'])}입니다.")
        table = {"title": "최근 분기 이용금액 비중", "columns": ["구분", "이용금액(백만원)", "비중(%)"],
                 "rows": [[a["age"], narrate.num(a["amount_million"]), a["share_pct"] or "-"] for a in sa["by_age"]]
                 + [[x["sex"], narrate.num(x["amount_million"]), x["share_pct"] or "-"] for x in sa["by_sex"]]}
    else:
        text, table = "이 업종은 성별·연령 분기 자료에 없어 이 칸은 비워 둡니다.", None
    blocks.append({"id": "sex_age", "title": "성별·연령 구성", "text": text, "table": table})
    se = d["season"]
    blocks.append({"id": "season", "title": "계절성",
                   "text": (f"최근 12개월 가운데 이용금액이 가장 많은 달은 {narrate.month_label(se['max']['month'])}"
                            f"({mil(se['max']['amount'])}백만원), 가장 적은 달은 {narrate.month_label(se['min']['month'])}"
                            f"({mil(se['min']['amount'])}백만원)입니다."), "table": None})
    ctx = d["context"]
    ctext, crows = "", []
    if ctx.get("weekday") and ctx.get("time"):
        wd = sorted(ctx["weekday"]["shares"], key=lambda x: -x["uses"])[0]
        tm = sorted(ctx["time"]["shares"], key=lambda x: -x["amount_million"])[0]
        ctext = (f"제주 전체(업종 구분 없음) 기준으로 {narrate.month_label(ctx['weekday']['month'])} 이용건수는 "
                 f"{josa_day(wd['day'])} {narrate.pct_text(wd['share_pct'])}로 가장 많고, {narrate.month_label(ctx['time']['month'])} "
                 f"시간대별 이용금액은 {narrate.josa(tm['time'], '이/가')} {narrate.pct_text(tm['share_pct'])}로 가장 많습니다. 이 업종만의 값은 아닙니다.")
        crows = ([["요일 " + x["day"], x["share_pct"] or "-"] for x in ctx["weekday"]["shares"]]
                 + [["시간대 " + x["time"], x["share_pct"] or "-"] for x in ctx["time"]["shares"]])
    blocks.append({"id": "context", "title": "요일·시간대 참고(제주 전체, 업종 구분 없음)", "text": ctext,
                   "table": {"title": "요일별 이용건수 비중, 시간대별 이용금액 비중", "columns": ["구분", "비중(%)"], "rows": crows}})
    blocks.append(_local_block(d, biz))
    for bl in blocks:
        if bl["text"]:
            bl["text"] = _guard_texts([bl["text"]], allowed)[0]
    sources = [f"출처: 제주데이터허브, {cat.KINDS['hub_biz_sex']['label']}({_span([calc.shift(d['month'], -23), d['month']])})",
               f"출처: 제주데이터허브, {cat.LIBRARY_KINDS['hub_sexage']['label']}",
               f"출처: 제주데이터허브, {cat.LIBRARY_KINDS['hub_weekday']['label']}, {cat.LIBRARY_KINDS['hub_time']['label']}"]
    limits = [narrate.LIMIT_TEXT, "요일·시간대 값은 제주 전체 값이며 이 업종만의 값이 아닙니다."]
    if center:
        sources.append(f"출처: 제주빅데이터센터, {center['label']}({_span(center['months'])})")
        if center.get("synthetic"):
            limits.append("가상 데이터 시연(실제 수치가 아닙니다)")
    cannot = [{"item": "경쟁 강도", "text": "이 자료로는 쓸 수 없습니다", "request": "센터의 '제주도 내 업종별 매장 수' 자료를 받아 주세요"},
              {"item": "향후 전망", "text": "이 자료로는 쓸 수 없습니다", "request": "전망은 지난 자료로 확인할 수 없어 근거를 직접 적어 주세요"}]
    summary = blocks[0]["text"] + " 사업계획서 시장·고객 현황 초안을 아래에 만들었습니다."
    return {"template": "bizplan_market", "title": t.get("label", "사업계획서: 시장·고객 현황 칸"), "modelled_on": forms,
            "basis_line": basis, "official_note": "이 초안은 공개 양식을 본떠 만든 것이며 공식 양식 자체가 아닙니다.",
            "blocks": blocks, "footnotes": list(t.get("footnotes", [])), "sources": sources, "limits": limits,
            "cannot_fill": cannot, "summary": summary,
            "check_sentences": [f"{biz}은 내국인 관광객이 도민보다 많이 썼다", f"{biz} 카드 이용금액이 작년 같은 달보다 늘었다"]}


def josa_day(day: str) -> str:
    return narrate.josa(day, "이/가")


# ---- data_brief ------------------------------------------------------------------------------------
def brief_result(res, u, store):
    act = store.active()
    center = bool(act and act["kind"] in ("c108", "c112", "c114"))
    if center:
        rows, months, label, export_check, dataset = store.rows(), act["months"], act["label"], act["export_check"], act["label"]
        active_like = act
    else:
        rows = store.library("hub_biz_sex")
        months = store.library_info("hub_biz_sex")["months"]
        label, export_check, dataset = cat.KINDS["hub_biz_sex"]["label"], False, None
        active_like = _lib_active(store)
    place = None
    if u["place"]:
        if not center or not act["has"].get("bjd"):
            res.update(behavior="need_file", data={"missing": "region", "dataset": cat.REGION_DATASET, "month": None},
                       message=narrate.need_file_message("region", cat.REGION_DATASET, None))
            return res
        place = (u["place"]["field"], u["place"]["value"])
    if u["month_explicit"]:
        if u["month"] not in months:
            return _need_month(res, u["month"], dataset)
        month, default = u["month"], False
    else:
        month, default = months[-1], True
    biz = u["biz"]
    data, used = calc.data_brief(rows, month, biz, place, export_check, dataset)
    res["intent"].update(month=month, biz=biz)
    tables = [eda_table(label, active_like["source"], rows, months, has_users=True)]
    used_months = [month] + ([calc.prev_year(month)] if data["yoy"] else [])
    allowed = narrate.allowed_tokens(data, tables, months=used_months)
    eda = {"tables": tables, "reading": None, "lines": _guard_texts([t["text"] for t in tables], allowed)}
    sm = data["summary"]
    masked = bool(sm["export"]["masked_groups"]) or bool(data["yoy"] and data["yoy"]["export"]["masked"])

    def cell(g, k):
        return MASKED_CELL if g.get("masked") else narrate.num(g[k])
    blocks = [{"id": "headline", "title": "한 줄 요약", "text": narrate.summary_message(sm), "table": None},
              {"id": "mix", "title": "고객 구성 표", "text": "",
               "table": {"title": "구분별 카드 이용", "columns": ["구분", "행 수", "이용자 수", "이용건수", "이용금액(원)", "비중(%)"],
                         "rows": [[narrate.GROUP_LABELS[g["group"]], narrate.num(g["rows"]), cell(g, "users"), cell(g, "uses"),
                                   cell(g, "amount"), g["amount_share_pct"] or "-"] for g in sm["groups"]]}}]
    if data["yoy"]:
        blocks.append({"id": "yoy", "title": "전년 동월 대비", "text": narrate.yoy_summary_message(data["yoy"]), "table": None})
    else:
        n = data["need"][0]
        where = f"센터의 '{n['dataset']}' 표" if n["dataset"] else "그 달이 든 자료"
        blocks.append({"id": "yoy", "title": "전년 동월 대비",
                       "text": f"전년 같은 달과 비교하려면 {where}를 {narrate.month_label(n['month'])}로 받아 넣어 주세요.", "table": None})
    for bl in blocks:
        if bl["text"]:
            bl["text"] = _guard_texts([bl["text"]], allowed)[0]
    limits = [narrate.LIMIT_TEXT]
    if active_like.get("synthetic"):
        limits.append("가상 데이터 시연(실제 수치가 아닙니다)")
    fmt = next((f for f in formats("card") if f["id"] == "data_brief"), None)
    src_short = "제주빅데이터센터" if center else "제주데이터허브"
    draft = {"template": "data_brief", "title": fmt["title"] if fmt else "자료 요약", "modelled_on": [],
             "basis_line": fmt["basis_line"] if fmt else "", "official_note": "자체 제작 양식입니다.",
             "blocks": blocks, "footnotes": [], "sources": [f"출처: {src_short}, {label}({_span(used_months)})"],
             "limits": limits, "cannot_fill": [], "summary": blocks[0]["text"],
             "check_sentences": [f"{biz}은 내국인 관광객이 도민보다 많이 썼다", f"{biz} 카드 이용금액이 작년 같은 달보다 늘었다"]}
    return _doc_result(res, "data_brief", data, eda, draft, active_like=active_like, months_used=used_months, rows_used=used,
                       formula="구분별 합계(R3)와 전년 같은 달 비교(R5), 센터 자료는 반출 사전 점검(R8)",
                       synthetic=bool(active_like.get("synthetic")), masked=masked, month_default=default)
