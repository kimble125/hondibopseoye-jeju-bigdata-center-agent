"""Local HTTP server (section 3.8). Owned by app.

Binds 127.0.0.1 only. No directory listing, no arbitrary file access. User files and results
live in memory only (C5); "퇴실 정리" drops them. Request logging prints method, path kind and
status only.
"""
from __future__ import annotations

import json
import secrets
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from . import report

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
INPUTS = ROOT / "inputs"
SAMPLES = ROOT / "samples"
STATIC = {"index.html": "text/html; charset=utf-8", "app.js": "text/javascript; charset=utf-8",
          "style.css": "text/css; charset=utf-8"}
MAX_BODY = 60_000_000
MAX_SMALL_BODY = 100_000
PUBLIC_FILE = "hub_card_by_biz_sex.csv"
EMPTY_GUIDE = {"steps": [], "unconfirmed": []}
EMPTY_CATALOG = {"datasets": [], "categories": []}
CSP = "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'"


def _read_json(path: Path, empty: dict, required: str) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return dict(empty)
    if not isinstance(data, dict) or not isinstance(data.get(required), list):
        return dict(empty)
    return data


def load_guide(path=None) -> dict:
    return _read_json(Path(path) if path else INPUTS / "center_guide.json", EMPTY_GUIDE, "steps")


def load_catalog(path=None) -> dict:
    data = _read_json(Path(path) if path else INPUTS / "center_catalog.json", EMPTY_CATALOG, "datasets")
    if not isinstance(data.get("categories"), list):
        data["categories"] = []
    return data


def load_branding(path=None) -> dict:
    defaults = {"product_name": "근거 한 장 메이트", "mate_name": "근거 메이트",
                "tagline": "받을 자료 고르기부터 반출 신청 준비까지, 한 번의 방문으로", "team_name": "",
                "contest_line": "「제주 AI·빅데이터 활용 AI Agent 개발 챌린지」 제출작"}
    try:
        from . import identity
        if path is None:
            return dict(identity.BRANDING)
        return identity.load_branding(path)
    except Exception:
        out = dict(defaults)
        try:
            data = json.loads(Path(path or INPUTS / "branding.json").read_text(encoding="utf-8-sig"))
            for k in defaults:
                if isinstance(data.get(k), str):
                    out[k] = data[k]
        except (OSError, ValueError, AttributeError):
            pass
        return out


class AppState:
    """Everything the server keeps; in memory only."""

    def __init__(self, answer_fn=None, store=None, guide_path=None, catalog_path=None, branding_path=None,
                 mascot_path=None, samples_dir=None, settings=None):
        self.lock = threading.Lock()
        self._answer_fn = answer_fn
        self.store = store
        self.guide_path = guide_path
        self.catalog_path = catalog_path
        self.mascot_path = Path(mascot_path) if mascot_path else INPUTS / "mascot.svg"
        self.samples_dir = Path(samples_dir) if samples_dir else SAMPLES
        self.branding = load_branding(branding_path)
        self.reports: dict = {}
        self.docs: dict = {}
        self.settings = settings if settings is not None else self._settings()
        self.keep_results = str(self.settings.get("KEEP_RESULTS", "0")) == "1"
        if self.store is None:
            self.store = self._new_store()

    @staticmethod
    def _settings():
        try:
            from . import config
            return config.load_settings()
        except Exception:
            return {"KEEP_RESULTS": "0"}

    def _new_store(self):
        try:
            from .store import Store
        except Exception:
            return None
        s = Store()
        self._load_bundled(s)
        return s

    @staticmethod
    def _load_bundled(s):
        if hasattr(s, "load_library"):
            s.load_library()
        else:
            s.load_path(INPUTS / PUBLIC_FILE)

    def answer(self, sentence):
        fn = self._answer_fn
        if fn is None:
            from .agent import answer as fn
        return fn(sentence, store=self.store, llm=None)

    def active(self):
        s = self.store
        if s is None:
            return None
        try:
            if hasattr(s, "card_view"):
                act = s.active()
                if act is not None and act.get("kind") == "generic":
                    return act
                return s.card_view()[0]
            return s.active()
        except Exception:
            return None

    def samples(self):
        try:
            return sorted(p.name for p in self.samples_dir.glob("*.csv") if p.is_file())
        except OSError:
            return []

    def policies(self):
        try:
            from . import identity
            return identity.policies()
        except Exception:
            return []

    def version(self):
        try:
            from . import __version__
            return __version__
        except Exception:
            return ""

    def status(self):
        return {"version": self.version(), "python": sys.version.split()[0], "llm_mode": "off",
                "active": self.active(), "policies": self.policies(), "samples": self.samples(),
                "public_file": PUBLIC_FILE, "branding": dict(self.branding),
                "mascot": self.mascot_path.is_file(), "keep_results": self.keep_results,
                "max_body": MAX_BODY}

    def clear(self):
        with self.lock:
            self.reports.clear()
            self.docs.clear()
            if self.store is not None:
                self.store.clear_user_files()


