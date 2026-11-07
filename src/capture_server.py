#!/usr/bin/env python3
"""
Local capture server for the browser extension.

`run.py` starts this server on 127.0.0.1. The extension, running in the operator's normal
browser where they are already logged in to LinkedIn, asks it for the next page to open,
loads that page in its own window, scrolls it, and posts the rendered HTML back. The server
saves each page to `raw_live/<slug>/<section>.html`.

The queue lives here, not in the extension, so a restarted extension worker simply continues.
Pages already saved are skipped. A LinkedIn checkpoint or login page stops the whole run.
"""

from __future__ import annotations

import json
import os
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, List, Optional, Tuple

from live_browser import SECTIONS, _root, _top_card, heading_counts, page_is_complete, slug_of

PORT = 8765
LEASE_SECONDS = 120  # A page handed out but not returned in this time is handed out again.
MAX_BODY_BYTES = 30 * 1024 * 1024
DELAY_RANGE_S = (5.0, 9.0)  # Pause between pages, applied by the extension.
MAX_SAVES_PER_PAGE = 3  # A page that keeps coming back incomplete is accepted after this many saves.


class CaptureQueue:
    """Thread-safe list of (slug, section, url) pages to capture."""

    def __init__(self, urls: List[str], out_dir: str, sections: Optional[List[str]] = None):
        self.out_dir = out_dir
        self.token = secrets.token_hex(16)
        self.lock = threading.Lock()
        # Main pages first: a profile whose main page shows no profile gets no further requests.
        self.tasks: List[Tuple[str, str, str]] = [
            (slug_of(url), section, url + SECTIONS[section])
            for section in (sections or list(SECTIONS))
            for url in urls
        ]
        self.unusable: set = set()
        self.saves: Dict[Tuple[str, str], int] = {}
        self._complete_cache: Dict[str, Tuple[float, bool]] = {}
        self.leases: Dict[Tuple[str, str], float] = {}
        self.blocked: Optional[str] = None
        self.last_contact: Optional[float] = None
        self.started_at = time.time()

    def path(self, slug: str, section: str) -> str:
        return os.path.join(self.out_dir, slug, f"{section}.html")

    def _profile_unusable(self, slug: str) -> bool:
        """True once the saved main page turns out to show no profile (wrong URL, removed account)."""
        if slug in self.unusable:
            return True
        main = self.path(slug, "profile")
        if not os.path.exists(main):
            return False
        with open(main, "r", encoding="utf-8") as f:
            name, *_ = _top_card(_root(f.read()))
        if not name:
            self.unusable.add(slug)
        return not name

    def _is_complete(self, slug: str, section: str) -> bool:
        path = self.path(slug, section)
        mtime = os.path.getmtime(path)
        cached = self._complete_cache.get(path)
        if cached is None or cached[0] != mtime:
            expected = None
            if section == "skills" and os.path.exists(self.path(slug, "profile")):
                with open(self.path(slug, "profile"), "r", encoding="utf-8") as f:
                    expected = heading_counts(f.read()).get("Skills")
            with open(path, "r", encoding="utf-8") as f:
                cached = (mtime, page_is_complete(section, f.read(), expected))
            self._complete_cache[path] = cached
        return cached[1]

    def is_done(self, slug: str, section: str) -> bool:
        """
        Saved with its content, or not needed because the profile itself could not be read.
        A page saved before its sections loaded is asked for again, up to MAX_SAVES_PER_PAGE saves.
        """
        if self._profile_unusable(slug):
            return True
        if not os.path.exists(self.path(slug, section)):
            return False
        return self.saves.get((slug, section), 0) >= MAX_SAVES_PER_PAGE or self._is_complete(slug, section)

    def next_task(self) -> Optional[Dict[str, str]]:
        with self.lock:
            self.last_contact = time.time()
            if self.blocked:
                return None
            now = time.time()
            for slug, section, url in self.tasks:
                if self.is_done(slug, section):
                    continue
                if section != "profile" and not os.path.exists(self.path(slug, "profile")):
                    continue  # Wait until the main page shows this is a real profile.
                if now - self.leases.get((slug, section), 0) < LEASE_SECONDS:
                    continue
                self.leases[(slug, section)] = now
                return {"slug": slug, "section": section, "url": url}
            return None

    def save(self, slug: str, section: str, html: str) -> bool:
        """Saves one page. Only pages in the queue are accepted, so paths cannot be chosen freely."""
        if not any(t[0] == slug and t[1] == section for t in self.tasks):
            return False
        os.makedirs(os.path.join(self.out_dir, slug), exist_ok=True)
        tmp = self.path(slug, section) + ".part"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(html)
        os.replace(tmp, self.path(slug, section))
        with self.lock:
            self.last_contact = time.time()
            self.leases.pop((slug, section), None)
            self.saves[(slug, section)] = self.saves.get((slug, section), 0) + 1
        return True

    def block(self, reason: str) -> None:
        with self.lock:
            self.blocked = reason

    def status(self) -> Dict[str, object]:
        done = sum(self.is_done(s, sec) for s, sec, _ in self.tasks)
        return {
            "total": len(self.tasks),
            "done": done,
            "finished": done == len(self.tasks),
            "blocked": self.blocked,
            "extension_connected": self.last_contact is not None and time.time() - self.last_contact < 75,
            "seconds_since_contact": None if self.last_contact is None else round(time.time() - self.last_contact),
        }


