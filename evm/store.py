"""In-memory store of loaded tables (section 3.1, 3.2, 9 A3/A8, 10.1, 10.8-4).
User files are parsed in memory only; nothing is written to disk."""
from __future__ import annotations

import csv
import hashlib
import io
from pathlib import Path

from . import catalog
from .config import LIBRARY_PATHS

SUPPORTED_TABLES = [catalog.KINDS[k]["label"] for k in catalog.KIND_ORDER]


class UnknownHeaderError(ValueError):
    """Raised when a file has no usable header (no header row or fewer than two columns)."""

    def __init__(self, message: str, kind=None, missing=None):
        super().__init__(message)
        self.kind = kind
        self.missing = list(missing or [])


class DuplicateFileError(ValueError):
    """Raised when a file with identical bytes is already loaded (A8)."""


def _clean_header(values: list) -> list:
    out = []
    for v in values:
        v = (v or "").replace("\ufeff", "").strip().strip('"').strip()
        out.append(v)
    return out


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp949", errors="replace")


def parse_csv(text: str) -> tuple:
    """Return (header, rows) where rows are lists of stripped strings; empty lines skipped."""
    if text.startswith("\ufeff"):
        text = text[1:]
    reader = csv.reader(io.StringIO(text, newline=""))
    header = None
    rows = []
    for rec in reader:
        if header is None:
            if not rec or all(not (x or "").strip() for x in rec):
                continue
            header = _clean_header(rec)
            continue
        if not rec:
            continue
        rows.append([(x or "").strip() for x in rec])
    return header or [], rows


def _to_int(v):
    v = (v or "").strip().replace(",", "")
    if v.upper() in ("", "NA", "NULL", "NAN"):
        return None
    try:
        return int(v)
    except ValueError:
        try:
            f = float(v)
        except ValueError:
            return None
        return int(f) if f.is_integer() else None


def card_rows(header: list, raw_rows: list) -> tuple:
    """Canonical card rows and the number of skipped rows."""
    names = [catalog.CANON.get(h, h) for h in header]
    rows, skipped = [], 0
    for rec in raw_rows:
        row = {}
        for i, name in enumerate(names):
            if name and name not in row:
                row[name] = rec[i] if i < len(rec) else ""
        ok = True
        for m in catalog.MEASURES:
            val = _to_int(row.get(m))
            if val is None:
                ok = False
                break
            row[m] = val
        if not ok:
            skipped += 1
            continue
        rows.append(row)
    return rows, skipped


def library_rows(header: list, raw_rows: list, int_cols: list) -> list:
    out = []
    for rec in raw_rows:
        row = {h: (rec[i] if i < len(rec) else "") for i, h in enumerate(header)}
        ok = True
        for c in int_cols:
            val = _to_int(row.get(c))
            if val is None:
                ok = False
                break
            row[c] = val
        if ok:
            out.append(row)
    return out


