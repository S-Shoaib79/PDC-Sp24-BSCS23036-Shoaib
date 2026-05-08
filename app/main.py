"""
StudySync FastAPI app — Part 3 of the PDC Assignment 2.

Implements the Circuit Breaker + Fallback pattern around an external LLM
to fix the Fault Tolerance bug, plus the mandatory X-Student-ID middleware.

Author: Saleha Shoaib (BSCS23036)
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
)
from .llm_client import Mode, llm_client

STUDENT_ID = "BSCS23036"

app = FastAPI(title="StudySync — Resilient Edition", version="1.0.0")

breaker = CircuitBreaker(
    failure_threshold=3,
    recovery_timeout=10.0,
    call_timeout=2.0,
    name="llm",
)


# --------------------------------------------------------------------------- #
# MANDATORY: every response must carry X-Student-ID. Missing this header is an
# automatic zero on Part 3, per the assignment spec.
# --------------------------------------------------------------------------- #
@app.middleware("http")
async def add_student_id_header(request: Request, call_next):
    try:
        response = await call_next(request)
    except Exception:
        # Even if a downstream handler crashes, the rule still applies.
        response = JSONResponse(
            status_code=500, content={"detail": "internal server error"}
        )
    response.headers["X-Student-ID"] = STUDENT_ID
    return response


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class AskRequest(BaseModel):
    prompt: str


class AskResponse(BaseModel):
    answer: str
    source: str  # "llm" | "fallback"
    breaker_state: str


class ModeRequest(BaseModel):
    mode: Mode  # "healthy" | "down" | "slow"


# --------------------------------------------------------------------------- #
# Fallback policy
# --------------------------------------------------------------------------- #
def fallback_answer(prompt: str) -> str:
    """
    Deterministic, cheap response served when the LLM is unavailable.

    In a real product this would be a cached previous answer, a smaller
    local model, or a templated "we are degraded, try again later" message.
    """
    return (
        "Our AI tutor is temporarily unavailable. "
        "Here is a generic study tip while we recover: "
        "break the topic into smaller questions and search your notes first."
    )


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@app.get("/health")
async def health():
    return {"status": "ok", "student_id": STUDENT_ID}


@app.get("/breaker")
async def breaker_status():
    return breaker.snapshot()


@app.post("/admin/llm-mode")
async def set_llm_mode(payload: ModeRequest):
    """Test-only hook to flip the upstream LLM between healthy/down/slow."""
    llm_client.set_mode(payload.mode)
    return {"mode": llm_client.mode}


@app.post("/admin/breaker/reset")
async def reset_breaker():
    breaker.force_reset()
    return breaker.snapshot()


@app.post("/ask", response_model=AskResponse)
async def ask(payload: AskRequest):
    """
    Protected LLM call. The circuit breaker guarantees this endpoint
    never blocks longer than `call_timeout` seconds and degrades to a
    fallback when the upstream is unhealthy.
    """
    try:
        answer = await breaker.call(llm_client.complete, payload.prompt)
        return AskResponse(
            answer=answer, source="llm", breaker_state=breaker.state.value
        )
    except CircuitBreakerOpenError:
        return AskResponse(
            answer=fallback_answer(payload.prompt),
            source="fallback",
            breaker_state=breaker.state.value,
        )
    except (TimeoutError, ConnectionError):
        return AskResponse(
            answer=fallback_answer(payload.prompt),
            source="fallback",
            breaker_state=breaker.state.value,
        )
