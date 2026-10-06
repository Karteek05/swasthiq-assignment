# AI Transcript

Coding assistant: Claude Code (Claude, Anthropic), used interactively in the IDE.

Note on scope: the backend/frontend skeleton (FastAPI app, React screens,
initial `agent.py`/`state.py`) already existed when this session started, from
earlier work not captured here. What follows is every prompt from the session
that hardened and fixed that skeleton into a working submission - tool-layer
bugs, the agent loop rewrite, frontend wiring, adversarial cases, docs, and
live verification. Screenshots are described in brackets since they can't be
reproduced in a text file. Assistant responses are summarized to one or two
lines per turn; the point of this file is what I asked for and how I steered
it, not a transcript of everything it said back.

---

**Prompt 1** (with the assignment PDF attached):
> I need help with a technical assessment thats due in 3 hours
> Can you look at swastikq-assignment and clinic-agent-assignment and see how far am I
> The task PDF is attached

-> Assistant read the PDF and both directories, reported a gap analysis
(missing tests, fake frontend data, 1/8 adversarial cases, no docs, several
backend bugs), and asked me to pick a priority order via a multiple-choice
question. I picked "recommended order."

**Prompt 2** (after the assistant had fixed backend bugs, added tests, wired
the frontend, written 8 adversarial cases, and drafted README/DECISIONS):
> Now all the tests you did
> What were they?

-> Assistant listed every pytest test file and test name with a one-line
description of what each covers.

**Prompt 3**:
> 2.5 hours to go
> if the LLM pulls through will there be anything left?

-> Assistant gave an honest punch list split into "needs the LLM" vs "doesn't
need the LLM, can do now" vs "needs you (deployment, repo, video, email)."

**Prompt 4**:
> I just changed the API key in .env
> See if that did something

-> Assistant tested the new key directly against the Gemini endpoint,
found a transient 503 then a successful response, reported the key was valid
(different error class than the earlier quota exhaustion).

**Prompt 5**:
> no
> focus on this
> Only if it succeeds will we go there next

-> This corrected the assistant's instinct to parallelize (keep working on
deployment prep while waiting on the live test). I wanted it to stay focused
on the one blocking question - does the agent actually work live - before
doing anything else.

**Prompt 6** (with a screenshot of NVIDIA's build.nvidia.com free API page for
`nemotron-3.5-lightning-30b-a3b`):
> what about this one
> shall we use the new one

-> Assistant evaluated it as a viable OpenAI-compatible alternative, flagged
that tool-calling support should be smoke-tested before trusting it, and
asked me to generate a key.

**Prompt 7** (with a screenshot showing "Billing setup completed" / Gemini API
Paid Tier activated in Google AI Studio):
> Did this

-> Assistant re-tested the existing key - still hit the same free-tier quota
error, diagnosed that the key was probably issued under a different project
than the one billing was just linked to.

**Prompt 8**:
> Try again?

-> Re-tested the same key once more in case of propagation delay - same
error, confirmed it wasn't a timing issue.

**Prompt 9** (after changing `backend/.env`):
> changed
> made a new key

-> Assistant tested the new key - worked cleanly. Ran a real conversation
(`cv_0001`) live end to end, which surfaced a real bug: the agent asked an
unanswerable clarifying question instead of booking decisively, failing the
given baseline test. Fixed the system prompt and re-verified live.

**Prompt 10**:
> its 1:22 PM
> The submission is due 4:01 PM
> I want to finish this by 3:40 PM
> Do you think that full run can be done once to see if everything is ok
> If it is
> Deploying the app and making the repo and video wont take more than an hour for me so

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

**Prompt 11**:
> whats --repeat 3 do?

-> Assistant explained the determinism check `runner.py --repeat 3` performs
and its direct link to the grading rubric's 15% "worst of three runs"
dimension, and flagged the time cost of running it given what was left in
the budget rather than just running it unprompted.

**Prompt 12**:
> So its 1:56 PM
> Say i submit by 3:55 PM
> What all do I have to do and then what can we do if time still is there

-> Assistant produced a concrete, time-estimated punch list split into
"mandatory for submission" and "if time remains," and flagged a deployment
risk proactively (serverless request-timeout limits vs. this agent's 15-60s
per-conversation latency) rather than waiting to be asked.

**Prompt 13**:
> 15 minutes
> Having lunch
> Will be back
> Its 2 PM
> Ill brb

-> Assistant used the gap to prepare this transcript file and deployment
config (`render.yaml`, `backend/Procfile`) so those steps would be ready to
go, rather than idling.

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
