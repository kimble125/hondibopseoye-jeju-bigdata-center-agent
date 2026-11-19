"""Golden runner (section 3.10, 10.6, 10.7 F2).
  PY -m evm.evalrun --golden eval/golden_card.json
  PY -m evm.evalrun --docs eval/golden_docs.json
Exit 0 only when every item passes."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from .agent import answer
from .store import Store

ROOT = Path(__file__).resolve().parent.parent


def _out(text: str) -> None:
    data = (text + "\n").encode("utf-8", errors="replace")
    try:
        sys.stdout.buffer.write(data)
        sys.stdout.flush()
    except (AttributeError, ValueError):
        print(text)


def first_diff(expect, got, path="data"):
    """Recursive type-and-value comparison; returns a description of the first difference or None."""
    if isinstance(expect, dict):
        if not isinstance(got, dict):
            return f"{path}: expected object, got {type(got).__name__}"
        for k, v in expect.items():
            if k not in got:
                return f"{path}.{k}: missing"
            d = first_diff(v, got[k], f"{path}.{k}")
            if d:
                return d
        return None
    if isinstance(expect, list):
        if not isinstance(got, list):
            return f"{path}: expected list, got {type(got).__name__}"
        if len(expect) != len(got):
            return f"{path}: expected {len(expect)} items, got {len(got)}"
        for i, (e, g) in enumerate(zip(expect, got)):
            d = first_diff(e, g, f"{path}[{i}]")
            if d:
                return d
        return None
    if expect is None:
        return None if got is None else f"{path}: expected null, got {got!r}"
    if type(expect) is not type(got):
        return f"{path}: expected {type(expect).__name__} {expect!r}, got {type(got).__name__} {got!r}"
    if expect != got:
        return f"{path}: expected {expect!r}, got {got!r}"
    return None


def check_sources(golden: dict, root: Path):
    bad = []
    for rel, digest in golden.get("sources", {}).items():
        p = root / rel
        if not p.is_file():
            bad.append(f"{rel}: missing")
        elif hashlib.sha256(p.read_bytes()).hexdigest() != digest:
            bad.append(f"{rel}: sha256 mismatch")
    return bad


def run(golden_path: str, docs: bool) -> int:
    gp = Path(golden_path)
    if not gp.is_absolute():
        gp = (Path.cwd() / gp) if (Path.cwd() / gp).is_file() else ROOT / gp
    golden = json.loads(gp.read_text(encoding="utf-8"))
    bad = check_sources(golden, ROOT)
    if bad:
        _out("입력 파일이 정답표와 다릅니다(sha256 점검 실패):")
        for b in bad:
            _out("  " + b)
        return 2
    items = golden["items"]
    lines, messages, passed = [], [], 0
    for it in items:
        store = Store()
        if docs:
            store.load_library()
        for f in it["files"]:
            store.load_path(ROOT / f)
        question = it["request"] if docs else it["question"]
        res = answer(question, store=store, llm=None)
        if docs:
            tpl = it["template"]
            want_behavior = {"consumption_trend": "document", "bizplan_market": "document", "data_brief": "document",
                             "ask_scope": "ask_scope", "profile": "profile", "recommend_data": "recommend_data"}.get(tpl, "document")
            diff = None
            if res.get("behavior") != want_behavior:
                diff = f"behavior: expected {want_behavior}, got {res.get('behavior')}"
            elif want_behavior == "document" and res.get("intent", {}).get("template") != tpl:
                diff = f"intent.template: expected {tpl}, got {res.get('intent', {}).get('template')}"
            else:
                diff = first_diff(it["expect"], res.get("data"))
            verdict = res.get("verdict")
        else:
            diff = None
            if res.get("behavior") != it["behavior"]:
                diff = f"behavior: expected {it['behavior']}, got {res.get('behavior')}"
            elif res.get("verdict") != it["verdict"]:
                diff = f"verdict: expected {it['verdict']}, got {res.get('verdict')}"
            else:
                diff = first_diff(it["expect"], res.get("data"))
            verdict = res.get("verdict")
        ok = diff is None
        passed += ok
        lines.append(f"{it['id']:<4} {str(res.get('behavior')):<14} {str(verdict):<10} {'pass' if ok else 'FAIL'}  {diff or ''}".rstrip())
        messages.append(f"[{it['id']}] {res.get('message', '')}")
    _out("id   behavior       verdict    result")
    for ln in lines:
        _out(ln)
    _out("")
    for m in messages:
        _out(m)
    _out("")
    _out(f"PASS {passed}/{len(items)}")
    return 0 if passed == len(items) else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="evm.evalrun")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--golden")
    g.add_argument("--docs")
    a = ap.parse_args(argv)
    return run(a.docs, True) if a.docs else run(a.golden, False)


if __name__ == "__main__":
    sys.exit(main())
