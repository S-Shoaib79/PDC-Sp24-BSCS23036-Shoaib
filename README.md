Saleha Shoaib — BSCS23036

# StudySync — Resilient Edition (PDC Assignment 2)

This repo is the Part 3 deliverable for the PDC Assignment 2 ("Building Resilient
Distributed Systems"). It implements the **Circuit Breaker + Fallback** pattern
around an external LLM call inside a FastAPI backend, fixing the Fault Tolerance
bug described in the spec (a 60-second LLM hang taking down the whole server).

## What is implemented

- `app/circuit_breaker.py` — async `CircuitBreaker` with `CLOSED → OPEN → HALF_OPEN`
  state machine, configurable failure threshold, per-call timeout, and recovery
  cooldown.
- `app/llm_client.py` — mock external LLM client with three modes: `healthy`,
  `down`, `slow` (the `slow` mode reproduces the 60-second hang from the spec).
- `app/main.py` — FastAPI app exposing `/ask` (protected by the breaker, falls
  back gracefully on failure), plus admin endpoints to flip the upstream mode
  and inspect breaker state.
- `tests/test_circuit_breaker.py` — pytest suite that *triggers* the failure
  state and proves the fix:
  - request does not block on a slow upstream,
  - breaker opens after N consecutive failures,
  - OPEN breaker rejects in <1 ms (no upstream call),
  - HALF_OPEN probe closes the breaker on success,
  - failed HALF_OPEN probe re-opens it,
  - HALF_OPEN admits exactly one concurrent probe (no thundering herd).
- `demo.py` — script for the 2-minute screen recording that walks through the
  before / after states.

## How to run (Windows CMD)

All commands below assume you are using **Windows CMD** (`cmd.exe`). For
PowerShell, the only differences are `activate.bat` → `Activate.ps1` and
`set VAR=value` → `$env:VAR = "value"`.

### 1. Install

```cmd
cd /d D:\path\to\PDC-Sp24-BSCS23036-Shoaib
python -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt
```

After `activate.bat`, your prompt should show `(.venv)` at the front. macOS /
Linux users: replace step 2 with `source .venv/bin/activate`.

### 2. Run the tests (proves the fix works)

```cmd
pytest -v
```

All six tests should pass. The first test confirms the `X-Student-ID` header
is present on every endpoint.

### 3. Run the API

```cmd
uvicorn app.main:app --reload --port 8000
```

Leave that window running. In a **second CMD window** (also with the venv
activated), check the mandatory header:

```cmd
curl http://127.0.0.1:8000/health -i
```

Look for the line `X-Student-ID: BSCS23036` in the response headers.

### 4. Run the demo script (in the second terminal)

```cmd
python demo.py
```

You will see:

1. A healthy `/ask` call returning an LLM answer in ~100 ms.
2. The upstream flipped to `down`; `/ask` now returns a fallback answer almost
   instantly (no 60-second wait).
3. After 3 failures the breaker is `OPEN` and rejects further calls in
   sub-millisecond time.
4. After the 10-second cooldown, the breaker probes upstream, sees it healthy,
   and closes again — traffic returns to normal.

If you ran the API on a port other than 8000, point the demo at it via
`STUDYSYNC_BASE`:

```cmd
set STUDYSYNC_BASE=http://127.0.0.1:8765
python demo.py
```

### Manually toggling failure modes

In CMD, JSON bodies for `curl` use double-quoted strings with `\"` for the
inner quotes:

```cmd
:: Take the LLM down
curl -X POST http://127.0.0.1:8000/admin/llm-mode -H "Content-Type: application/json" -d "{\"mode\":\"down\"}"

:: Bring it back
curl -X POST http://127.0.0.1:8000/admin/llm-mode -H "Content-Type: application/json" -d "{\"mode\":\"healthy\"}"

:: Inspect breaker state
curl http://127.0.0.1:8000/breaker

:: Reset the breaker (test helper)
curl -X POST http://127.0.0.1:8000/admin/breaker/reset
```

## Repository layout

```
PDC-Sp24-BSCS23036-Shoaib/
├── app/
│   ├── circuit_breaker.py     # the pattern itself
│   ├── llm_client.py          # mock external LLM
│   └── main.py                # FastAPI app + X-Student-ID middleware
├── tests/
│   └── test_circuit_breaker.py
├── demo.py                    # for the 2-minute screen recording
├── requirements.txt
└── README.md
```

