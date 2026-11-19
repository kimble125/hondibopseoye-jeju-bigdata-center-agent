"""Identity card, policies P1-P5, persona strings and branding (section 3.6, 11.3)."""
from __future__ import annotations

import json
from pathlib import Path

from .config import BRANDING_PATH

BRANDING_DEFAULTS = {
    "product_name": "근거 한 장 메이트",
    "mate_name": "근거 메이트",
    "tagline": "받을 자료 고르기부터 반출 신청 준비까지, 한 번의 방문으로",
    "team_name": "",
    "contest_line": "「제주 AI·빅데이터 활용 AI Agent 개발 챌린지」 제출작",
}

POLICIES = [
    {"id": "P1", "text": "근거 없이 숫자를 말하지 않습니다", "hook": "narrate.number_guard"},
    {"id": "P2", "text": "먼저 자료를 확인하고 말합니다", "hook": "agent.check_file"},
    {"id": "P3", "text": "이 자료로 알 수 없는 것은 모른다고 합니다", "hook": "agent: cannot, need_file"},
    {"id": "P4", "text": "틀린 문장은 바로잡습니다", "hook": "narrate.claim_message: revise starts with '아니요,'"},
    {"id": "P5", "text": "가려야 할 숫자는 가립니다", "hook": "calc R8 export pre-check"},
]


def load_branding(path=None) -> dict:
    """Read branding once; a missing file, invalid JSON or a missing/empty-typed key falls back to defaults."""
    out = dict(BRANDING_DEFAULTS)
    p = Path(path) if path is not None else BRANDING_PATH
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return out
    if isinstance(data, dict):
        for k in BRANDING_DEFAULTS:
            v = data.get(k)
            if isinstance(v, str):
                out[k] = v
    return out


BRANDING = load_branding()

PERSONA = {
    "name": BRANDING["mate_name"],
    "greeting": "안녕하세요, " + BRANDING["mate_name"] + "입니다. 문서에 쓰려는 문장을 적어 주시면 넣은 자료로 확인해 드립니다.",
    "tone": "존댓말, 짧고 분명하게",
    "ai_notice": "이 설명은 AI 에이전트가 정해진 규칙으로 만든 것입니다.",
}


def policies() -> list:
    return [{"id": p["id"], "text": p["text"]} for p in POLICIES]


def identity_card() -> dict:
    return {"branding": dict(BRANDING), "persona": dict(PERSONA), "policies": policies()}
