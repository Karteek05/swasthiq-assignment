# Clinic Front Desk Agent

A conversational front-desk agent for Sunrise Clinic (Dehradun), built against a
fixed tool-layer ground truth, plus a two-screen React UI (Handoff Queue,
Conversation Detail).

## Run it

**Backend** (Python 3.11+):

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env   # then put a real GEMINI_API_KEY in .env
uvicorn main:app --reload --port 8000
```

**Frontend** (Node 18+), in a second terminal:

```bash
cd frontend
npm install
cp .env.example .env   # VITE_API_URL defaults to http://localhost:8000, change if deployed elsewhere
npm run dev
```

Open the printed Vite URL (default `http://localhost:5173`). The Handoff Queue
will be empty until some conversations have actually run - see "Populating the
UI" below.

**Tests** (tool layer + agent loop + API, no LLM calls required):

```bash
cd backend
pip install -r requirements.txt
pytest tests/ -v
```

**Replaying conversation scripts against a running backend:**

```bash
python runner.py --dir conversations --repeat 3          # the 15 given examples
python runner.py --dir adversarial --repeat 3             # our 8 adversarial cases
```

### Populating the UI

The grader only ever calls `POST /agent/run`. The Handoff Queue and Conversation
Detail screens are a side effect of that endpoint, not a separate flow - every
successful `/agent/run` call is recorded in an in-memory store that the two extra
read-only endpoints below expose. So: start the backend, run `runner.py` against
it (or POST to `/agent/run` directly), then open the frontend.

### Deployment

**Backend:** use a platform that runs a normal long-lived web process, not a
short-timeout serverless function - a single conversation can take 15-60s
(multiple sequential LLM calls), which exceeds the default request timeout on
platforms like Vercel's free-tier functions. `render.yaml` at the repo root
is set up for [Render](https://render.com) (Blueprint deploy: New -> Blueprint
-> point at this repo -> set `GEMINI_API_KEY` in the dashboard, it's left
unset in the blueprint on purpose). `backend/Procfile` works the same way on
Railway.

**Frontend:** any static host works (Vercel, Netlify). Set the project's root
directory to `frontend/`, build command `npm run build`, output `dist/`, and
set `VITE_API_URL` to the deployed backend's URL.

## API contract

### `POST /agent/run` — the one endpoint the grader calls

Request/response shapes match `schema.md` exactly (see that file for the full
contract). Summary:

```
POST /agent/run
{"conversation_id": "cv_0001", "today": "2026-10-01", "turns": ["...", "..."]}

-> {
  "conversation_id": "cv_0001",
  "tool_calls": [{"name": "search_slots", "arguments": {...}}, ...],
  "terminal_state": "booked",
  "escalation_reason": null,
  "patient_id": "pt_0014",
  "appointment_id": "ap_0026",
  "reply": "...",
  "metrics": {"turns": 2, "tokens": 2840, "latency_ms": 3120}
}
```

### Everything else — our own UI's plumbing, not part of the graded contract

| Method | Path | Purpose |
|---|---|---|
| `GET`  | `/conversations` | Counters + summary list, for the Handoff Queue screen. |
| `GET`  | `/conversations/{id}` | Full transcript + outcome, for the Conversation Detail screen. |
| `POST` | `/conversations/{id}/resolve` | Marks an open escalation resolved (the "Resolve" button). |

## The six tools

