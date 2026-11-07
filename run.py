#!/usr/bin/env python3
"""
Runs the whole project from a file of LinkedIn profile URLs (any number of profiles).

  python run.py            Reads every profile through the browser extension, then analyzes,
                           packages and verifies. The only manual step is installing the
                           extension once in a browser where you are logged in to LinkedIn.
  python run.py analyze    Skips reading; analyzes pages already saved (--saved DIR).

Options: --urls FILE (default urls.txt), --saved DIR (default raw_live/).
"""
import argparse
import os
import subprocess
import sys
import time
import webbrowser
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "src"))

from capture_server import PORT, CaptureQueue, start_server  # noqa: E402
from live_browser import read_urls_file, slug_of  # noqa: E402

MIN_PROFILES = 2  # A graph needs at least two people.
RAW_LIVE_DIR = os.path.join(ROOT, "raw_live")
EXTENSION_DIR = os.path.join(ROOT, "browser_extension")
NO_EXTENSION_TIMEOUT_S = 15 * 60


def load_urls(path):
    """Returns the file's profile URLs, or exits with a message saying what to fix."""
    if not os.path.isfile(path):
        sys.exit(f"File not found: {path}")
    urls = read_urls_file(path)
    not_profiles = [u for u in urls if not urlparse(u).path.startswith("/in/")]
    if not_profiles:
        sys.exit("These lines are not LinkedIn profile URLs (expected .../in/<name>):\n  " + "\n  ".join(not_profiles))
    if len(urls) < MIN_PROFILES:
        sys.exit(f"{path} has {len(urls)} profile URL(s); at least {MIN_PROFILES} are needed.")
    return urls


def capture_with_extension(urls, open_page=True):
    """Serves the page queue to the extension and waits until every page is saved."""
    queue = CaptureQueue(urls, RAW_LIVE_DIR)
    status = queue.status()
    if status["finished"]:
        print("All pages are already saved; skipping the browser step.")
        return
    try:
        server = start_server(queue, EXTENSION_DIR)
    except OSError:
        sys.exit(f"Port {PORT} is busy. Close the other run.py and try again.")

    remaining = status["total"] - status["done"]
    print(f"{remaining} pages to read ({len(urls)} profiles). Estimated time: about {max(1, round(remaining * 11 / 60))} minutes.")
    print(f"Progress page: http://127.0.0.1:{PORT}/  (open it in the browser where the extension is installed)")
    if open_page:
        webbrowser.open(f"http://127.0.0.1:{PORT}/")

    last_done, last_print = -1, 0.0
    try:
        while True:
            status = queue.status()
            if status["blocked"]:
                server.shutdown()
                sys.exit(f"Stopped: {status['blocked']}. Open LinkedIn in that browser, resolve it, then run again; saved pages are kept.")
            if status["finished"]:
                break
            if status["done"] != last_done:
                print(f"  {status['done']}/{status['total']} pages saved")
                last_done = status["done"]
            if status["seconds_since_contact"] is None:
                waited = time.time() - queue.started_at
                if waited > NO_EXTENSION_TIMEOUT_S:
                    server.shutdown()
                    sys.exit("The extension never connected. Install it as shown on the progress page, then run again.")
                if time.time() - last_print > 60:
                    print(f"  Waiting for the extension. If it is not installed, load {EXTENSION_DIR} in chrome://extensions.")
                    last_print = time.time()
            time.sleep(1)
    except KeyboardInterrupt:
        server.shutdown()
        sys.exit("Stopped by you; saved pages are kept and the next run continues from here.")
    server.shutdown()
    print("All pages saved.")


def run_steps(steps):
    for label, step in steps:
        print(f"\n== {label}")
        code = subprocess.run([sys.executable] + step, cwd=ROOT).returncode
        if code != 0:
            sys.exit(code)


def analyze(urls_path, saved_dir):
    run_steps([
        ("Parsing saved pages", [os.path.join(ROOT, "src", "extractor.py"), "--mode", "replay",
                                 "--urls-file", urls_path, "--capture-dir", saved_dir]),
        ("Graph and ML analysis", [os.path.join(ROOT, "src", "analyzer.py")]),
        ("Packaging", [os.path.join(ROOT, "src", "merge_and_verify.py")]),
        ("Verification", [os.path.join(ROOT, "verify_all.py")]),
    ])
    print("\nDone. Data: data/  Results: output/  Package: dist/cyberyan_ai_specialist_project.zip")


def main():
    parser = argparse.ArgumentParser(description="Run the project from a file of LinkedIn profile URLs.")
    parser.add_argument("command", nargs="?", choices=["auto", "analyze"], default="auto")
    parser.add_argument("--urls", default=os.path.join(ROOT, "urls.txt"))
    parser.add_argument("--saved", default=RAW_LIVE_DIR)
    parser.add_argument("--no-open", action="store_true", help="Do not open the progress page in the default browser.")
    args = parser.parse_args()

    urls_path = os.path.abspath(args.urls)
    urls = load_urls(urls_path)
    print(f"Read {len(urls)} profiles from {urls_path}")

    if args.command == "auto":
        capture_with_extension(urls, open_page=not args.no_open)
        analyze(urls_path, RAW_LIVE_DIR)
    else:
        saved_dir = os.path.abspath(os.path.expanduser(args.saved))
        missing = [slug_of(u) for u in urls if not os.path.exists(os.path.join(saved_dir, slug_of(u), "profile.html"))]
        if missing:
            sys.exit(f"No saved main page for: {', '.join(missing)} (looked in {saved_dir})")
        analyze(urls_path, saved_dir)


if __name__ == "__main__":
    main()
