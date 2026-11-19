"""Rule-based sentence understanding (section 3.5, 9 B1/B2, 10.2, 10.8).
Returns meaning slots before any row is read. It never consults the rows themselves."""
from __future__ import annotations

import re

from . import catalog as cat

_MONTH_KR = re.compile(r"(\d{4})\s*년\s*(\d{1,2})\s*월")
_MONTH_NUM = re.compile(r"(?<!\d)(\d{4})(0[1-9]|1[0-2])(?!\d)")
_RANK = re.compile(r"(?<!\d)(\d{1,3})\s*위")


def _is_hangul(ch: str) -> bool:
    return "\uac00" <= ch <= "\ud7a3"


class _Text:
    def __init__(self, text: str):
        self.text = text
        self.used = [False] * len(text)

    def free(self, start: int, end: int) -> bool:
        return not any(self.used[start:end])

    def consume(self, start: int, end: int) -> None:
        for i in range(start, end):
            self.used[i] = True

    def find(self, terms, boundary=None, consume=True):
        """Longest-first search. terms: iterable of (term, value). Returns [(start, end, term, value)]
        sorted by position."""
        hits = []
        for term, value in sorted(terms, key=lambda tv: -len(tv[0])):
            if not term:
                continue
            start = 0
            while True:
                i = self.text.find(term, start)
                if i < 0:
                    break
                j = i + len(term)
                if self.free(i, j) and (boundary is None or boundary(self.text, i, j)):
                    hits.append((i, j, term, value))
                    if consume:
                        self.consume(i, j)
                start = i + 1
        hits.sort(key=lambda h: h[0])
        return hits


def _particles_only(rest: str) -> bool:
    if not rest:
        return True
    for p in cat.PARTICLES:
        if rest.startswith(p) and _particles_only(rest[len(p):]):
            return True
    return False


def place_boundary(text: str, i: int, j: int) -> bool:
    """A place name must be a whole word: no Hangul right before it, and only particles after it (B2)."""
    if i > 0 and _is_hangul(text[i - 1]):
        return False
    k = j
    while k < len(text) and _is_hangul(text[k]):
        k += 1
    return _particles_only(text[j:k])


def build_vocab(active: dict | None, table_biz=None, table_places=None) -> dict:
    """Vocabulary: business names in the table plus the code list; places from the code list (and table)."""
    table_biz = list(table_biz or [])
    names = list(dict.fromkeys(table_biz + cat.code_biz_names()))
    preferred: dict = {}
    for n in names:                         # the table's spelling wins over the code list's
        preferred.setdefault(cat.norm_name(n), n)
    for n in table_biz:
        preferred[cat.norm_name(n)] = n
    terms = {}
    for n in names:
        canon = preferred[cat.norm_name(n)]
        terms[n] = canon
        terms[n.replace(", ", " ").replace(",", "")] = canon
    places = cat.place_names()
    if table_places:
        for field, vals in table_places.items():
            places[field] = list(dict.fromkeys(places.get(field, []) + list(vals)))
    return {"biz_terms": terms, "biz_preferred": preferred, "places": places}


def resolve_biz(label: str, vocab: dict):
    return vocab.get("biz_preferred", {}).get(cat.norm_name(label))


