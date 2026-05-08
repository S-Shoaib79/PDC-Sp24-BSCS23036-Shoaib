"""
Demo script for the 2-minute screen recording.

Walks the grader through:
    1. App is healthy           -> /ask returns an LLM answer.
    2. We flip the LLM "down"   -> /ask now serves fallback after fast-fail.
    3. After N failures the breaker OPENS -> calls short-circuit instantly.
    4. After the cooldown elapses, the breaker recovers (HALF_OPEN -> CLOSED).

Run the server first:
    uvicorn app.main:app --reload --port 8000

Then in a second terminal:
    python demo.py
"""

from __future__ import annotations

import time

import os

import httpx

BASE = os.environ.get("STUDYSYNC_BASE", "http://127.0.0.1:8000")


def banner(title: str) -> None:
    print("\n" + "=" * 64)
    print(f"  {title}")
    print("=" * 64)


def show(resp: httpx.Response) -> None:
    elapsed_ms = resp.elapsed.total_seconds() * 1000
    print(
        f"  HTTP {resp.status_code} in {elapsed_ms:6.1f} ms"
        f" | X-Student-ID = {resp.headers.get('X-Student-ID')!r}"
    )
    try:
        print(f"  body  : {resp.json()}")
    except Exception:
        print(f"  body  : {resp.text}")


def main() -> None:
    with httpx.Client(base_url=BASE, timeout=10.0) as c:
        c.post("/admin/breaker/reset")
        c.post("/admin/llm-mode", json={"mode": "healthy"})

        banner("STEP 1 — healthy upstream, breaker CLOSED")
        show(c.post("/ask", json={"prompt": "What is the CAP theorem?"}))
        show(c.get("/breaker"))

        banner("STEP 2 — upstream goes DOWN; we fail fast & serve fallback")
        c.post("/admin/llm-mode", json={"mode": "down"})
        for i in range(4):
            print(f"  request #{i + 1}")
            show(c.post("/ask", json={"prompt": "hello?"}))
        show(c.get("/breaker"))

        banner("STEP 3 — breaker OPEN, calls short-circuit in <1ms")
        for i in range(3):
            print(f"  request #{i + 1}")
            show(c.post("/ask", json={"prompt": "still there?"}))

        banner("STEP 4 — recovery: heal upstream, wait for cooldown, retry")
        c.post("/admin/llm-mode", json={"mode": "healthy"})
        snap = c.get("/breaker").json()
        wait = snap.get("seconds_until_half_open", 0) + 0.5
        print(f"  sleeping {wait:.1f}s for breaker cooldown...")
        time.sleep(wait)
        show(c.post("/ask", json={"prompt": "are we back?"}))
        show(c.get("/breaker"))


if __name__ == "__main__":
    main()
