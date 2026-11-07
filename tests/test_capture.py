#!/usr/bin/env python3
"""
Capture server check: queue order, resume, leases, write safety, token and stop-on-block.
Exit Code 0 = PASS, Non-Zero = FAIL
"""
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))

import capture_server  # noqa: E402
from capture_server import CaptureQueue, start_server  # noqa: E402


def fail(reason, evidence=""):
    print(json.dumps({"UNIT": "capture_server", "VERDICT": "FAIL", "REASON": reason, "EVIDENCE": str(evidence)}))
    sys.exit(1)


def call(port, path, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def main():
    urls = ["https://www.linkedin.com/in/a/", "https://www.linkedin.com/in/b/"]
    with tempfile.TemporaryDirectory() as out:
        queue = CaptureQueue(urls, out, sections=["profile", "skills"])
        first = queue.next_task()
        if first != {"slug": "a", "section": "profile", "url": "https://www.linkedin.com/in/a/"}:
            fail("First task is wrong", first)
        second = queue.next_task()
        if (second["slug"], second["section"]) != ("b", "profile"):
            fail("Main pages are not read first, or a leased task was handed out twice", second)
        if queue.save("../evil", "profile", "x") or queue.save("a", "../../x", "x"):
            fail("Saved a page outside the queue")
        # 'a' turns out not to be a profile (no name): its other pages must not be requested.
        queue.save("a", "profile", "<html><main><p>This page doesn't exist</p></main></html>")

        resumed = CaptureQueue(urls, out, sections=["profile", "skills"])
        task = resumed.next_task()
        if (task["slug"], task["section"]) != ("b", "profile") or resumed.status()["done"] != 2:
            fail("Saved or unusable pages are requested again on a new run", (task, resumed.status()))
        if resumed.next_task() is not None:
            fail("Pages of an unusable profile were requested", resumed.status())

        server = start_server(queue, "ext", port=0)
        port = server.server_address[1]
        status, job = call(port, "/next")
        if status != 200 or "token" not in job:
            fail("/next did not answer", job)
        if call(port, "/result", {"token": "wrong", "slug": "b", "section": "profile", "html": "x"})[0] != 403:
            fail("A request without the token was accepted")
        if not call(port, "/result", {"token": job["token"], "slug": "b", "section": "profile", "html": "<p>b</p>"})[1]["saved"]:
            fail("A valid page was not saved")
        if not os.path.exists(os.path.join(out, "b", "profile.html")):
            fail("Saved page missing on disk")
        call(port, "/blocked", {"token": job["token"], "url": "https://www.linkedin.com/checkpoint/x"})
        if call(port, "/next")[1]["task"] is not None or not queue.status()["blocked"]:
            fail("The queue kept going after a checkpoint")
        server.shutdown()

    if capture_server.PORT != 8765:
        fail("Port differs from the extension's host permission", capture_server.PORT)
    print(json.dumps({"UNIT": "capture_server", "VERDICT": "PASS"}))


if __name__ == "__main__":
    main()
