"""
Async Circuit Breaker for protecting calls to the external LLM API.

States:
    CLOSED      -> calls flow through normally; failures are counted.
    OPEN        -> calls are short-circuited immediately (fail fast) until
                   the cooldown window elapses.
    HALF_OPEN   -> exactly ONE probe call is in flight; concurrent callers
                   are rejected (treated as OPEN) until the probe finishes.
                   On probe success the breaker closes; on probe failure
                   it re-opens. This prevents a thundering herd from
                   re-killing a recovering upstream.

The breaker is the StudySync answer to Problem 3: instead of every request
blocking for 60s on a dead LLM, we trip the breaker after a few failures
and serve a deterministic fallback. This isolates the fault and keeps the
rest of the app responsive.
"""

from __future__ import annotations

import asyncio
import time
from enum import Enum
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreakerOpenError(Exception):
    """Raised when a call is rejected because the breaker is OPEN."""


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_timeout: float = 10.0,
        call_timeout: float = 2.0,
        name: str = "llm",
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.call_timeout = call_timeout
        self.name = name

        self._state: CircuitState = CircuitState.CLOSED
        self._failure_count: int = 0
        self._opened_at: float = 0.0
        # In HALF_OPEN, only ONE probe call may be in flight at a time.
        # All other concurrent callers are rejected with CircuitBreakerOpenError.
        self._probe_in_flight: bool = False
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        return self._state

    def snapshot(self) -> dict:
        return {
            "name": self.name,
            "state": self._state.value,
            "failure_count": self._failure_count,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout_s": self.recovery_timeout,
            "probe_in_flight": self._probe_in_flight,
            "seconds_until_half_open": max(
                0.0,
                self.recovery_timeout - (time.monotonic() - self._opened_at),
            )
            if self._state == CircuitState.OPEN
            else 0.0,
        }

    async def call(self, func: Callable[..., Awaitable[T]], *args, **kwargs) -> T:
        await self._before_call()
        try:
            result = await asyncio.wait_for(
                func(*args, **kwargs), timeout=self.call_timeout
            )
        except asyncio.TimeoutError as exc:
            await self._on_failure()
            raise TimeoutError(
                f"Upstream '{self.name}' exceeded {self.call_timeout}s"
            ) from exc
        except Exception:
            await self._on_failure()
            raise
        else:
            await self._on_success()
            return result

    async def _before_call(self) -> None:
        async with self._lock:
            if self._state == CircuitState.OPEN:
                if time.monotonic() - self._opened_at >= self.recovery_timeout:
                    # Cooldown elapsed: enter HALF_OPEN and claim the probe slot
                    # for *this* caller. All other concurrent callers will see
                    # _probe_in_flight=True below and be rejected.
                    self._state = CircuitState.HALF_OPEN
                    self._probe_in_flight = True
                    return
                raise CircuitBreakerOpenError(
                    f"Circuit '{self.name}' is OPEN; failing fast"
                )

            if self._state == CircuitState.HALF_OPEN:
                if self._probe_in_flight:
                    # Another caller already owns the single probe slot.
                    # Reject so we don't thunder-herd a recovering upstream.
                    raise CircuitBreakerOpenError(
                        f"Circuit '{self.name}' is HALF_OPEN with probe in "
                        f"flight; failing fast"
                    )
                # No probe in flight (e.g., direct manual transition);
                # claim the slot.
                self._probe_in_flight = True

    async def _on_success(self) -> None:
        async with self._lock:
            self._failure_count = 0
            self._state = CircuitState.CLOSED
            self._probe_in_flight = False

    async def _on_failure(self) -> None:
        async with self._lock:
            self._failure_count += 1
            if (
                self._state == CircuitState.HALF_OPEN
                or self._failure_count >= self.failure_threshold
            ):
                self._state = CircuitState.OPEN
                self._opened_at = time.monotonic()
            # Always release the probe slot on failure: either the breaker is
            # now OPEN (no probes happen there) or we were CLOSED and the slot
            # was already False, so this is a no-op.
            self._probe_in_flight = False

    def force_reset(self) -> None:
        """Test helper: drop all state. Not part of the public runtime path."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._opened_at = 0.0
        self._probe_in_flight = False
