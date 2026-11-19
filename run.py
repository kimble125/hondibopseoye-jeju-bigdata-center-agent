"""Start the Jeju Evidence Mate local server (section 3.9)."""
from __future__ import annotations

import sys

if sys.version_info < (3, 12):
    sys.stderr.write("Python 3.12 이상이 필요합니다. 설명서(README)를 따라 설치해 주세요. "
                     "(Python 3.12 or newer is required.)\n")
    sys.exit(2)

import argparse
import errno
import threading
import webbrowser


def _safe_stdout():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")
        except Exception:
            pass


def main(argv=None) -> int:
    _safe_stdout()
    ap = argparse.ArgumentParser(description="Jeju Evidence Mate")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args(argv)
    from evm.server import make_server
    try:
        srv = make_server(args.port)
    except OSError as e:
        if e.errno in (errno.EADDRINUSE, 10048) or "in use" in str(e).lower():
            print(f"{args.port}번 포트를 다른 프로그램이 쓰고 있습니다. 다른 번호로 실행해 주세요: run.bat --port 8766", flush=True)
        else:
            print("서버를 시작하지 못했습니다. 포트 번호를 바꿔 다시 실행해 주세요 (예: --port 8766).", flush=True)
        return 2
    port = srv.server_address[1]
    url = f"http://127.0.0.1:{port}/"
    print(f"준비되었습니다: {url}  (끝내려면 이 창에서 Ctrl+C)", flush=True)
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("끝냈습니다. 넣은 파일과 결과는 남기지 않았습니다.", flush=True)
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
