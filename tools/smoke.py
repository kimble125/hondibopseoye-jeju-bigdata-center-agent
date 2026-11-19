"""End-to-end smoke test over HTTP with the real answer (gate G2/G2b). Standard library only.

Usage: PY -m tools.smoke   (starts a server on a free 127.0.0.1 port and stops it by itself)
"""
from __future__ import annotations

import json
import re
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXTERNAL = re.compile(r"""(?:\b(?:src|href|action)\s*=\s*["']?\s*(?:https?:)?//)|(?:url\(\s*["']?\s*(?:https?:)?//)|@import""", re.I)


class Smoke:
    def __init__(self):
        from evm.server import AppState, make_server
        self.httpd = make_server(0, AppState(settings={"KEEP_RESULTS": "0"}), quiet=True)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.failures = []
        self.passed = 0

    def check(self, ok, label):
        if ok:
            self.passed += 1
            print(f"ok   {label}")
        else:
            self.failures.append(label)
            print(f"FAIL {label}")

    def get(self, path):
        try:
            with urllib.request.urlopen(self.base + path, timeout=30) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            body = e.read()
            e.close()
            return e.code, body

    def post(self, path, obj):
        req = urllib.request.Request(self.base + path, data=json.dumps(obj).encode("utf-8"), method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read()
            e.close()
            try:
                return e.code, json.loads(body.decode("utf-8"))
            except ValueError:
                return e.code, {}

    def no_external(self, label, body: bytes):
        text = body.decode("utf-8", errors="replace")
        self.check(EXTERNAL.search(text) is None, f"no resource from another host: {label}")

    def ask(self, sentence, behavior, label):
        code, res = self.post("/api/ask", {"sentence": sentence})
        self.check(code == 200 and res.get("behavior") == behavior, f"{label}: behavior {res.get('behavior')} (want {behavior})")
        if code == 200:
            self.no_external(f"card {label}", res.get("card_html", "").encode("utf-8"))
        return res

    def run(self) -> int:
        try:
            self._run()
        finally:
            self.httpd.shutdown()
            self.httpd.server_close()
        print(f"SMOKE {'PASS' if not self.failures else 'FAIL'} {self.passed}/{self.passed + len(self.failures)}")
        return 0 if not self.failures else 1

    def _run(self):
        code, body = self.get("/")
        self.check(code == 200 and b"/static/app.js" in body, "GET / serves the page")
        self.no_external("index.html", body)
        for name in ("app.js", "style.css"):
            code, b = self.get("/static/" + name)
            self.check(code == 200, f"GET /static/{name}")
            self.no_external(name, b)
        self.check(self.get("/static/../run.py")[0] == 404 and self.get("/inputs/")[0] == 404, "no directory listing or file access")

        code, st = self.get("/api/status")
        st = json.loads(st.decode("utf-8"))
        self.check(bool((st.get("branding") or {}).get("product_name")), "/api/status branding.product_name")
        self.check(st.get("llm_mode") == "off", "external AI off by default")

        code, g = self.get("/api/guide")
        g = json.loads(g.decode("utf-8"))
        self.check(len(g.get("steps") or []) >= 5, f"/api/guide steps {len(g.get('steps') or [])} >= 5")
        code, c = self.get("/api/catalog")
        c = json.loads(c.decode("utf-8"))
        self.check(len(c.get("datasets") or []) >= 60, f"/api/catalog datasets {len(c.get('datasets') or [])} >= 60")
        if (ROOT / "inputs" / "mascot.svg").is_file():
            self.check(self.get("/api/mascot")[0] == 200, "/api/mascot")

        # one of each behaviour on the bundled public table
        res = self.ask("2025년 6월 호텔업 카드 이용 현황을 보여 주세요", "summary", "summary")
        rid = res.get("report_id")
        code, sheet = self.get(f"/report/{rid}")
        self.check(code == 200 and "인쇄 / PDF로 저장".encode("utf-8") in sheet, "public sheet fetched with print button")
        self.no_external("public sheet", sheet)
        self.ask("호텔업은 법인이 도민보다 많이 썼다", "claim_check", "claim_check")
        self.ask("카페는 관광객이 도민보다 많이 쓴다", "ask_scope", "ask_scope")
        self.ask("연동 호텔업 카드 이용금액을 보여 주세요", "need_file", "need_file")
        self.ask("호텔업은 왜 줄었나요", "cannot", "cannot")
        self.ask(" ", "error", "error")

        # documents (M2b)
        res = self.ask("카페 창업 사업계획서 작성에 어떤 자료를 받아야 하나요", "recommend_data", "recommend_data")
        for tpl, params in (("consumption_trend", {"month": "202506"}), ("bizplan_market", {"biz": "호텔업"}),
                            ("data_brief", {"biz": "호텔업"})):
            code, res = self.post("/api/doc", {"template": tpl, "params": params})
            ok = code == 200 and res.get("behavior") == "document"
            self.check(ok, f"/api/doc {tpl}: {res.get('behavior')}")
            if ok and res.get("doc_id"):
                code, page = self.get(f"/doc/{res['doc_id']}")
                self.check(code == 200 and "인쇄 / PDF로 저장".encode("utf-8") in page, f"/doc page {tpl}")
                self.no_external(f"doc {tpl}", page)

        # synthetic center sample, masked summary and its sheet
        code, res = self.post("/api/load_sample", {"name": "SYNTHETIC_card_emd_v02_202506.csv"})
        self.check(code == 200 and (res.get("status") or {}).get("active", {}).get("synthetic") is True, "load synthetic sample")
        res = self.ask("성산읍 스포츠 및 레크레이션 용품 임대업 카드 이용 현황을 보여 주세요", "summary", "masked summary")
        exp = (res.get("data") or {}).get("export") or {}
        self.check(bool(exp.get("masked_groups")) and exp.get("totals_hidden") is True, "masked groups and hidden totals")
        code, sheet = self.get(f"/report/{res.get('report_id')}")
        txt = sheet.decode("utf-8")
        self.check(code == 200 and "반출 신청용 점검 요약" in txt and "<svg" not in txt and "10 미만(가림)" in txt,
                   "center sheet: reviewer summary, masked cells, no chart")
        self.check("가상 데이터 시연" in txt, "synthetic banner on sheet")
        center_rid = res.get("report_id")
        code, res = self.post("/api/doc", {"template": "bizplan_market", "params": {"biz": "한식 음식점업", "bjd": "노형동"}})
        if code == 200 and res.get("doc_id"):
            code, page = self.get(f"/doc/{res['doc_id']}")
            self.check(code == 200 and b"<svg" not in page, "center document page has no chart")

        # generic profile
        code, res = self.post("/api/load_sample", {"name": "SYNTHETIC_bus_station_usage_202611.csv"})
        self.check(code == 200, "load generic sample")
        self.ask("이 자료를 요약해 주세요", "profile", "profile")

        # clear
        code, res = self.post("/api/clear", {})
        act = (res.get("status") or {}).get("active") or {}
        self.check(code == 200 and act.get("kind") == "hub_biz_sex" and not act.get("synthetic"), "clear returns to the public table")
        code, body = self.get(f"/report/{center_rid}")
        self.check(code == 404 and "지워진 결과입니다".encode("utf-8") in body, "old sheet is gone after clear")


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")
        except Exception:
            pass
    return Smoke().run()


if __name__ == "__main__":
    raise SystemExit(main())