def understand(sentence: str, *, active: dict | None = None, vocab: dict | None = None) -> dict:
    vocab = vocab or build_vocab(active)
    s = (sentence or "").strip()
    t = _Text(s)
    out = {"sentence": s, "limit": None, "recommend": False, "doc": None, "brief": False,
           "biz": None, "biz_ambiguous": None, "place": None, "month": None, "month_explicit": False,
           "groups": [], "group_ambiguous": None, "measure": "amount", "analysis": None, "claim": None,
           "yoy_direction": None, "compare": None, "rank_n": None}

    # 1. limits
    for code, words in cat.LIMIT_WORDS:
        if any(w in s for w in words):
            out["limit"] = code
            break
    out["recommend"] = any(w in s for w in cat.RECOMMEND_WORDS)
    for tpl, words in cat.DOC_WORDS:
        if any(w in s for w in words):
            out["doc"] = tpl
            break
    out["brief"] = any(w in s for w in cat.BRIEF_WORDS)

    # month first (so its digits are not read as a rank)
    m = _MONTH_KR.search(s)
    if m and 1 <= int(m.group(2)) <= 12:
        out["month"] = f"{m.group(1)}{int(m.group(2)):02d}"
        out["month_explicit"] = True
        t.consume(m.start(), m.end())
    else:
        m = _MONTH_NUM.search(s)
        if m:
            out["month"] = m.group(1) + m.group(2)
            out["month_explicit"] = True
            t.consume(m.start(), m.end())

    # 2. business: exact names, then aliases, then stand-alone ambiguous words
    hits = t.find(list(vocab["biz_terms"].items()))
    if hits:
        out["biz"] = hits[0][3]
    alias_hits = t.find(list(cat.BIZ_ALIASES.items()))
    if alias_hits and out["biz"] is None:
        out["biz"] = resolve_biz(alias_hits[0][3], vocab) or alias_hits[0][3]
    amb = t.find([(w, w) for w in cat.AMBIGUOUS_BIZ], consume=False)
    if amb and out["biz"] is None:
        out["biz_ambiguous"] = {"word": amb[0][2], "start": amb[0][0], "end": amb[0][1]}

    # 3. region
    place_terms = []
    for field in ("dstrct_se", "bjd"):
        for name in vocab["places"].get(field, []):
            place_terms.append((name, (field, name)))
    ph = t.find(place_terms, boundary=place_boundary)
    if ph:
        out["place"] = {"field": ph[0][3][0], "value": ph[0][3][1]}

    # 5. groups
    gh = t.find(cat.GROUP_TERMS)
    seen = []
    for i, j, term, g in gh:
        if g not in [x["group"] for x in seen]:
            seen.append({"group": g, "start": i, "end": j})
    out["groups"] = seen
    ga = t.find([(cat.AMBIGUOUS_GROUP, cat.AMBIGUOUS_GROUP)], consume=False)
    if ga:
        out["group_ambiguous"] = {"word": ga[0][2], "start": ga[0][0], "end": ga[0][1]}

    # 6. measure
    for term, meas in cat.MEASURE_TERMS:
        if term in s:
            out["measure"] = meas
            break

    # 7. analysis
    groups = [g["group"] for g in seen]
    bpos = s.find("보다")
    yoy_word = next((w for w in cat.YOY_WORDS if w in s), None)
    rank_m = None
    for mm in _RANK.finditer(s):
        if t.free(mm.start(), mm.end()):
            rank_m = mm
            break
    if len(groups) >= 2 and bpos >= 0:
        before = [g for g in seen if g["end"] <= bpos]
        b = before[-1]["group"] if before else seen[-1]["group"]
        a = next(g for g in groups if g != b)
        pred = s[bpos + 2:]
        claim = "less" if any(st in pred for st in cat.LESS_STEMS) else "greater"
        out["analysis"] = "group_compare"
        out["compare"] = {"a": a, "b": b}
        out["claim"] = {"type": claim}
    elif yoy_word:
        pred = s[s.find(yoy_word) + len(yoy_word):]
        if bpos >= 0 and bpos > s.find(yoy_word):
            pred = s[bpos + 2:] or pred
        direction = None
        if any(w in pred for w in cat.INCREASE_WORDS):
            direction = "increase"
        elif any(w in pred for w in cat.DECREASE_WORDS):
            direction = "decrease"
        out["analysis"] = "yoy"
        out["yoy_direction"] = direction
        if direction:
            out["claim"] = {"type": direction}
    elif rank_m or any(w in s for w in cat.RANK_WORDS):
        n = int(rank_m.group(1)) if rank_m else 1
        out["analysis"] = "rank"
        out["rank_n"] = n
        if out["biz"]:
            out["claim"] = {"type": "rank", "rank": n}
    else:
        out["analysis"] = "summary"
    return out


def replace_choice(sentence: str, slot: str, label: str, span=None) -> str:
    """Resend helper for ask_scope buttons (3.5-8, B1): replace the ambiguous span or insert the label."""
    if span and 0 <= span.get("start", -1) < span.get("end", -1) <= len(sentence):
        return sentence[:span["start"]] + label + sentence[span["end"]:]
    return label + " " + sentence
