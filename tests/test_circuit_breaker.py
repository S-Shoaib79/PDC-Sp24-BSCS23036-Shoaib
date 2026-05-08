"""
Tests that simulate the production failure described in Problem 3 of the
assignment ("the LLM hangs and the whole server hangs with it") and prove
that the circuit-breaker fix handles it gracefully.

Run with:
    pytest -v
"""

from __future__ import annotations

import asyncio
import time

import pytest
from httpx import ASGITransport, AsyncClient

from app.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitState,
)
from app.llm_client import llm_client
from app.main import STUDENT_ID, app, breaker


@pytest.fixture(autouse=True)
def _reset_state():
    breaker.force_reset()
    llm_client.set_mode("healthy")
    yield
    breaker.force_reset()
    llm_client.set_mode("healthy")


def _client() -> AsyncClient:
    # AsyncClient + ASGITransport runs the app in-process on the current
    # event loop, which avoids the Windows + Py3.8 TestClient teardown bug.
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# --------------------------------------------------------------------------- #
# Mandatory submission rule: every response carries X-Student-ID.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_student_id_header_present_on_every_response():
    async with _client() as c:
        for path in ["/health", "/breaker"]:
            r = await c.get(path)
            assert r.status_code == 200
            assert r.headers.get("X-Student-ID") == STUDENT_ID, (
                f"X-Student-ID header missing on {path}"
            )


# --------------------------------------------------------------------------- #
# The "before" scenario: without protection, a 60s LLM hang would freeze
# the request. We assert the breaker enforces a fast-fail timeout instead.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_slow_upstream_does_not_block_request():
    llm_client.set_mode("slow")  # simulates the 60s timeout from the spec

    async with _client() as c:
        started = time.monotonic()
        r = await c.post("/ask", json={"prompt": "explain transformers"})
        elapsed = time.monotonic() - started

    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "fallback"
    # Breaker call_timeout is 2s; allow generous slack for CI cold start.
    assert elapsed < 5.0, f"Request blocked for {elapsed:.2f}s (should fail fast)"


# --------------------------------------------------------------------------- #
# The breaker must trip after N consecutive failures and short-circuit
# subsequent calls (no upstream call attempted, no waiting).
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_breaker_opens_after_threshold_failures_and_short_circuits():
    llm_client.set_mode("down")

    async with _client() as c:
        for _ in range(breaker.failure_threshold):
            r = await c.post("/ask", json={"prompt": "hi"})
            assert r.status_code == 200
            assert r.json()["source"] == "fallback"

        snap = (await c.get("/breaker")).json()
        assert snap["state"] == CircuitState.OPEN.value

        # Once OPEN, even if upstream came back, calls should be rejected fast
        # until the recovery window elapses. We verify by timing.
        llm_client.set_mode("healthy")
        started = time.monotonic()
        r = await c.post("/ask", json={"prompt": "hi"})
        elapsed = time.monotonic() - started

    assert r.json()["source"] == "fallback"
    assert elapsed < 0.2, "OPEN breaker should reject instantly"


# --------------------------------------------------------------------------- #
# Recovery: after the cooldown the breaker enters HALF_OPEN, lets one
# probe through, and on success returns to CLOSED.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_breaker_recovers_via_half_open_probe():
    cb = CircuitBreaker(
        failure_threshold=2, recovery_timeout=0.3, call_timeout=1.0, name="t"
    )

    async def boom():
        raise ConnectionError("upstream down")

    async def ok():
        return "pong"

    for _ in range(2):
        with pytest.raises(ConnectionError):
            await cb.call(boom)
    assert cb.state == CircuitState.OPEN

    with pytest.raises(CircuitBreakerOpenError):
        await cb.call(ok)

    await asyncio.sleep(0.35)  # let cooldown elapse
    result = await cb.call(ok)  # probe in HALF_OPEN
    assert result == "pong"
    assert cb.state == CircuitState.CLOSED


# --------------------------------------------------------------------------- #
# A failed probe in HALF_OPEN re-opens the breaker immediately.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_failed_probe_reopens_breaker():
    cb = CircuitBreaker(
        failure_threshold=1, recovery_timeout=0.2, call_timeout=1.0, name="t2"
    )

    async def boom():
        raise ConnectionError("still down")

    with pytest.raises(ConnectionError):
        await cb.call(boom)
    assert cb.state == CircuitState.OPEN

    await asyncio.sleep(0.25)
    with pytest.raises(ConnectionError):
        await cb.call(boom)  # HALF_OPEN probe fails -> back to OPEN
    assert cb.state == CircuitState.OPEN


# --------------------------------------------------------------------------- #
# Thundering-herd guard: when many concurrent callers arrive in HALF_OPEN,
# only ONE may reach the upstream. The rest must be rejected immediately
# with CircuitBreakerOpenError so a recovering dependency is not re-killed.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_halfopen_admits_only_one_concurrent_probe():
    cb = CircuitBreaker(
        failure_threshold=1, recovery_timeout=0.05, call_timeout=2.0, name="probe"
    )

    async def fail():
        raise ConnectionError("down")

    # Trip the breaker.
    with pytest.raises(ConnectionError):
        await cb.call(fail)
    assert cb.state == CircuitState.OPEN

    # Let the cooldown elapse so the next call(s) can probe.
    await asyncio.sleep(0.1)

    upstream_calls = 0

    async def slow_ok():
        nonlocal upstream_calls
        upstream_calls += 1
        # Hold the probe slot long enough that the other concurrent
        # callers race past _before_call while the probe is still running.
        await asyncio.sleep(0.1)
        return "pong"

    results = await asyncio.gather(
        cb.call(slow_ok),
        cb.call(slow_ok),
        cb.call(slow_ok),
        cb.call(slow_ok),
        cb.call(slow_ok),
        return_exceptions=True,
    )

    # EXACTLY one call must have reached the upstream.
    assert upstream_calls == 1, (
        f"Expected exactly 1 upstream call in HALF_OPEN, got {upstream_calls}. "
        "Thundering-herd guard is broken."
    )

    successes = [r for r in results if r == "pong"]
    rejections = [r for r in results if isinstance(r, CircuitBreakerOpenError)]
    assert len(successes) == 1
    assert len(rejections) == 4

    # Probe succeeded -> breaker closes; probe slot is released.
    assert cb.state == CircuitState.CLOSED
    assert cb.snapshot()["probe_in_flight"] is False
