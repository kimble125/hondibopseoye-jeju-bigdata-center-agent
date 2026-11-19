"""Dataset kinds, canonical columns, user groups, vocabulary and aliases (section 3.1, 3.3, 3.5)."""
from __future__ import annotations

import json
from pathlib import Path

from .config import CODES_PATH, REPORT_CATALOG_PATH, DOC_TEMPLATES_PATH

CENTER_LABEL = "제주빅데이터센터"
HUB_SOURCE = "제주데이터허브(공개)"

# kind -> spec. "required" lists the exact source header names.
KINDS = {
    "c108": {
        "required": ["base_year_month", "dstrct_se", "city", "area_type", "bjd", "biz_cd", "biz_nm", "user_type",
                     "tour_type", "age", "sex", "user_cnt", "use_cnt", "use_amt"],
        "label": "카드 이용 현황(읍면동)_v02", "source": CENTER_LABEL, "export_check": True, "center": True,
    },
    "c112": {
        "required": ["base_year_month", "dstrct_se", "bjd", "biz_cd", "biz_nm", "user_type", "tour_type", "week",
                     "age", "sex", "user_cnt", "use_cnt", "use_amt"],
        "label": "카드 이용 현황(요일별)_v02", "source": CENTER_LABEL, "export_check": True, "center": True,
    },
    "c114": {
        "required": ["base_year_month", "dstrct_se", "bjd", "biz_cd", "biz_nm", "user_type", "tour_type", "time",
                     "age", "sex", "user_cnt", "use_cnt", "use_amt"],
        "label": "카드 이용 현황(시간대)_v02", "source": CENTER_LABEL, "export_check": True, "center": True,
    },
    "hub_biz_sex": {
        "required": ["base_year_month", "biz_nm", "user_type", "sex", "user_count", "use_count", "use_amount"],
        "label": "업종별 성별 카드 이용 정보", "source": HUB_SOURCE, "export_check": False, "center": False,
    },
}
KIND_ORDER = ["c108", "c112", "c114", "hub_biz_sex"]
CARD_KINDS = set(KIND_ORDER)
REGION_DATASET = KINDS["c108"]["label"]

# Library tables (section 10.1); integer columns per table.
LIBRARY_KINDS = {
    "hub_biz_sex": {"label": "업종별 성별 카드 이용 정보", "int_cols": []},
    "hub_sexage": {"label": "성별 카드 이용금액 비율", "int_cols": ["use_amout_by_million"],
                   "required": ["base_year", "base_quarter", "biz_name", "sex", "age_range", "use_amout_by_million"]},
    "hub_weekday": {"label": "요일별 카드 이용 건수 비교", "int_cols": ["use_count"],
                    "required": ["base_year_month", "day_of_week", "age_range", "sex", "use_count"]},
    "hub_time": {"label": "시간대별 카드 이용금액 현황", "int_cols": ["use_amout_by_million"],
                 "required": ["base_year_month", "time_type", "user_type", "age_range", "use_amout_by_million"]},
}

CANON = {"base_year_month": "month", "biz_nm": "biz", "user_count": "users", "user_cnt": "users",
         "use_count": "uses", "use_cnt": "uses", "use_amount": "amount", "use_amt": "amount"}
MEASURES = ("users", "uses", "amount")

GROUPS = {"resident": ["제주도민"], "domestic": ["내국인"], "foreign": ["중국", "일본", "동남아", "기타외국"], "corporate": ["법인"]}
GROUPS["visitors"] = GROUPS["domestic"] + GROUPS["foreign"]
GROUPS["all"] = GROUPS["resident"] + GROUPS["domestic"] + GROUPS["foreign"] + GROUPS["corporate"]
GROUP_SETS = {k: frozenset(v) for k, v in GROUPS.items()}
ORDER = ["resident", "domestic", "foreign", "corporate"]
GROUP_LABELS = {"resident": "도민", "domestic": "내국인 관광객", "foreign": "외국인", "corporate": "법인",
                "visitors": "관광객 전체", "all": "전체"}
MEASURE_LABELS = {"amount": "카드 이용금액", "uses": "카드 이용건수", "users": "카드 이용자 수"}
MEASURE_UNITS = {"amount": "원", "uses": "건", "users": "명"}