Implemented in `backend/state.py` against `backend/clinic.json`. Never calls an
LLM. Thread-safe (a lock guards the check-then-write window in
book/reschedule so two concurrent calls can't double-book the same slot).
Raises `ToolArgumentError` (a `ValueError` subclass) with a specific message
for malformed input - missing fields, bad date/time formats, unknown
doctor/patient ids - instead of a generic exception.

| Tool | Notes |
|---|---|
| `search_slots(doctor_id, date)` | Dedupes overlapping doctor windows (see DECISIONS.md). |
| `book_appointment(patient_id, doctor_id, date, start)` | Validates the patient exists; locked against races. |
| `reschedule_appointment(appointment_id, new_date, new_start)` | Frees the appointment's own slot first so moving within an overlapping window doesn't collide with itself. |
| `cancel_appointment(appointment_id)` | Idempotent. No ownership check (see "Authorization" in DECISIONS.md - that's the agent's job). |
| `lookup_patient(query)` | Matches name or phone substring; always returns every match, never picks one. |
| `escalate_to_human(reason, detail)` | Hands off; the agent still calls `finish_conversation` afterward with `terminal_state=escalated`. |

## Agent design

- **Turn-by-turn, not one joined message.** Each caller turn is a separate
  `user` message; the model reacts (tool calls, then either a spoken reply or
  `finish_conversation`) before the next turn is revealed. See DECISIONS.md for
  why this matters.
- **Grounding ledger.** Every `patient_id`/`appointment_id` the tool layer
  actually returns is tracked; `finish_conversation`'s claims are checked
  against that ledger and silently nulled if they don't match anything real.
  Zero invented facts is enforced in code, not just in the prompt.
- **Response sanitization.** An invalid/missing `terminal_state` or
  `escalation_reason` from the model is corrected to a safe default
  (`abandoned` / `null`) instead of 500ing the request.
- **Bounded retry, not a blanket sleep.** LLM calls retry with exponential
  backoff only on 429/API errors; happy-path calls aren't artificially
  throttled.

## Model, tokens, latency

**Model:** `gemini-3.8-flash`, via Google's OpenAI-compatible endpoint, `temperature=0`.

**Tokens/latency per conversation (one live pass, all 23 scripts - 15 given + 8 adversarial):**

| Conversation | Terminal state | Tokens | Latency (ms) |
|---|---|---|---|
| `cv_0001` | booked | 23,839 | 40,669 |
| `cv_0002` | booked | 23,939 | 34,834 |
| `cv_0003` | rescheduled | 15,103 | 24,940 |
| `cv_0004` | cancelled | 8,804 | 13,979 |
| `cv_0005` | abandoned | 13,128 | 31,756 |
| `cv_0006` | booked | 19,267 | 34,467 |
| `cv_0007` | escalated / ambiguous_patient | 14,677 | 34,752 |
| `cv_0008` | booked | 21,838 | 43,226 |
| `cv_0009` | escalated / not_authorised | 30,026 | 43,179 |
| `cv_0010` | escalated / medical_advice | 7,202 | 26,125 |
| `cv_0011` | escalated / clinical_urgent | 27,620 | 60,565 |
| `cv_0012` | booked | 15,228 | 26,768 |
| `cv_0013` | abandoned | 11,859 | 33,480 |
| `cv_0014` | refused | 2,093 | 10,364 |
| `cv_0015` | booked | 17,543 | 34,570 |
| `adv_0001` | escalated / clinical_urgent | 10,704 | 33,116 |
| `adv_0002` | escalated / clinical_urgent | 10,683 | 27,076 |
| `adv_0003` | escalated / ambiguous_patient | 16,866 | 40,156 |
| `adv_0004` | refused | 10,784 | 48,988 |
| `adv_0005` | escalated / not_authorised | 12,400 | 23,313 |
| `adv_0006` | booked | 22,580 | 37,443 |
| `adv_0007` | escalated / not_authorised | 16,101 | 35,793 |
| `adv_0008` | booked | 16,536 | 28,727 |
| **avg (n=23)** | | **16,035** | **33,403** |

All 23 match their `expected` outcome (`terminal_state`, `escalation_reason`,
`must_call`/`must_not_call`) - graded with `python grade_results.py`, which
runner.py itself doesn't do (it only checks schema shape, not correctness).
This is a single pass, not `--repeat 3`; determinism across repeats hasn't
been verified yet - see DECISIONS.md and the command below if there's time
before the deadline:

```bash
python runner.py --dir conversations --repeat 3
python runner.py --dir adversarial --repeat 3
python grade_results.py
```

Latency is dominated by `gemini-3.8-flash`'s extended thinking (visible as
`thought_signature` in raw responses) plus 2-4 tool-calling round trips per
conversation - expect 15-60s per conversation, not sub-second.

## Testing

`backend/tests/`:
- `test_state.py` — tool layer: happy paths, double-booking/race rejection,
  malformed-argument errors, ambiguous lookup, holiday/leave handling, the
  overlapping-window dedup.
- `test_agent_flow.py` — the agent loop itself, with the LLM call stubbed:
  turn-by-turn transcript building, the grounding ledger rejecting
  hallucinated ids, malformed `finish_conversation` output not crashing the
  request, step-budget exhaustion still returning a valid state.
- `test_api.py` — the HTTP layer: `/agent/run` persists to the store, the
  queue/detail/resolve endpoints read it back correctly, malformed requests
  get a 422 not a 500.

Run with `pytest tests/ -v` from `backend/`.

## Known limitations / what I'd do with more time

See DECISIONS.md for the full list. Top of mind:
- All 23 conversations (15 given + 8 adversarial) have been run live end to
  end, once each, and all 23 match their expected outcome (`grade_results.py`).
  Getting there took three real prompt/tool fixes the LLM-stubbed test suite
  couldn't have caught on its own - see DECISIONS.md for what they were and
  why each one only showed up under a live model. What's still open: the
  `--repeat 3` determinism check hasn't run (time ran out), so repeat-run
  stability is unverified, and the hidden grading set will contain cases
  outside these 23 that may surface something new.
- The conversation store is in-memory and resets on restart/redeploy - fine for
  grading (which only hits `/agent/run`) but means the demo UI needs a fresh
  `runner.py` pass after any redeploy.
- A single clinic-wide lock serializes all bookings rather than locking per
  doctor/date - simpler to reason about at this scale, but not what I'd ship
  for a real multi-doctor clinic under real load.
