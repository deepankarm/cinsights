"""Smoke test: start cinsights serve, verify key endpoints, exit."""

import subprocess
import sys
import time
import urllib.request

PORT = 8199
BASE = f"http://localhost:{PORT}"
TIMEOUT = 30  # max seconds to wait for server


def wait_for_server():
    """Poll until the server responds or timeout."""
    start = time.time()
    while time.time() - start < TIMEOUT:
        try:
            urllib.request.urlopen(f"{BASE}/api/sessions/stats", timeout=2)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def check(url, expect_in_body, label):
    """Fetch URL and assert expected string is in the response body."""
    try:
        resp = urllib.request.urlopen(url, timeout=5)
        body = resp.read().decode()
        if expect_in_body not in body:
            print(f"FAIL: {label} — '{expect_in_body}' not found in response")
            return False
        print(f"OK: {label}")
        return True
    except Exception as e:
        print(f"FAIL: {label} — {e}")
        return False


def main():
    # Start server
    proc = subprocess.Popen(
        [sys.executable, "-m", "cinsights.cli", "serve", "--port", str(PORT)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    try:
        if not wait_for_server():
            print(f"FAIL: server did not start within {TIMEOUT}s")
            sys.exit(1)

        results = [
            check(f"{BASE}/", "__sveltekit", "/ serves index.html"),
            check(f"{BASE}/_app/version.json", "version", "/_app assets mounted"),
            check(f"{BASE}/api/sessions/stats", "total_sessions", "API responds"),
            check(f"{BASE}/projects", "__sveltekit", "SPA fallback works"),
        ]

        if not all(results):
            sys.exit(1)

        print("All smoke tests passed")
    finally:
        proc.terminate()
        proc.wait(timeout=5)


if __name__ == "__main__":
    main()
