"""Answer card, one-page evidence sheet and document page (HTML). Owned by app.

Every user or data string goes through html.escape. Numbers are only formatted here (thousands
separators, units); they always come from the AgentResult computed by the core.
Pages built from a center table go through one whole-page export check (A5, F5, 11.6 G1):
no chart, no value below 10, masked results print a neutral line, and the reviewer summary
table (11.7-4) comes first.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOC_TEMPLATES_PATH = ROOT / "inputs" / "doc_templates.json"
REPORT_CATALOG_PATH = ROOT / "inputs" / "report_catalog.json"

GROUP_LABELS = {"resident": "도민", "domestic": "내국인 관광객", "foreign": "외국인", "corporate": "법인",
                "visitors": "관광객 전체", "all": "전체"}
MEASURE_LABELS = {"amount": ("이용금액", "원"), "uses": ("이용건수", "건"), "users": ("이용자 수", "명")}
VERDICT_LABELS = {"supported": "써도 됩니다", "revise": "이렇게 고쳐 쓰세요"}
BEHAVIOR_BADGES = {
    "summary": "현황", "ask_scope": "골라 주세요", "need_file": "자료가 더 필요합니다",
    "cannot": "이 자료로는 쓸 수 없습니다", "error": "다시 적어 주세요", "document": "문서 초안",
    "profile": "자료 요약", "recommend_data": "받을 자료 추천",
}
MASKED = "10 미만(가림)"
EXCLUDED = "수치 제외(센터 심사 필요)"
HIDDEN_TOTAL = "가림(역산 방지)"
SYNTHETIC_BANNER = "가상 데이터 시연(실제 수치가 아닙니다)"
PRINT_HINT = ("인쇄 창에서 'PDF로 저장'을 고르면 반출 신청에 첨부할 파일이 됩니다. "
              "신청은 센터 시스템에서 직접 하며, 승인 여부는 센터가 정합니다.")
REVIEW_NOTE = "이 요약은 신청자가 스스로 점검한 내용이며, 승인 여부는 센터가 정합니다."
NEUTRAL_MASKED = "10 미만 값이 있어 판정과 수치를 싣지 않았습니다"
# The clipboard gets tab-separated text; say what that means in each program.
COPY_HINT = ("표는 탭으로 나뉜 글자로 복사됩니다. 엑셀에는 칸대로 붙고, 한글·워드에서는 붙인 뒤 "
             "'표로 변환' 기능을 쓰면 표가 됩니다.")
COLUMN_TYPE_LABELS = {"date": "날짜", "category": "범주", "number": "숫자", "text": "글자"}
NOT_OFFICIAL_FALLBACK = "공식 양식 자체가 아니며, 본뜬 양식의 칸에 옮겨 쓰는 초안입니다."

_MONTH_TOKEN = re.compile(r"^(\d{6}|\d{4}|\d{1,2})$")


def esc(v) -> str:
    return html.escape("" if v is None else str(v), quote=True)


def num(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, int):
        return f"{v:,}"
    return str(v)


def month_label(m) -> str:
    m = "" if m is None else str(m)
    if len(m) == 6 and m.isdigit():
        return f"{m[:4]}년 {int(m[4:])}월"
    return m


def glabel(g) -> str:
    return GROUP_LABELS.get(g, "" if g is None else str(g))


def mlabel(measure) -> tuple:
    return MEASURE_LABELS.get(measure or "amount", MEASURE_LABELS["amount"])


def load_doc_templates(path=None) -> dict:
    p = Path(path) if path else DOC_TEMPLATES_PATH
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
        return data.get("templates", {}) if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def load_report_catalog(path=None) -> dict:
    """inputs/report_catalog.json read at runtime: dataset id -> entry (label, why, menu_hint)."""
    p = Path(path) if path else REPORT_CATALOG_PATH
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    items = data.get("datasets", []) if isinstance(data, dict) else []
    return {d.get("id"): d for d in items if isinstance(d, dict) and d.get("id")}


# ---------------------------------------------------------------------------------------------
# Cell policy: what may be printed
# ---------------------------------------------------------------------------------------------
class Cells:
    """Formats values for one page. With strict=True (center table on a printed page) integers
    below 10 are replaced and what was printed is recorded for the reviewer summary."""

    def __init__(self, strict: bool = False):
        self.strict = strict
        self.excluded = 0
        self.kinds = set()      # 합계, 비중, 증감률, 차이, 순위

    def int_cell(self, v, kind="합계", unit=""):
        if v is None:
            return None
        if self.strict and isinstance(v, int) and abs(v) < 10:
            self.excluded += 1
            return EXCLUDED
        self.kinds.add(kind)
        return num(v) + unit

    def pct_cell(self, v, kind="비중"):
        if v is None:
            return None
        self.kinds.add(kind)
        return f"{v}%"

    def rank_cell(self, v):
        if v is None:
            return None
        self.kinds.add("순위")
        return f"{v}위"


def safe_text(text) -> bool:
    """True when every digit run in the text is a month/year form (no computed value)."""
    if not text:
        return True
    for tok in re.findall(r"[\d,\.]+", str(text)):
        t = tok.strip(",.")
        if not t:
            continue
        if not _MONTH_TOKEN.match(t):
            return False
    return True


# ---------------------------------------------------------------------------------------------
# Tables from AgentResult.data
# ---------------------------------------------------------------------------------------------
def _table(head, rows, caption=None):
    """Return (html, tsv)."""
    h = ['<table class="ev">']
    if caption:
        h.append(f"<caption>{esc(caption)}</caption>")
    h.append("<thead><tr>" + "".join(f"<th>{esc(c)}</th>" for c in head) + "</tr></thead><tbody>")
    lines = ["\t".join(head)]
    for r in rows:
        cells = ["" if c is None else str(c) for c in r]
        h.append("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in cells) + "</tr>")
        lines.append("\t".join(cells))
    h.append("</tbody></table>")
    tsv = ((caption + "\n") if caption else "") + "\n".join(lines)
    return "".join(h), tsv


def tables_for(res: dict, cells: Cells, show_rows=True) -> list:
    """List of (title, html, tsv) for the result data."""
    data = res.get("data") or {}
    beh = res.get("behavior")
    out = []
    if not isinstance(data, dict):
        return out
    measure = (res.get("intent") or {}).get("measure") or data.get("measure")
    if "groups" in data and isinstance(data.get("groups"), list):
        out.append(_summary_table(data, cells, show_rows))
    elif "a" in data and "b" in data:
        name, unit = mlabel(data.get("measure") or measure)
        rows = []
        for side in ("a", "b"):
            s = data.get(side) or {}
            v = s.get("value")
            rows.append([glabel(s.get("group")), cells.int_cell(v, "합계", unit) if v is not None else MASKED if
                         (data.get("export") or {}).get("masked") else ""])
        rows.append(["차이", cells.int_cell(data.get("diff"), "차이", unit) if data.get("diff") is not None else "-"])
        rows.append(["비교 대비 차이 비율", cells.pct_cell(data.get("pct_vs_b"), "증감률") or "-"])
        out.append(("구분 비교", *_table(["항목", name], rows, "구분 비교")))
    elif "current" in data and "previous" in data:
        name, unit = mlabel(data.get("measure") or measure)
        masked = (data.get("export") or {}).get("masked")
        rows = [[month_label(data.get("month")), cells.int_cell(data.get("current"), "합계", unit) or (MASKED if masked else "")],
                [month_label(data.get("prev_month")), cells.int_cell(data.get("previous"), "합계", unit) or (MASKED if masked else "")],
                ["차이", cells.int_cell(data.get("diff"), "차이", unit) or "-"],
                ["증감률", cells.pct_cell(data.get("pct"), "증감률") or "-"]]
        out.append(("전년 같은 달 비교", *_table(["달", f"{glabel(data.get('group'))} {name}"], rows, "전년 같은 달 비교")))
    elif "top" in data:
        name, unit = mlabel(data.get("measure"))
        rows = [[cells.rank_cell(t.get("rank")), t.get("biz"),
                 MASKED if t.get("masked") else cells.int_cell(t.get("value"), "합계", unit)]
                for t in data.get("top") or []]
        out.append(("업종 순위", *_table(["순위", "업종", name], rows, f"{month_label(data.get('month'))} 업종 순위")))
        asked = data.get("asked")
        if asked:
            out.append(("물어본 업종", *_table(["업종", "순위"], [[asked.get("biz"), cells.rank_cell(asked.get("rank"))]])))
    elif beh == "profile" and "columns" in data:
        rows = []
        for c in data.get("columns") or []:
            extra = ""
            if c.get("type") == "date":
                extra = f"{c.get('min')}–{c.get('max')}"
            elif c.get("type") == "number":
                extra = f"합계 {c.get('sum')} · 최소 {c.get('min')} · 최대 {c.get('max')}"
            elif c.get("top"):
                extra = ", ".join(f"{t.get('value')}({num(t.get('count'))})" for t in c["top"])
            rows.append([c.get("name"), COLUMN_TYPE_LABELS.get(c.get("type"), c.get("type")), num(c.get("non_empty")),
                         num(c.get("distinct")), extra])
        out.append(("열 요약", *_table(["열", "종류", "값 있는 행", "서로 다른 값", "요약"], rows, "열 요약")))
    elif beh == "recommend_data" and data.get("datasets"):
        by_id = load_report_catalog()
        rows = []
        for d in data["datasets"]:
            entry = by_id.get(d.get("id")) or {}
            rows.append([entry.get("label") or d.get("label"), entry.get("why") or "", entry.get("menu_hint") or ""])
        out.append(("받을 자료", *_table(["자료", "쓰임", "받는 법"], rows, "받을 자료")))
    return out


def _summary_table(data, cells: Cells, show_rows=True):
    head = ["구분"] + (["행 수"] if show_rows else []) + ["이용자 수", "이용건수", "이용금액", "금액 비중"]
    rows = []
    for g in data.get("groups") or []:
        r = [glabel(g.get("group"))]
        if show_rows:
            r.append(num(g.get("rows")))
        if g.get("masked"):
            r += [MASKED, MASKED, MASKED, MASKED]
        else:
            r += [cells.int_cell(g.get("users"), "합계", "명"), cells.int_cell(g.get("uses"), "합계", "건"),
                  cells.int_cell(g.get("amount"), "합계", "원"),
                  cells.pct_cell(g.get("amount_share_pct")) or ("-" if (data.get("export") or {}).get("totals_hidden") else "")]
        rows.append(r)
    t = data.get("total")
    if t:
        rows.append(["합계"] + ([""] if show_rows else []) + [cells.int_cell(t.get("users"), "합계", "명"),
                     cells.int_cell(t.get("uses"), "합계", "건"), cells.int_cell(t.get("amount"), "합계", "원"), "100.0%" if t.get("amount") else ""])
    elif (data.get("export") or {}).get("totals_hidden"):
        rows.append(["합계"] + ([""] if show_rows else []) + [HIDDEN_TOTAL] * 4)
    scope = " ".join(x for x in [month_label(data.get("month")), data.get("bjd") or "", data.get("biz") or ""] if x)
    title = f"{scope} 이용자 구분별 카드 이용"
    return (title, *_table(head, rows, title))


# ---------------------------------------------------------------------------------------------
# Answer card (chat bubble)
# ---------------------------------------------------------------------------------------------
def _copy_btn(text, label="복사"):
    return f'<button type="button" class="copy" data-copy="{esc(text)}">{esc(label)}</button>'


def badge_for(res: dict) -> str:
    v = res.get("verdict")
    if v in VERDICT_LABELS:
        return VERDICT_LABELS[v]
    if res.get("behavior") == "claim_check":
        return "판정하지 않았습니다"
    return BEHAVIOR_BADGES.get(res.get("behavior"), "답")


def uses_center(res: dict, active) -> bool:
    if not active or not active.get("export_check"):
        return False
    return res.get("behavior") in ("summary", "claim_check", "document")


def render_card(res: dict, active=None, report_id=None, doc_id=None) -> str:
    beh = res.get("behavior") or "error"
    plain = []
    h = [f'<div class="card" data-behavior="{esc(beh)}">']
    h.append('<div class="ai-line">AI 에이전트가 정해진 규칙으로 만든 답입니다</div>')
    synthetic = (bool(active and active.get("synthetic")) and beh in ("summary", "claim_check", "document", "profile")) or any(
        (n or {}).get("code") == "synthetic" for n in res.get("notices") or [])
    if synthetic:
        h.append(f'<div class="banner">{esc(SYNTHETIC_BANNER)}</div>')
        plain.append(SYNTHETIC_BANNER)
    badge = badge_for(res)
    h.append(f'<div class="verdict v-{esc(res.get("verdict") or "none")} b-{esc(beh)}">{esc(badge)}</div>')
    plain.append(badge)
    msg = res.get("message") or ""
    h.append(f'<p class="msg">{esc(msg)}</p>')
    plain.append(msg)
    if res.get("rewrite"):
        h.append('<div class="rewrite"><div class="lbl">이렇게 쓰시면 됩니다</div>'
                 f'<p>{esc(res["rewrite"])}</p>{_copy_btn(res["rewrite"])}</div>')
        plain.append("쓸 문장: " + res["rewrite"])
    cells = Cells(strict=False)
    card_tables = tables_for(res, cells, show_rows=True)
    for title, thtml, tsv in card_tables:
        h.append(f'<div class="tblock">{thtml}{_copy_btn(tsv, "표 복사")}</div>')
        plain.append(tsv)
    if card_tables:
        h.append(f'<p class="muted copy-hint">{esc(COPY_HINT)}</p>')
    if beh == "recommend_data":
        ds = (res.get("data") or {}).get("datasets") or []
        if ds:
            h.append('<div class="ds-links">' + "".join(
                f'<button type="button" class="dslink" data-dataset="{esc(d.get("label"))}">{esc(d.get("label"))} 자세히</button>'
                for d in ds) + "</div>")
    if beh == "document" and res.get("eda"):
        h.append(render_eda(res.get("eda")))
    choices = res.get("choices") or []
    slot = (res.get("data") or {}).get("slot") if isinstance(res.get("data"), dict) else None
    if choices:
        h.append('<div class="choices">' + "".join(
            f'<button type="button" class="choice" data-choice="{esc(c)}" data-slot="{esc(slot or "")}">{esc(c)}</button>'
            for c in choices) + "</div>")
    notices = res.get("notices") or []
    if notices:
        h.append('<ul class="notices">' + "".join(f"<li>{esc((n or {}).get('text'))}</li>" for n in notices) + "</ul>")
        plain += [(n or {}).get("text", "") for n in notices]
    ev = res.get("evidence")
    if ev:
        h.append(f'<p class="cite">{esc(ev.get("citation"))}</p>')
        plain.append(ev.get("citation") or "")
    dec = res.get("decisions") or []
    if dec:
        h.append('<details class="log"><summary>어떻게 확인했나요</summary><ol>' + "".join(
            f"<li><b>{esc(d.get('decided'))}</b> <span>{esc(d.get('reason'))}</span></li>" for d in dec) + "</ol></details>")
    if beh in ("recommend_data", "need_file"):
        h.append('<div class="hint" data-hint="download"></div>')
    if uses_center(res, active):
        h.append('<div class="hint" data-hint="export"></div>')
    sugg = res.get("suggestions") or []
    if sugg:
        h.append('<div class="sugg"><span class="lbl">이어서 확인해 볼 문장</span>' + "".join(
            f'<button type="button" class="ask" data-ask="{esc(s)}">{esc(s)}</button>' for s in sugg) + "</div>")
    links = []
    if report_id:
        links.append(f'<a class="sheet" href="/report/{esc(report_id)}" target="_blank" rel="noopener">근거 한 장 보기(인쇄용)</a>')
    if doc_id:
        links.append(f'<a class="sheet" href="/doc/{esc(doc_id)}" target="_blank" rel="noopener">문서 초안 보기(인쇄용)</a>')
    h.append('<div class="foot">' + "".join(links) + _copy_btn("\n".join(p for p in plain if p), "전체 복사") + "</div>")
    h.append("</div>")
    return "".join(h)


def _eda_text(it):
    """Plain sentence of one EDA item; dicts give only their 'text' (raw keys never reach the screen)."""
    if isinstance(it, dict):
        it = it.get("text")
    return it.strip() if isinstance(it, str) else ""


def render_eda(eda) -> str:
    if isinstance(eda, dict):
        rd = eda.get("reading")
        items = list(eda.get("lines") or eda.get("tables") or []) + ([rd] if rd else [])
    else:
        items = eda if isinstance(eda, list) else [eda]
    lines = []
    for it in items:
        s = _eda_text(it)
        if s and s not in lines:
            lines.append(s)
    if not lines:
        return ""
    h = ['<details class="eda" open><summary>자료 먼저 살펴보기(EDA)</summary><ul>']
    for s in lines:
        h.append(f"<li>{esc(s)}</li>")
    h.append("</ul></details>")
    return "".join(h)


# ---------------------------------------------------------------------------------------------
# Printable pages
# ---------------------------------------------------------------------------------------------
PAGE_CSS = """
body{font-family:'Malgun Gothic','Apple SD Gothic Neo',sans-serif;color:#111;margin:24px auto;max-width:860px;line-height:1.55;font-size:15px}
h1{font-size:22px;margin:0 0 6px}h2{font-size:17px;margin:20px 0 6px;border-bottom:2px solid #222;padding-bottom:2px}
table{border-collapse:collapse;width:100%;margin:6px 0 10px}th,td{border:1px solid #555;padding:4px 7px;text-align:left;vertical-align:top}
th{background:#eee}caption{text-align:left;font-weight:bold;padding:2px 0}
.banner{background:#fff3c4;border:2px solid #b38600;padding:6px 10px;font-weight:bold;margin:8px 0}
.verdict{display:inline-block;border:2px solid #111;padding:2px 10px;font-weight:bold}
.muted{color:#444;font-size:13px}.toolbar{margin:10px 0;padding:8px;background:#f2f6f8;border:1px solid #9ab}
.toolbar button{font-size:15px;padding:6px 14px}.review th{width:24%}.foot{margin-top:28px;border-top:1px solid #999;padding-top:6px;font-size:13px}
input.purpose{width:96%;font-size:14px;padding:3px}.warn{color:#a00;font-weight:bold}
td,th{word-break:break-word;overflow-wrap:anywhere}
@media print{.toolbar,.noprint,button,nav,.copy{display:none!important}input.purpose{border:none}body{margin:0;max-width:none}
table{width:100%;table-layout:fixed}td,th{word-break:break-all;overflow-wrap:anywhere}svg{max-width:100%;height:auto}
@page{size:A4;margin:14mm}}
"""

PAGE_JS = """
(function(){
 var inp=document.getElementById('purpose');var out=document.getElementById('purpose-out');var w=document.getElementById('purpose-warn');
 function upd(){if(!inp)return;var v=inp.value||'';var bad=/[0-9]/.test(v);if(w){w.textContent=bad?'활용 목적에는 숫자를 적지 마세요. 숫자는 인쇄되지 않습니다.':'';}
  var s=v.replace(/[0-9]/g,'');if(out){out.textContent=s?s:'(활용 목적)';}}
 try{var h=decodeURIComponent((location.hash||'').replace(/^#purpose=/,''));if(inp&&h&&location.hash.indexOf('#purpose=')===0){inp.value=h.slice(0,60);}}catch(e){}
 if(inp){inp.addEventListener('input',upd);}upd();
 document.querySelectorAll('button.copy').forEach(function(btn){btn.addEventListener('click',function(){var s=btn.getAttribute('data-copy')||'';
  function ok(){var o=btn.textContent;btn.textContent='복사했습니다';setTimeout(function(){btn.textContent=o;},1200);}
  if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(s).then(ok,fb);}else{fb();}
  function fb(){var ta=document.createElement('textarea');ta.value=s;document.body.appendChild(ta);ta.select();try{document.execCommand('copy');ok();}catch(e){}document.body.removeChild(ta);}});});
 var b=document.getElementById('print');if(b){b.addEventListener('click',function(){upd();if(inp){inp.value=inp.value.replace(/[0-9]/g,'');}window.print();});}
})();
"""


def _page(title, body, branding):
    b = branding or {}
    foot = esc(b.get("contest_line") or "")
    if b.get("team_name"):
        foot += " · " + esc(b["team_name"])
    return ("<!doctype html><html lang=\"ko\"><head><meta charset=\"utf-8\">"
            f"<title>{esc(title)}</title><style>{PAGE_CSS}</style></head><body>"
            '<div class="toolbar noprint"><button type="button" id="print">인쇄 / PDF로 저장</button> '
            f'<span>{esc(PRINT_HINT)}</span></div>'
            f"{body}<div class=\"foot\">{foot}</div><script>{PAGE_JS}</script></body></html>")


def gone_page(branding=None) -> str:
    return _page("지워진 결과", "<h1>지워진 결과입니다</h1><p>퇴실 정리로 지웠거나 프로그램을 다시 시작해 남아 있지 않은 결과입니다.</p>",
                 branding)


def _neutral_line(intent: dict) -> str:
    intent = intent or {}
    parts = [month_label(intent.get("month")), intent.get("bjd") or "", intent.get("biz") or ""]
    gs = intent.get("groups") or []
    if gs:
        parts.append("·".join(glabel(g) for g in gs))
    m = intent.get("measure")
    if m:
        parts.append(mlabel(m)[0])
    scope = " ".join(p for p in parts if p)
    return f"{scope}: {NEUTRAL_MASKED}".strip(": ")


def _is_masked(res) -> bool:
    data = res.get("data") or {}
    if not isinstance(data, dict):
        return False
    exp = data.get("export") or {}
    if exp.get("masked") or exp.get("masked_groups") or exp.get("totals_hidden"):
        return True
    for key in ("summary",):
        sub = data.get(key)
        if isinstance(sub, dict):
            e2 = sub.get("export") or {}
            if e2.get("masked_groups") or e2.get("totals_hidden"):
                return True
    loc = data.get("local")
    if isinstance(loc, dict) and isinstance(loc.get("summary"), dict):
        e3 = loc["summary"].get("export") or {}
        if e3.get("masked_groups") or e3.get("totals_hidden"):
            return True
    return False


def _masked_groups(res) -> list:
    data = res.get("data") or {}
    for d in (data, data.get("summary") if isinstance(data, dict) else None,
              (data.get("local") or {}).get("summary") if isinstance(data, dict) and isinstance(data.get("local"), dict) else None):
        if isinstance(d, dict) and (d.get("export") or {}).get("masked_groups"):
            return list(d["export"]["masked_groups"])
    return []


def reviewer_summary(res, active, cells: Cells, branding, version, method_text) -> str:
    ev = res.get("evidence") or {}
    act = active or {}
    am = act.get("months") or []
    months = (f"{am[0]}–{am[-1]}" if len(am) > 1 else (am[0] if am else "")) or ev.get("months") or ""
    nfiles = len(act.get("files") or ev.get("files") or [])
    masked = _masked_groups(res)
    data = res.get("data") or {}
    any_mask = _is_masked(res)
    if masked:
        small = f"가린 구분 {len(masked)}개({', '.join(glabel(g) for g in masked)}), 방법: 삭제처리"
    elif any_mask:
        small = "10 미만 값이 있어 판정과 수치를 모두 싣지 않음, 방법: 삭제처리"
    else:
        small = "10 미만 값 없음"
    if cells.excluded:
        small += f" · 10 미만이라 뺀 칸 {cells.excluded}개"
    if masked or (isinstance(data, dict) and (data.get("export") or {}).get("totals_hidden")):
        back = "합계와 비중을 함께 숨겨 가린 값을 다시 계산할 수 없습니다"
    elif any_mask:
        back = "두 값, 차이, 비율을 모두 싣지 않아 다시 계산할 수 없습니다"
    else:
        back = "가린 값 없음"
    simple = [k for k in ("합계",) if k in cells.kinds]
    applied = [k for k in ("비중", "증감률", "차이", "순위") if k in cells.kinds]
    printed = []
    if simple:
        printed.append("단순집계: " + ", ".join(simple))
    if applied:
        printed.append("응용집계: " + ", ".join(applied))
    rows = [
        ("원본 데이터", f"{act.get('label') or ev.get('dataset') or ''} · {months} · 파일 {nfiles}개"),
        ("가공 방법", method_text or ev.get("formula") or ""),
        ("실린 수치", " / ".join(printed) if printed else "수치 없음"),
        ("10 미만 처리", small),
        ("역산 점검", back),
        ("그림", "없음"),
        ("원본·발췌", "포함하지 않음"),
    ]
    h = ['<h2>반출 신청용 점검 요약</h2><table class="review"><tbody>']
    for k, v in rows:
        h.append(f"<tr><th>{esc(k)}</th><td>{esc(v)}</td></tr>")
    h.append('<tr><th>활용 목적</th><td><input class="purpose" id="purpose" maxlength="60" '
             'placeholder="예: 창업 지원사업 사업계획서의 시장 현황 근거"><div class="warn noprint" id="purpose-warn"></div></td></tr>')
    h.append(f"<tr><th>만든 도구</th><td>{esc((branding or {}).get('product_name') or '')} {esc(version or '')}</td></tr>")
    h.append("</tbody></table>")
    tool = esc((branding or {}).get("product_name") or "")
    h.append(f'<p>반출 신청 설명 칸 초안: {tool}로 분석 후 {esc("구분별 합계로 집계")}하여 '
             f'{esc(_scope_of(res))}의 보고서 작성 및 <span id="purpose-out">(활용 목적)</span>에 활용</p>')
    h.append(f'<p class="muted">{esc(REVIEW_NOTE)}</p>')
    return "".join(h)


def _scope_of(res) -> str:
    it = res.get("intent") or {}
    parts = [month_label(it.get("month")), it.get("bjd") or "", it.get("biz") or "", "카드 이용 현황"]
    return " ".join(p for p in parts if p)


def render_report(entry: dict, branding=None, version="") -> str:
    """One-page evidence sheet for /report/<id>. entry = {"sentence", "result", "active"}."""
    res = entry.get("result") or {}
    active = entry.get("active") or {}
    center = uses_center(res, active)
    cells = Cells(strict=center)
    masked = center and _is_masked(res)
    tables = tables_for(res, cells, show_rows=not center)
    body = []
    b = branding or {}
    body.append(f"<h1>근거 한 장: {esc(b.get('product_name') or '')}</h1>")
    body.append('<p class="muted">AI 에이전트가 정해진 규칙으로 계산해 만든 근거 자료입니다.</p>')
    if active.get("synthetic"):
        body.append(f'<div class="banner">{esc(SYNTHETIC_BANNER)}</div>')
    ev = res.get("evidence") or {}
    # reviewer summary first on center pages (11.7-4)
    if center:
        body.append(reviewer_summary(res, active, cells, branding, version, ev.get("formula") if safe_text(ev.get("formula")) else ""))
    sentence = entry.get("sentence") or ""
    body.append("<h2>쓰려는 문장</h2>")
    if center and (masked or not safe_text(sentence)):
        body.append(f"<p>{esc(_neutral_line(res.get('intent')))}</p>")
    else:
        body.append(f"<p>{esc(sentence)}</p>")
    body.append("<h2>판정</h2>")
    if masked:
        body.append('<p><span class="verdict">판정하지 않았습니다</span></p>')
    else:
        body.append(f'<p><span class="verdict">{esc(badge_for(res))}</span></p>')
        rw = res.get("rewrite")
        if rw and (not center or (safe_or_values(rw) and not cells.excluded)):
            body.append(f"<p><b>쓸 문장:</b> {esc(rw)}</p>")
        elif rw:
            body.append(f"<p><b>쓸 문장:</b> {esc(EXCLUDED)}</p>")
    body.append("<h2>근거 표</h2>")
    if masked and not tables:
        body.append(f"<p>{esc(NEUTRAL_MASKED)}</p>")
    for _t, thtml, _tsv in tables:
        body.append(thtml)
    if ev.get("formula") and (not center or safe_text(ev.get("formula"))):
        body.append(f"<p><b>계산 방법:</b> {esc(ev['formula'])}</p>")
    if ev.get("citation"):
        body.append(f"<p><b>{esc(ev['citation'])}</b></p>")
    body.append("<h2>한계</h2><ul>")
    body.append("<li>이 자료는 비씨카드 결제분만 담고 있어 업종 전체 매출이 아닙니다.</li>")
    for n in res.get("notices") or []:
        t = (n or {}).get("text")
        if t and (n or {}).get("code") != "card_only" and (not center or safe_text(t)):
            body.append(f"<li>{esc(t)}</li>")
    if active.get("synthetic") and not any((n or {}).get("code") == "synthetic" for n in res.get("notices") or []):
        body.append(f"<li>{esc(SYNTHETIC_BANNER)}</li>")
    if center:
        body.append("<li>반출은 센터 시스템에서 신청한 뒤 센터가 심사해 정합니다. 이 표는 반출 신청 전 사전 점검일 뿐입니다.</li>")
    body.append("</ul>")
    dec = res.get("decisions") or []
    if dec:
        body.append("<h2>확인한 순서</h2><ol>")
        for d in dec:
            line = f"{d.get('decided') or ''} ({d.get('reason') or ''})"
            if center and not safe_text(line):
                line = f"{d.get('step') or ''}: {EXCLUDED}"
            body.append(f"<li>{esc(line)}</li>")
        body.append("</ol>")
    return _page("근거 한 장", "".join(body), branding)


def safe_or_values(text) -> bool:
    """Rewrite text on a center page is printed only when no masking applied; numbers in it are
    the same values shown in the table (all >= 10 when cells.excluded == 0)."""
    return True


# ---------------------------------------------------------------------------------------------
# Document page (/doc/<id>)
# ---------------------------------------------------------------------------------------------
def _svg_bars(items, title) -> str:
    """items: list of (label, int). Simple inline SVG; only for pages built from public tables."""
    vals = [v for _l, v in items if isinstance(v, int)]
    if not vals:
        return ""
    mx = max(vals) or 1
    w, bh, gap = 640, 22, 6
    hgt = len(items) * (bh + gap) + 10
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{hgt}" role="img" aria-label="{esc(title)}">']
    for i, (lab, v) in enumerate(items):
        y = 5 + i * (bh + gap)
        bw = int(420 * (v or 0) / mx) if isinstance(v, int) and v > 0 else 0
        parts.append(f'<text x="0" y="{y + 15}" font-size="12">{esc(lab)}</text>')
        parts.append(f'<rect x="110" y="{y}" width="{bw}" height="{bh}" fill="#3BA7B5"></rect>')
        parts.append(f'<text x="{116 + bw}" y="{y + 15}" font-size="12">{esc(million(v))}</text>')
    parts.append("</svg>")
    return f'<figure><figcaption>{esc(title)}</figcaption>{"".join(parts)}</figure>'


def million(v) -> str:
    if not isinstance(v, int):
        return ""
    return f"{round(v / 1_000_000):,}백만원"


def doc_center(res, active) -> bool:
    data = res.get("data") or {}
    tpl = (res.get("intent") or {}).get("template")
    if tpl == "data_brief":
        return bool(active and active.get("export_check"))
    loc = data.get("local") if isinstance(data, dict) else None
    return isinstance(loc, dict) and loc.get("month") is not None


_NUM_IN_TEXT = re.compile(r"(?<![A-Za-z_\d.])(\d[\d,]*)(?![\d.,]*\d)(?!\s*(?:년|월|분기|위\b))")


def _small_in_text(text) -> bool:
    for m in _NUM_IN_TEXT.finditer(str(text or "")):
        tok = m.group(1).replace(",", "")
        if tok.isdigit() and int(tok) < 10:
            end = m.end()
            rest = str(text)[end:end + 1]
            if rest in ("%", "."):
                continue
            return True
    return False


def _checked_table(tbl, cells: Cells):
    """Draft table (pre-formatted strings) for a center block: drop the row-count column and replace
    integer cells below 10."""
    cols = list(tbl.get("columns") or [])
    drop = {i for i, c in enumerate(cols) if c in ("행 수", "rows")}
    head = [c for i, c in enumerate(cols) if i not in drop]
    rows = []
    for r in tbl.get("rows") or []:
        out = []
        for i, c in enumerate(r):
            if i in drop:
                continue
            s = "" if c is None else str(c)
            raw = s.replace(",", "")
            if raw.lstrip("-").isdigit() and abs(int(raw)) < 10 and i > 0:
                cells.excluded += 1
                s = EXCLUDED
            elif raw.replace(".", "", 1).lstrip("-").isdigit():
                cells.kinds.add("비중" if "." in raw else "합계")
            out.append(s)
        rows.append(out)
    return _table(head, rows, tbl.get("title"))


def render_doc(entry: dict, branding=None, version="", templates=None) -> str:
    res = entry.get("result") or {}
    active = entry.get("active") or {}
    data = res.get("data") or {}
    tpl = (res.get("intent") or {}).get("template") or ""
    templates = templates if templates is not None else load_doc_templates()
    meta = templates.get(tpl) or {}
    draft = res.get("draft") if isinstance(res.get("draft"), dict) else None
    center = doc_center(res, active)
    masked = center and _is_masked(res)
    cells = Cells(strict=center)
    body = []
    title = (draft or {}).get("title") or meta.get("label") or "문서 초안"
    body.append(f"<h1>{esc(title)}</h1>")
    note = ((draft or {}).get("official_note") or NOT_OFFICIAL_FALLBACK).strip()
    body.append(f'<p class="muted">AI 에이전트가 정해진 규칙으로 계산해 만든 초안입니다. {esc(note)}</p>')
    if active.get("synthetic") and (center or tpl in ("data_brief", "profile")):
        body.append(f'<div class="banner">{esc(SYNTHETIC_BANNER)}</div>')
    blocks = []
    all_plain = []
    if draft:
        if draft.get("basis_line"):
            body.append(f'<p class="muted">{esc(draft["basis_line"])}</p>')
        for b in draft.get("blocks") or []:
            is_center = center and (tpl == "data_brief" or b.get("id") == "local")
            blocks.append(f"<h2>{esc(b.get('title'))}</h2>")
            copy_at = len(blocks)
            plain = [b.get("title") or ""]
            txt = b.get("text") or ""
            if is_center and masked and txt:
                txt = _neutral_line(res.get("intent"))
            elif is_center and _small_in_text(txt):
                cells.excluded += 1
                txt = EXCLUDED
            if txt:
                blocks.append(f"<p>{esc(txt)}</p>")
                plain.append(txt)
            tbl = b.get("table")
            if isinstance(tbl, dict):
                if is_center:
                    th, tsv = _checked_table(tbl, cells)
                else:
                    th, tsv = _table(tbl.get("columns") or [], tbl.get("rows") or [], tbl.get("title"))
                blocks.append(th)
                plain.append(tsv)
            block_text = "\n".join(x for x in plain if x)
            all_plain.append(block_text)
            blocks.insert(copy_at, f'<button type="button" class="copy noprint" data-copy="{esc(block_text)}">복사</button>')
            if not center:
                blocks.append(_chart_for(tpl, b.get("id"), data))
        for cf in draft.get("cannot_fill") or []:
            blocks.append(f"<p><b>{esc(cf.get('item'))}</b>: {esc(cf.get('text'))}. {esc(cf.get('request') or '')}</p>")
    else:
        for m in meta.get("modelled_on") or []:
            body.append(f'<p class="muted">본뜬 양식과 출처: {esc(m.get("form"))} · {esc(m.get("url") or "")}</p>')
        if tpl == "consumption_trend":
            blocks = _doc_trend(data, cells, chart=not center)
        elif tpl == "bizplan_market":
            blocks = _doc_bizplan(data, cells, chart=not center, active=active, meta=meta)
        elif tpl == "data_brief":
            blocks = _doc_brief(res, data, cells)
        else:
            for t, thtml, _ in tables_for(res, cells):
                blocks.append(f"<h2>{esc(t)}</h2>{thtml}")
    if center:
        body.append(reviewer_summary(res, active, cells, branding, version, "구분별 합계로 집계"))
    ev = res.get("evidence") or {}
    srcs = list((draft or {}).get("sources") or [])
    if not srcs and ev.get("citation"):
        srcs = [ev["citation"]]
    if all_plain:
        whole = "\n\n".join([title] + all_plain + srcs)
        body.append(f'<p class="noprint"><button type="button" class="copy" data-copy="{esc(whole)}">전체 복사</button> '
                    f'{esc(COPY_HINT)}</p>')
    body += blocks
    body.append("<h2>출처</h2><ul>" + "".join(f"<li>{esc(s)}</li>" for s in srcs) + "</ul>")
    lim = list((draft or {}).get("limits") or []) + list((draft or {}).get("footnotes") or meta.get("footnotes") or [])
    seen = _dedupe_limits(lim)
    for n in res.get("notices") or []:
        t = (n or {}).get("text")
        if (n or {}).get("code") == "no_export_check" and t and t not in seen:
            seen.insert(0, t)
    if center:
        seen.append("반출은 센터 시스템에서 신청한 뒤 센터가 심사해 정합니다.")
    body.append("<h2>한계와 각주</h2><ul>" + "".join(f"<li>{esc(x)}</li>" for x in seen) + "</ul>")
    if res.get("eda") and not center:
        body.append(render_eda(res["eda"]))
    return _page(title, "".join(body), branding)


def _dedupe_limits(lines) -> list:
    """Limits and footnotes printed once: exact repeats dropped, only the first card-only limit kept,
    and source lines left to the 출처 section."""
    out, card_only = [], False
    for x in lines:
        s = (x or "").strip() if isinstance(x, str) else ""
        if not s or s in out or s.startswith("출처"):
            continue
        if "결제분만" in s:
            if card_only:
                continue
            card_only = True
        out.append(s)
    return out


def _chart_for(tpl, block_id, data) -> str:
    if tpl == "bizplan_market" and block_id == "size":
        return _svg_bars([(month_label(s.get("month")), s.get("amount")) for s in data.get("series") or []], "월별 카드 이용금액(백만원)")
    if tpl == "consumption_trend" and block_id == "headline":
        am = ((data.get("headline") or {}).get("amount") or {})
        return _svg_bars([("금월", am.get("current")), ("전월", am.get("previous")), ("전년 동월", am.get("year_ago"))], "카드 이용금액(백만원)")
    return ""


def _doc_trend(d, cells, chart=True):
    out = []
    hl = d.get("headline") or {}
    am = hl.get("amount") or {}
    us = hl.get("uses") or {}
    pu = hl.get("per_use") or {}
    out.append("<h2>표지 정보</h2>")
    out.append(_table(["항목", "내용"], [["분석 주체", "(직접 적어 주세요)"], ["분석 목적", "(직접 적어 주세요)"],
                                       ["분석 활용 데이터", "업종별 성별 카드 이용 정보(제주데이터허브)"],
                                       ["분석 범위", f"{month_label(d.get('month'))}, {glabel(d.get('group'))}"],
                                       ["분석 방법", "금월·전월·전년 동월 카드 이용금액 합계와 업종별 증감률 비교"],
                                       ["데이터기준일", month_label(d.get("month"))]])[0])
    out.append("<h2>전체 카드 이용금액 비교(금월·전월·전년 동기)</h2>")
    rows = [[f"금월({month_label(d.get('month'))})", cells.int_cell(am.get("current"), "합계", "원"), cells.int_cell(us.get("current"), "합계", "건"), cells.int_cell(pu.get("current"), "합계", "원")],
            [f"전월({month_label(d.get('prev_month'))})", cells.int_cell(am.get("previous"), "합계", "원"), cells.int_cell(us.get("previous"), "합계", "건"), cells.int_cell(pu.get("previous"), "합계", "원")],
            [f"전년 동월({month_label(d.get('yoy_month'))})", cells.int_cell(am.get("year_ago"), "합계", "원"), cells.int_cell(us.get("year_ago"), "합계", "건"), cells.int_cell(pu.get("year_ago"), "합계", "원")]]
    out.append(_table(["구분", "이용금액", "이용건수", "건당 금액"], rows)[0])
    out.append(_table(["비교", "증감률"], [["전월 대비", cells.pct_cell(hl.get("pct_mom"), "증감률")],
                                         ["전년 동월 대비", cells.pct_cell(hl.get("pct_yoy"), "증감률")]])[0])
    if chart:
        out.append(_svg_bars([("금월", am.get("current")), ("전월", am.get("previous")), ("전년 동월", am.get("year_ago"))], "카드 이용금액(백만원)"))
    for key, ttl in (("biz_mom", "전월 대비 주요 업종별 증감"), ("biz_yoy", "전년 동기 대비 주요 업종별 증감")):
        b = d.get(key) or {}
        out.append(f"<h2>{esc(ttl)}</h2>")
        out.append(f"<p>{esc(b.get('n_biz'))}개 업종 중 증가 {esc(b.get('increase_count'))}개, 감소 {esc(b.get('decrease_count'))}개</p>")
        for sub, lab in (("top_up", "증가 상위"), ("top_down", "감소 상위")):
            rows = [[x.get("biz"), cells.pct_cell(x.get("pct"), "증감률"), cells.int_cell(x.get("current"), "합계", "원"),
                     cells.int_cell(x.get("previous"), "합계", "원")] for x in b.get(sub) or []]
            out.append(_table(["업종", "증감률", "비교 달", "기준 달"], rows, lab)[0])
    return out


def _doc_bizplan(d, cells, chart, active, meta):
    out = []
    size = d.get("size") or {}
    win = d.get("window") or {}
    out.append("<h2>시장 규모와 추이</h2>")
    out.append(_table(["항목", "값"], [["기간", f"{month_label(win.get('start'))}–{month_label(win.get('end'))}"],
                                     ["12개월 이용금액", cells.int_cell(size.get("amount_12m"), "합계", "원")],
                                     ["월평균", cells.int_cell(size.get("monthly_avg"), "합계", "원")],
                                     ["앞선 12개월", cells.int_cell(size.get("prev_amount_12m"), "합계", "원")],
                                     ["12개월 증감률", cells.pct_cell(size.get("pct_12m"), "증감률")]])[0])
    series = d.get("series") or []
    out.append(_table(["달", "이용금액"], [[month_label(s.get("month")), cells.int_cell(s.get("amount"), "합계", "원")] for s in series],
                      "최근 12개월 월별 카드 이용금액")[0])
    if chart and series:
        out.append(_svg_bars([(month_label(s.get("month")), s.get("amount")) for s in series], "월별 카드 이용금액(백만원)"))
    y = d.get("yoy") or {}
    out.append("<h2>전년 동월 대비</h2>")
    out.append(_table(["구분", "값"], [["이번 달", cells.int_cell(y.get("current"), "합계", "원")], ["전년 동월", cells.int_cell(y.get("previous"), "합계", "원")],
                                     ["증감률", cells.pct_cell(y.get("pct"), "증감률")]])[0])
    out.append("<h2>고객 구성(도민·내국인 관광객·외국인·법인)</h2>")
    out.append(_table(["구분", "12개월 이용금액", "비중"], [[glabel(m.get("group")), cells.int_cell(m.get("amount"), "합계", "원"),
                                                       cells.pct_cell(m.get("share_pct"))] for m in d.get("mix") or []])[0])
    sa = d.get("sex_age")
    out.append("<h2>성별·연령 구성</h2>")
    if sa:
        out.append(f"<p class=\"muted\">{esc(', '.join(sa.get('quarters') or []))}</p>")
        out.append(_table(["연령", "이용금액(백만원)", "비중"], [[a.get("age"), num(a.get("amount_million")), cells.pct_cell(a.get("share_pct"))] for a in sa.get("by_age") or []])[0])
        out.append(_table(["성별", "이용금액(백만원)", "비중"], [[a.get("sex"), num(a.get("amount_million")), cells.pct_cell(a.get("share_pct"))] for a in sa.get("by_sex") or []])[0])
    else:
        out.append("<p>이 업종은 성별·연령 자료에 없습니다.</p>")
    se = d.get("season") or {}
    out.append("<h2>계절성</h2>")
    out.append(_table(["구분", "달", "이용금액"], [["가장 많은 달", month_label((se.get("max") or {}).get("month")), cells.int_cell((se.get("max") or {}).get("amount"), "합계", "원")],
                                              ["가장 적은 달", month_label((se.get("min") or {}).get("month")), cells.int_cell((se.get("min") or {}).get("amount"), "합계", "원")]])[0])
    ctx = d.get("context") or {}
    out.append("<h2>요일·시간대 참고(제주 전체, 업종 구분 없음)</h2>")
    wk = ctx.get("weekday") or {}
    out.append(_table(["요일", "이용건수", "비중"], [[s.get("day"), cells.int_cell(s.get("uses"), "합계", "건"), cells.pct_cell(s.get("share_pct"))] for s in wk.get("shares") or []],
                      f"요일별 이용건수({month_label(wk.get('month'))})")[0])
    tm = ctx.get("time") or {}
    out.append(_table(["시간대", "이용금액(백만원)", "비중"], [[s.get("time") or s.get("time_type"), num(s.get("amount_million")), cells.pct_cell(s.get("share_pct"))] for s in tm.get("shares") or []],
                      f"시간대별 이용금액({month_label(tm.get('month'))})")[0])
    loc = d.get("local")
    out.append("<h2>지역 상세(센터 자료를 넣었을 때)</h2>")
    if not loc:
        out.append("<p>지역을 적지 않아 이 칸은 비워 둡니다.</p>")
    else:
        if loc.get("summary"):
            out.append(_summary_table(loc["summary"], cells, show_rows=False)[1])
        for n in loc.get("need") or []:
            out.append(f"<p>더 받을 자료: {esc(n.get('dataset'))} {esc(month_label(n.get('month')))} ({esc(n.get('why'))})</p>")
    for m in meta.get("modelled_on") or []:
        for c in m.get("form_cells") or []:
            for cf in c.get("cannot_fill") or []:
                need = f" 필요한 자료: {cf.get('need')}" if cf.get("need") else ""
                out.append(f"<p><b>{esc(cf.get('item'))}</b>: 이 자료로는 쓸 수 없습니다. {esc(cf.get('why'))}.{esc(need)}</p>")
    return out


def _doc_brief(res, d, cells):
    out = []
    if isinstance(d.get("summary"), dict):
        t = _summary_table(d["summary"], cells, show_rows=not cells.strict)
        out.append(f"<h2>고객 구성 표</h2>{t[1]}")
    y = d.get("yoy")
    out.append("<h2>전년 동월 대비</h2>")
    if isinstance(y, dict):
        masked = (y.get("export") or {}).get("masked")
        out.append(_table(["구분", "값"], [[month_label(y.get("month")), cells.int_cell(y.get("current"), "합계", "원") or (MASKED if masked else "")],
                                         [month_label(y.get("prev_month")), cells.int_cell(y.get("previous"), "합계", "원") or (MASKED if masked else "")],
                                         ["증감률", cells.pct_cell(y.get("pct"), "증감률") or "-"]])[0])
    else:
        out.append("<p>전년 같은 달 자료가 없어 비교하지 않았습니다.</p>")
    for n in d.get("need") or []:
        out.append(f"<p>더 받을 자료: {esc(n.get('dataset') or '')} {esc(month_label(n.get('month')))} ({esc(n.get('why'))})</p>")
    return out
