# AI Transcript

Coding assistant: Claude Code (Claude, Anthropic), used interactively in the IDE.

Note on scope: the backend/frontend skeleton (FastAPI app, React screens,
initial `agent.py`/`state.py`) already existed when this session started, from
earlier work not captured here. What follows is a paraphrased summary of the
session that hardened and fixed that skeleton into a working submission -
tool-layer bugs, the agent loop rewrite, frontend wiring, adversarial cases,
docs, and live verification. Screenshots are described in brackets since they
can't be reproduced in a text file. Each entry summarizes what I asked for and
how I steered the work, not a verbatim transcript.

---

**1. Initial gap analysis** (assignment PDF attached):
Asked the assistant to review both candidate directories against the task
PDF and assess progress under a tight deadline.

-> Assistant read the PDF and both directories, reported a gap analysis
(missing tests, fake frontend data, 1/8 adversarial cases, no docs, several
backend bugs), and proposed a priority order, which I confirmed.

**2. Test coverage review** (after the assistant had fixed backend bugs,
added tests, wired the frontend, written 8 adversarial cases, and drafted
README/DECISIONS):
Asked for a rundown of everything covered by the new tests.

-> Assistant listed every pytest test file and test name with a one-line
description of what each covers.

**3. Time-boxed scope check:**
Partway through the session, asked what would still be outstanding once
live LLM verification was complete.

-> Assistant gave an honest punch list split into "needs the LLM" vs "doesn't
need the LLM, can do now" vs "needs you (deployment, repo, video, email)."

**4. API key validation:**
Rotated the Gemini API key in `.env` and asked the assistant to confirm it
worked.

-> Assistant tested the new key directly against the Gemini endpoint,
found a transient 503 then a successful response, reported the key was valid
(different error class than the earlier quota exhaustion).

**5. Scope correction:**
Redirected the assistant away from parallelizing deployment prep while the
live-model question was still open, to keep focus on the one blocking
question - does the agent actually work live - before anything else.

-> Assistant dropped the deployment-prep thread and stayed on live
verification until it either passed or failed.

**6. Alternative model evaluation** (screenshot of NVIDIA's
build.nvidia.com free API page for `nemotron-3.5-lightning-30b-a3b`):
Asked whether this model should replace the current one.

-> Assistant evaluated it as a viable OpenAI-compatible alternative, flagged
that tool-calling support should be smoke-tested before trusting it, and
asked me to generate a key.

**7. Billing follow-up** (screenshot showing "Billing setup completed" /
Gemini API Paid Tier activated in Google AI Studio):
Confirmed billing was set up and asked the assistant to re-check.

-> Assistant re-tested the existing key - still hit the same free-tier quota
error, diagnosed that the key was probably issued under a different project
than the one billing was just linked to.

**8. Retest after propagation delay:**
Asked the assistant to try the key again in case the billing change hadn't
propagated yet.

-> Re-tested the same key once more - same error, confirmed it wasn't a
timing issue.

**9. New key, live verification** (after changing `backend/.env`):
Provided a freshly generated key and asked the assistant to verify it.

-> Assistant tested the new key - worked cleanly. Ran a real conversation
(`cv_0001`) live end to end, which surfaced a real bug: the agent asked an
unanswerable clarifying question instead of booking decisively, failing the
given baseline test. Fixed the system prompt and re-verified live.

**10. Full live run, go/no-go call:**
With a submission deadline approaching, asked whether a full run across all
scripts could confirm everything was in order before moving on to
deployment, repo cleanup, video, and the submission email.

-> This set the actual time budget and asked for a go/no-go judgment call,
not just information. Assistant ran all 23 conversation scripts (15 given +
8 adversarial) live, once each, against the real model. Found and fixed three
more real bugs this surfaced (an authorization bypass on cancel without
identity verification, the agent ending conversations prematurely on a dead
end instead of continuing, and a genuine tool-design gap - no way to look up
"my appointment today" without an appointment ID). Re-ran the failures after
each fix. Ended at 23/23 passing against their own `expected` fields, graded
with a small script written for this purpose (`grade_results.py`, since
`runner.py` only checks schema shape, not correctness).

**11. Clarifying the determinism check:**
Asked what `runner.py --repeat 3` actually does.

-> Assistant explained the determinism check `runner.py --repeat 3` performs
and its direct link to the grading rubric's 15% "worst of three runs"
dimension, and flagged the time cost of running it given what was left in
the budget rather than just running it unprompted.

**12. Submission punch list:**
Asked for a complete breakdown of what was mandatory before submission
versus what could be done with any remaining time.

-> Assistant produced a concrete, time-estimated punch list split into
"mandatory for submission" and "if time remains," and flagged a deployment
risk proactively (serverless request-timeout limits vs. this agent's 15-60s
per-conversation latency) rather than waiting to be asked. Also prepared
deployment config (`render.yaml`, `backend/Procfile`) ahead of time so those
steps were ready to go.

---

## What I was deliberate about, across the session

- **Didn't let it guess silently.** When it found something ambiguous or
  wrong in the provided materials (overlapping doctor windows in
  `clinic.json`, no tool to look up a patient's existing appointments), I
  wanted that written down with reasoning, not quietly patched - that's why
  `DECISIONS.md` exists and is as long as it is.
- **Made it verify against the real model before trusting anything.** The
  agent loop had 25 passing tests before a single live API call was made -
  all of them against a stubbed LLM. Three of the four real bugs found in
  this session only showed up once it actually talked to Gemini. I pushed
  for live verification specifically because I didn't trust the stubbed
  suite to be sufficient, and that judgment turned out to be correct.
- **Kept it honest about what wasn't done.** At several points the easy
  answer would have been to report things as more complete than they were
  (fabricated token/latency numbers while the API key was quota-exhausted,
  claiming full `--repeat 3` coverage after only a single pass). I didn't
  ask for this explicitly, but corrected course whenever it over-claimed and
  it adjusted README/DECISIONS to the honest state each time.