def _control_page(extension_dir: str) -> str:
    return f"""<!doctype html><html lang="fa" dir="rtl"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>LinkedIn capture</title>
<style>
:root {{ --bg:#f8fafc; --fg:#0f172a; --muted:#475569; --card:#fff; --line:#cbd5e1; --ok:#059669; --bad:#dc2626; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#0b1120; --fg:#e2e8f0; --muted:#94a3b8; --card:#111827; --line:#334155; }} }}
body {{ font:16px/1.8 system-ui, sans-serif; background:var(--bg); color:var(--fg); max-width:760px; margin:32px auto; padding:0 16px; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:16px 20px; margin:16px 0; }}
progress {{ width:100%; height:18px; }} code {{ direction:ltr; unicode-bidi:embed; }}
.ok {{ color:var(--ok); }} .bad {{ color:var(--bad); }} .muted {{ color:var(--muted); }}
</style>
<h1>استخراج پروفایل‌ها</h1>
<div class="card"><b id="state">در انتظار افزونه…</b><br><progress id="bar" value="0" max="1"></progress>
<div id="count" class="muted"></div></div>
<div class="card" id="install"><b>اگر افزونه نصب نیست (فقط یک‌بار):</b><ol>
<li>در همین مرورگر <code>chrome://extensions</code> را باز کنید.</li>
<li>Developer mode را روشن کنید و Load unpacked را بزنید.</li>
<li>پوشه‌ی <code>{extension_dir}</code> را انتخاب کنید.</li>
<li>مطمئن شوید در همین مرورگر وارد لینکدین هستید. افزونه ظرف ۳۰ ثانیه شروع می‌کند.</li></ol></div>
<p class="muted">افزونه برای خواندن صفحه‌ها یک پنجره‌ی جدا باز می‌کند؛ آن را نبندید. اگر لینکدین چالش امنیتی نشان دهد، کار متوقف می‌شود.</p>
<script>
async function tick() {{
  try {{
    const s = await (await fetch("/status")).json();
    const bar = document.getElementById("bar"), state = document.getElementById("state");
    bar.max = s.total; bar.value = s.done;
    document.getElementById("count").textContent = s.done + " از " + s.total + " صفحه ذخیره شد";
    document.getElementById("install").style.display = s.extension_connected ? "none" : "block";
    if (s.blocked) {{ state.textContent = "متوقف شد: " + s.blocked; state.className = "bad"; return; }}
    if (s.finished) {{ state.textContent = "همه‌ی صفحه‌ها ذخیره شد. تحلیل در ترمینال اجرا می‌شود."; state.className = "ok"; return; }}
    state.textContent = s.extension_connected ? "افزونه در حال کار است…" : "در انتظار افزونه…";
    state.className = "";
  }} catch (e) {{ document.getElementById("state").textContent = "کار سرور تمام شد."; return; }}
  setTimeout(tick, 2000);
}}
tick();
</script></html>"""


def make_handler(queue: CaptureQueue, extension_dir: str):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: object, content_type: str = "application/json") -> None:
            data = body.encode("utf-8") if isinstance(body, str) else json.dumps(body).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/":
                self._send(200, _control_page(extension_dir), "text/html")
            elif self.path == "/status":
                self._send(200, queue.status())
            elif self.path == "/next":
                task = queue.next_task()
                self._send(200, {"task": task, "token": queue.token, "delay_range_s": DELAY_RANGE_S})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY_BYTES:
                self._send(413, {"error": "too large"})
                return
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                self._send(400, {"error": "bad json"})
                return
            # The token is only readable by the extension (other web pages cannot read /next).
            if body.get("token") != queue.token:
                self._send(403, {"error": "bad token"})
                return
            if self.path == "/result":
                ok = queue.save(str(body.get("slug")), str(body.get("section")), str(body.get("html") or ""))
                self._send(200 if ok else 400, {"saved": ok})
            elif self.path == "/blocked":
                queue.block(f"LinkedIn showed {body.get('url')}")
                self._send(200, {"stopped": True})
            else:
                self._send(404, {"error": "not found"})

        def log_message(self, format, *args):  # Keep the terminal readable.
            pass

    return Handler


def start_server(queue: CaptureQueue, extension_dir: str, port: int = PORT) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(queue, extension_dir))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