def _new_id() -> str:
    return secrets.token_hex(8)


class Handler(BaseHTTPRequestHandler):
    server_version = "EvidenceMate"
    sys_version = ""
    state: AppState = None  # set by make_server

    # -- logging: method, path kind, status only --------------------------------------------------
    def log_message(self, fmt, *args):  # noqa: D401
        pass

    def log_request(self, code="-", size="-"):
        if getattr(self.server, "quiet", False):
            return
        kind = urlparse(self.path).path.split("/")[1:2]
        try:
            sys.stdout.write(f"{self.command} /{kind[0] if kind else ''} {code}\n")
            sys.stdout.flush()
        except Exception:
            pass

    # -- helpers ---------------------------------------------------------------------------------
    def _send(self, code, body: bytes, ctype: str, extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", CSP)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _html(self, code, text):
        self._send(code, text.encode("utf-8"), "text/html; charset=utf-8")

    def _err(self, code, msg):
        self._json(code, {"error": msg})

    def _body(self, limit):
        raw_len = self.headers.get("Content-Length")
        if raw_len is None:
            self._err(413, f"요청 크기를 알 수 없습니다. 파일은 {limit // 1_000_000}MB까지 넣을 수 있습니다.")
            return None
        try:
            n = int(raw_len)
        except ValueError:
            self._err(400, "요청 형식이 올바르지 않습니다.")
            return None
        if n < 0 or n > limit:
            self._err(413, f"파일이 너무 큽니다. {limit // 1_000_000}MB까지 넣을 수 있습니다.")
            return None
        data = self.rfile.read(n)
        try:
            obj = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            self._err(400, "요청 형식이 올바르지 않습니다.")
            return None
        if not isinstance(obj, dict):
            self._err(400, "요청 형식이 올바르지 않습니다.")
            return None
        return obj

    # -- GET -------------------------------------------------------------------------------------
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        st = self.state
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            return self._static("index.html")
        if path.startswith("/static/"):
            return self._static(path[len("/static/"):])
        if path == "/api/status":
            return self._json(200, st.status())
        if path == "/api/guide":
            return self._json(200, load_guide(st.guide_path))
        if path == "/api/catalog":
            return self._json(200, load_catalog(st.catalog_path))
        if path == "/api/report_catalog":
            return self._json(200, _read_json(INPUTS / "report_catalog.json", {"datasets": []}, "datasets"))
        if path == "/api/mascot":
            p = st.mascot_path
            if p.is_file():
                return self._send(200, p.read_bytes(), "image/svg+xml")
            return self._err(404, "그림이 없습니다.")
        if path.startswith("/report/") or path.startswith("/doc/"):
            kind, _, rid = path[1:].partition("/")
            store = st.reports if kind == "report" else st.docs
            with st.lock:
                entry = store.get(rid)
            if entry is None:
                return self._html(404, report.gone_page(st.branding))
            if kind == "report":
                return self._html(200, report.render_report(entry, st.branding, st.version()))
            return self._html(200, report.render_doc(entry, st.branding, st.version()))
        if path == "/favicon.ico":
            return self._send(204, b"", "image/x-icon")
        return self._err(404, "찾는 주소가 없습니다.")

    def _static(self, name):
        if name not in STATIC:
            return self._err(404, "찾는 주소가 없습니다.")
        p = WEB / name
        try:
            data = p.read_bytes()
        except OSError:
            return self._err(404, "찾는 주소가 없습니다.")
        return self._send(200, data, STATIC[name])

    # -- POST ------------------------------------------------------------------------------------
    def do_POST(self):
        st = self.state
        path = urlparse(self.path).path
        if path == "/api/load":
            obj = self._body(MAX_BODY)
            if obj is None:
                return
            return self._load(obj.get("name"), obj.get("text"))
        obj = self._body(MAX_SMALL_BODY)
        if obj is None:
            return
        if path == "/api/load_sample":
            name = obj.get("name")
            if name == PUBLIC_FILE:
                with st.lock:
                    st.store.clear_user_files()
                return self._json(200, {"loaded": PUBLIC_FILE, "status": st.status(),
                                        "message": "공개 실측 자료(업종별 성별 카드 이용 정보)로 돌아왔습니다."})
            if not isinstance(name, str) or name not in st.samples():
                return self._err(400, "그런 예시 파일이 없습니다.")
            try:
                text = (st.samples_dir / name).read_bytes().decode("utf-8-sig")
            except (OSError, UnicodeDecodeError):
                return self._err(400, "예시 파일을 읽지 못했습니다.")
            return self._load(name, text)
        if path == "/api/ask":
            sentence = obj.get("sentence")
            if not isinstance(sentence, str) or not (1 <= len(sentence) <= 300):
                return self._err(400, "문장은 1자부터 300자까지 적을 수 있습니다.")
            return self._ask(sentence)
        if path == "/api/doc":
            return self._doc(obj)
        if path == "/api/clear":
            st.clear()
            return self._json(200, {"status": st.status(), "message": "넣은 파일과 결과를 모두 지웠습니다. 공개 실측 자료로 돌아왔습니다."})
        return self._err(404, "찾는 주소가 없습니다.")

    def _load(self, name, text):
        st = self.state
        if not isinstance(name, str) or not isinstance(text, str) or not name:
            return self._err(400, "파일 이름과 내용이 필요합니다.")
        name = Path(name.replace("\\", "/")).name[:200]
        try:
            with st.lock:
                before = (st.active() or {}).get("kind")
                info = st.store.load_text(name, text)
                after = (st.active() or {}).get("kind")
                if before != after and not st.keep_results:
                    st.reports.clear()
                    st.docs.clear()
        except ValueError as e:  # UnknownHeaderError, DuplicateFileError (A3, A8)
            msg = str(e) or "이 파일은 아직 읽을 수 없습니다."
            missing = getattr(e, "missing", None)
            return self._json(400, {"error": msg, "missing": list(missing or [])})
        except Exception:
            return self._err(400, "이 파일은 아직 읽을 수 없습니다.")
        return self._json(200, {"loaded": info, "status": st.status()})

    def _ask(self, sentence):
        st = self.state
        with st.lock:
            active = st.active()
            try:
                res = st.answer(sentence)
            except Exception:
                res = {"behavior": "error", "verdict": "none", "message": "죄송합니다. 이 문장을 처리하는 중에 문제가 생겼습니다.",
                       "notices": [], "data": {}, "decisions": [], "evidence": None, "choices": [], "suggestions": []}
            active = st.active() or active
            return self._json(200, self._publish(sentence, res, active))

    def _publish(self, sentence, res, active):
        st = self.state
        report_id = doc_id = None
        beh = res.get("behavior")
        entry = {"sentence": sentence, "result": res, "active": active}
        if beh in ("summary", "claim_check") and res.get("evidence"):
            report_id = _new_id()
            st.reports[report_id] = entry
        elif beh in ("document", "profile"):
            doc_id = _new_id()
            st.docs[doc_id] = entry
        out = dict(res)
        out["card_html"] = report.render_card(res, active, report_id, doc_id)
        out["report_id"] = report_id
        out["doc_id"] = doc_id
        out["active"] = active
        return out

    def _doc(self, obj):
        """POST /api/doc {"template", "params"}: same function as a typed request."""
        st = self.state
        tpl = obj.get("template")
        params = obj.get("params") if isinstance(obj.get("params"), dict) else {}
        sentence = None
        try:
            from . import docflow
            fn = getattr(docflow, "draft", None)
        except Exception:
            fn = None
        if fn is not None:
            with st.lock:
                active = st.active()
                try:
                    res = fn(tpl, params, store=st.store)
                except Exception:
                    res = None
                if isinstance(res, dict):
                    return self._json(200, self._publish(sentence or "", res, st.active() or active))
        sentence = compose_doc_sentence(tpl, params)
        if sentence is None:
            return self._err(400, "그런 문서 틀이 없습니다.")
        return self._ask(sentence)


def compose_doc_sentence(tpl, params):
    """Fallback for /api/doc: turn explicit params into the request sentence the core understands."""
    def clean(v, n=30):
        return str(v or "").replace("\n", " ").strip()[:n]
    month = clean(params.get("month"), 6)
    mtxt = f"{month[:4]}년 {int(month[4:])}월" if len(month) == 6 and month.isdigit() else ""
    if tpl == "consumption_trend":
        group = clean(params.get("group"))
        return " ".join(x for x in [mtxt, group, "소비동향 현황자료를 만들어 주세요"] if x)
    if tpl == "bizplan_market":
        return " ".join(x for x in [clean(params.get("bjd")), clean(params.get("biz")), "사업계획서 시장 현황을 써 주세요"] if x)
    if tpl == "data_brief":
        return " ".join(x for x in [mtxt, clean(params.get("bjd")), clean(params.get("biz")), "자료 요약을 만들어 주세요"] if x)
    return None


def make_server(port: int = 8765, state: AppState | None = None, quiet: bool = False) -> ThreadingHTTPServer:
    st = state or AppState()
    handler = type("BoundHandler", (Handler,), {"state": st})
    srv = ThreadingHTTPServer(("127.0.0.1", port), handler)
    srv.daemon_threads = True
    srv.quiet = quiet
    srv.state = st
    return srv
