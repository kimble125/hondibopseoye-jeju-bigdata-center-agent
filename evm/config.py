"""Paths and the KEY=VALUE settings file parser (no third-party library)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INPUTS = ROOT / "inputs"
SAMPLES = ROOT / "samples"
CODES_PATH = INPUTS / "card_v02_codes.json"
HUB_PATH = INPUTS / "hub_card_by_biz_sex.csv"
LIBRARY_PATHS = {
    "hub_biz_sex": INPUTS / "hub_card_by_biz_sex.csv",
    "hub_sexage": INPUTS / "hub_card_by_biz_sex_age_quarter.csv",
    "hub_weekday": INPUTS / "hub_card_by_weekday.csv",
    "hub_time": INPUTS / "hub_card_by_time.csv",
}
DOC_TEMPLATES_PATH = INPUTS / "doc_templates.json"
REPORT_CATALOG_PATH = INPUTS / "report_catalog.json"
BRANDING_PATH = INPUTS / "branding.json"
SETTINGS_PATH = ROOT / ".env"

DEFAULTS = {
    "KEEP_RESULTS": "0",
}


def parse_settings(text: str) -> dict:
    """Parse KEY=VALUE lines. Blank lines and lines starting with '#' are ignored.
    Surrounding quotes of a value are removed. Later keys win."""
    out: dict = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if key:
            out[key] = value
    return out


def load_settings(path=None) -> dict:
    """Return defaults overlaid with the settings file (if present). Never prints values."""
    settings = dict(DEFAULTS)
    p = Path(path) if path is not None else SETTINGS_PATH
    try:
        if p.is_file():
            settings.update(parse_settings(p.read_text(encoding="utf-8-sig")))
    except (OSError, UnicodeDecodeError):
        pass
    return settings
