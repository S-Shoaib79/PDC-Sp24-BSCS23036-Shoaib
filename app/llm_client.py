"""
Mock external LLM client.

Stands in for a real LLM provider (OpenAI / Anthropic / etc.) so the
circuit breaker can be demoed without burning real API credits and
without depending on the public internet during grading.

Failure modes are toggled via an in-memory `mode` flag so the demo
script can flip the upstream between healthy / down / slow.
"""

from __future__ import annotations

import asyncio
import random
from typing import Literal

Mode = Literal["healthy", "down", "slow"]


class MockLLMClient:
    def __init__(self) -> None:
        self.mode: Mode = "healthy"
        self.upstream_timeout_s: float = 60.0  # what a "real" outage feels like

    def set_mode(self, mode: Mode) -> None:
        self.mode = mode

    async def complete(self, prompt: str) -> str:
        if self.mode == "down":
            raise ConnectionError("LLM upstream returned 503 Service Unavailable")

        if self.mode == "slow":
            # Simulate a hung connection; in production this would block the
            # worker for a full minute and pile up requests.
            await asyncio.sleep(self.upstream_timeout_s)
            return "(this should never be returned in slow mode)"

        await asyncio.sleep(random.uniform(0.05, 0.15))
        return f"[LLM healthy reply] You asked: {prompt!r}. Here is a thoughtful answer."


llm_client = MockLLMClient()
