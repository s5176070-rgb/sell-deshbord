"""Serve page.html on localhost with a button that reruns the whole chain.

The published artifact is a static file on claude.ai: nothing in it can fetch a
price or run the model, so a button there could only ever lie. Served from here
it can be real - the button posts to this process, which runs the same scripts
a refresh runs by hand and then the browser reloads the rewritten page.

    python artifact/serve.py          # then open http://127.0.0.1:8766

What the button does NOT do is publish. The two artifact URLs are updated by
Claude and by nothing else, so the local page can be ahead of them. The page
dates itself from score.csv, so which one you are looking at is always legible.

Bound to 127.0.0.1 on purpose. /refresh takes no input of any kind - it runs a
fixed list of scripts from this repository - but it does run them, so it has no
business being reachable from another machine.
"""
import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).parent
PROJECT = HERE.parent
PAGE = HERE / "page.html"
HOST, PORT = "127.0.0.1", 8766

# In the order the data depends on it: the feeds, then the score, then the page.
# breadth.py is the slow one, about two minutes on its own.
CHAIN = ["breadth.py", "fear.py", "debt.py", "check.py", "artifact/refresh.py"]
TIMEOUT = 900

running = threading.Lock()


def run_chain():
    """Every script in order. Returns (ok, log lines)."""
    log = []
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    for script in CHAIN:
        started = time.monotonic()
        print(f"  {script} …", flush=True)
        try:
            done = subprocess.run([sys.executable, script], cwd=PROJECT, env=env,
                                  capture_output=True, text=True,
                                  encoding="utf-8", errors="replace",
                                  timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            log.append(f"{script}: חרג מ-{TIMEOUT} שניות")
            return False, log
        took = time.monotonic() - started
        if done.returncode != 0:
            tail = (done.stderr or done.stdout or "").strip().splitlines()[-3:]
            log.append(f"{script}: יצא עם {done.returncode} — {' / '.join(tail)}")
            print(f"  {script} failed:\n{done.stderr}", flush=True)
            return False, log
        last = [ln for ln in (done.stdout or "").strip().splitlines() if ln.strip()]
        log.append(f"{script}: {took:.0f}s — {last[-1] if last else 'ok'}")
    return True, log


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):      # one line per request, not three
        print(f"  {self.command} {self.path} {fmt % args}", flush=True)

    def send_json(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.split("?")[0] not in ("/", "/index.html", "/page.html"):
            self.send_error(404)
            return
        body = PAGE.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")   # a reload must re-read
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/refresh":
            self.send_error(404)
            return
        if not running.acquire(blocking=False):
            self.send_json(409, {"ok": False, "error": "רענון אחר עוד רץ"})
            return
        try:
            print("refresh:", flush=True)
            ok, log = run_chain()
            print("  done\n" if ok else "  failed\n", flush=True)
            self.send_json(200 if ok else 500,
                           {"ok": ok, "log": log,
                            "error": None if ok else log[-1] if log else "נכשל"})
        finally:
            running.release()


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"מד לחץ שוק · http://{HOST}:{PORT}")
    print(f"the button runs: {', '.join(CHAIN)}")
    print("ctrl-c to stop\n", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