# Understanding vocabulary (section 3.5).
LIMIT_WORDS = [
    ("forecast", ["내년", "다음 달", "다음달", "앞으로", "전망", "예측", "늘까", "줄까", "될까"]),
    ("cause", ["왜", "이유", "원인", "때문"]),
    ("store_count", ["몇 곳", "몇 개", "몇 군데", "점포 수", "가게 수", "매장 수"]),
    ("total_market", ["전체 매출", "총매출", "총 매출", "시장 규모", "모든 가게"]),
]
BIZ_ALIASES = {
    "한식당": "한식 음식점업", "한식집": "한식 음식점업",
    "중식당": "중식 음식점업", "중국집": "중식 음식점업",
    "일식집": "일식 음식점업", "일식당": "일식 음식점업",
    "레스토랑": "서양식 음식점업", "양식당": "서양식 음식점업",
    "카페": "비알콜 음료점업", "커피숍": "비알콜 음료점업",
    "편의점": "체인화 편의점",
    "렌터카": "자동차 임대업", "렌트카": "자동차 임대업",
    "골프장": "골프장 운영업", "호텔": "호텔업", "주유소": "차량용 주유소 운영업", "슈퍼": "슈퍼마켓",
    "빵집": "빵 및 과자류 소매업", "베이커리": "빵 및 과자류 소매업", "택시": "택시 운송업",
}
AMBIGUOUS_BIZ = ["식당", "음식점", "외식"]
FOOD_CHOICES = ["한식 음식점업", "중식 음식점업", "일식 음식점업", "서양식 음식점업", "기타 외국식 음식점업",
                "피자 햄버거 샌드위치 및 유사 음식점업"]
GROUP_TERMS = [("내국인 관광객", "domestic"), ("외국인 관광객", "foreign"), ("관광객 전체", "visitors"),
               ("전체 관광객", "visitors"), ("제주도민", "resident"), ("외국인", "foreign"), ("도민", "resident"),
               ("법인", "corporate")]
AMBIGUOUS_GROUP = "관광객"
GROUP_CHOICES = ["내국인 관광객", "외국인", "관광객 전체"]
MEASURE_TERMS = [("이용자 수", "users"), ("이용자수", "users"), ("몇 명", "users"), ("건수", "uses"), ("횟수", "uses")]
YOY_WORDS = ["작년", "전년", "지난해"]
INCREASE_WORDS = ["늘", "증가", "올랐", "상승"]
DECREASE_WORDS = ["줄", "감소", "내렸", "하락"]
RANK_WORDS = ["가장", "제일", "최고"]
LESS_STEMS = ["적", "작", "낮"]
DOC_WORDS = [("bizplan_market", ["사업계획서", "시장 현황", "시장현황", "시장 분석"]),
             ("consumption_trend", ["현황자료", "소비동향", "동향 자료", "동향 보고"])]
RECOMMEND_WORDS = ["어떤 데이터", "무슨 데이터", "어떤 자료", "무슨 자료", "받아야"]
BRIEF_WORDS = ["자료 요약", "요약 자료", "요약해"]
PARTICLES = ["에서", "으로", "에는", "까지", "부터", "보다", "에게", "이랑", "이", "가", "은", "는", "을", "를", "의", "에",
             "도", "만", "과", "와", "로", "랑", "요"]


def _read_json(path: Path) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}


_CACHE: dict = {}


def codes(path=None) -> dict:
    key = ("codes", str(path or CODES_PATH))
    if key not in _CACHE:
        _CACHE[key] = _read_json(Path(path or CODES_PATH))
    return _CACHE[key]


def report_catalog(path=None) -> dict:
    key = ("report", str(path or REPORT_CATALOG_PATH))
    if key not in _CACHE:
        _CACHE[key] = _read_json(Path(path or REPORT_CATALOG_PATH))
    return _CACHE[key]


def doc_templates(path=None) -> dict:
    key = ("docs", str(path or DOC_TEMPLATES_PATH))
    if key not in _CACHE:
        _CACHE[key] = _read_json(Path(path or DOC_TEMPLATES_PATH))
    return _CACHE[key]


def code_biz_names(path=None) -> list:
    return [b.get("name", "") for b in codes(path).get("biz", []) if b.get("name")]


def place_names(path=None) -> dict:
    """Deduplicated region names: legal-dong (bjd) and district (dstrct_se)."""
    c = codes(path)
    return {"bjd": list(dict.fromkeys(c.get("bjd", []))), "dstrct_se": list(dict.fromkeys(c.get("dstrct_se", [])))}


def norm_name(s: str) -> str:
    """Lookup key that ignores punctuation and spaces (B1)."""
    return "".join(ch for ch in s if ch.isalnum() or ch == "?")


def detect_kind(header: list) -> tuple:
    """Return (kind, missing). kind is None when no known kind matches; missing lists the
    columns missing for the closest known kind."""
    hs = set(header)
    best_missing = None
    for kind in KIND_ORDER:
        req = KINDS[kind]["required"]
        missing = [c for c in req if c not in hs]
        if not missing:
            return kind, []
        if best_missing is None or len(missing) < len(best_missing):
            best_missing = missing
    return None, best_missing or []