class Store:
    def __init__(self, codes_path=None):
        self.codes_path = codes_path
        self._tables: list = []      # files of the active kind: dicts with name, kind, rows, hash, months
        self._kind = None
        self._generic = None         # {"name", "header", "rows"} when a generic table is active
        self._library: dict = {}
        self.last_notice = None

    # ---- loading -------------------------------------------------------------------------------
    def load_path(self, path) -> dict:
        p = Path(path)
        data = p.read_bytes()
        return self.load_text(p.name, _decode(data))

    def load_text(self, name: str, text: str) -> dict:
        if not isinstance(text, str):
            raise UnknownHeaderError("이 파일은 아직 읽을 수 없습니다. 글자로 된 CSV 파일을 넣어 주세요.")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        header, raw = parse_csv(text)
        if len(header) < 2:
            raise UnknownHeaderError(
                "이 파일은 아직 읽을 수 없습니다. 첫 줄에 열 이름이 두 개 이상 있는 CSV 파일이어야 합니다. 읽을 수 있는 표: "
                + ", ".join(SUPPORTED_TABLES), kind=None, missing=[])
        if any(t["hash"] == digest for t in self._tables) or (self._generic and self._generic["hash"] == digest):
            raise DuplicateFileError("같은 파일이 이미 들어 있습니다. 같은 내용은 두 번 더하지 않습니다.")
        kind, _missing = catalog.detect_kind(header)
        synthetic = Path(name).name.startswith("SYNTHETIC_")
        self.last_notice = None
        if kind is None:
            if self._kind is not None or self._generic is not None:
                self.last_notice = "다른 종류의 파일이라 지금 쓰던 표를 이 파일로 바꿨습니다."
            self._tables = []
            self._kind = "generic"
            self._generic = {"name": name, "header": header, "rows": raw, "hash": digest, "synthetic": synthetic}
            return {"kind": "generic", "label": "그 밖의 CSV 표", "rows": len(raw), "skipped_rows": 0, "months": [],
                    "synthetic": synthetic, "notice": self.last_notice}
        rows, skipped = card_rows(header, raw)
        months = sorted({r.get("month", "") for r in rows if r.get("month")})
        entry = {"name": name, "kind": kind, "rows": rows, "hash": digest, "months": months, "header": header,
                 "skipped": skipped, "synthetic": synthetic}
        if self._kind != kind:
            if self._kind is not None:
                self.last_notice = "다른 종류의 파일이라 지금 쓰던 표를 이 파일로 바꿨습니다."
            self._tables = []
            self._generic = None
            self._kind = kind
        self._tables.append(entry)
        return {"kind": kind, "label": catalog.KINDS[kind]["label"], "rows": len(rows), "skipped_rows": skipped,
                "months": months, "synthetic": synthetic, "notice": self.last_notice}

    def load_library(self, paths=None) -> None:
        """Load the four bundled public tables as the library (independent of the active table)."""
        paths = paths or LIBRARY_PATHS
        for kind, p in paths.items():
            p = Path(p)
            if not p.is_file():
                continue
            header, raw = parse_csv(_decode(p.read_bytes()))
            if kind == "hub_biz_sex":
                rows, skipped = card_rows(header, raw)
            else:
                rows, skipped = library_rows(header, raw, catalog.LIBRARY_KINDS[kind]["int_cols"]), 0
            self._library[kind] = {"name": p.name, "rows": rows, "months": sorted({r.get("month", r.get("base_year_month", "")) for r in rows}) if kind != "hub_sexage" else []}

    def library(self, kind: str) -> list:
        entry = self._library.get(kind)
        return entry["rows"] if entry else []

    def library_info(self, kind: str):
        return self._library.get(kind)

    def has_library(self, kind: str) -> bool:
        return kind in self._library

    # ---- state ---------------------------------------------------------------------------------
    def active(self):
        if self._kind == "generic" and self._generic:
            g = self._generic
            return {"kind": "generic", "label": "그 밖의 CSV 표", "source": "사용자가 넣은 파일", "files": [g["name"]],
                    "months": [], "has": {"bjd": False, "dstrct_se": False}, "synthetic": g["synthetic"],
                    "export_check": False, "rows": len(g["rows"]), "skipped_rows": 0}
        if not self._tables:
            return None
        spec = catalog.KINDS[self._kind]
        months = sorted({m for t in self._tables for m in t["months"]})
        header = set(self._tables[0]["header"])
        return {"kind": self._kind, "label": spec["label"], "source": spec["source"],
                "files": [t["name"] for t in self._tables], "months": months,
                "has": {"bjd": "bjd" in header, "dstrct_se": "dstrct_se" in header},
                "synthetic": any(t["synthetic"] for t in self._tables), "export_check": spec["export_check"],
                "rows": sum(len(t["rows"]) for t in self._tables), "skipped_rows": sum(t["skipped"] for t in self._tables)}

    def rows(self) -> list:
        out = []
        for t in self._tables:
            out.extend(t["rows"])
        return out

    def generic(self):
        return self._generic if self._kind == "generic" else None

    def card_view(self):
        """(active-like dict, rows) for card answers: the active card table, else the library public table."""
        act = self.active()
        if act and act["kind"] in catalog.CARD_KINDS:
            return act, self.rows()
        if act is None and "hub_biz_sex" in self._library:
            lib = self._library["hub_biz_sex"]
            spec = catalog.KINDS["hub_biz_sex"]
            return ({"kind": "hub_biz_sex", "label": spec["label"], "source": spec["source"], "files": [lib["name"]],
                     "months": lib["months"], "has": {"bjd": False, "dstrct_se": False}, "synthetic": False,
                     "export_check": False, "rows": len(lib["rows"]), "skipped_rows": 0}, lib["rows"])
        return act, []

    def clear_user_files(self) -> None:
        self._tables = []
        self._kind = None
        self._generic = None
        self.last_notice = None
