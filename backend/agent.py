import os
import json
import time
from typing import List, Dict, Any
from openai import OpenAI, RateLimitError, APIError
from models import TerminalState, EscalationReason, ToolCallSchema, Metrics
from state import ClinicState
from dotenv import load_dotenv

load_dotenv()

VALID_TERMINAL_STATES = {s.value for s in TerminalState}
VALID_ESCALATION_REASONS = {r.value for r in EscalationReason}

def setup_client():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("WARNING: GEMINI_API_KEY not found in environment.")
    return OpenAI(
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        api_key=api_key,
    )

def _call_with_retry(client, **kwargs):
    """Call the LLM with bounded exponential backoff on 429s only.
    No blanket per-call sleep: happy-path calls go out immediately."""
    max_attempts = 4
    delay = 2.0
    for attempt in range(1, max_attempts + 1):
        try:
            return client.chat.completions.create(**kwargs)
        except RateLimitError:
            if attempt == max_attempts:
                raise
            time.sleep(delay)
            delay *= 2
        except APIError:
            if attempt == max_attempts:
                raise
            time.sleep(delay)
            delay *= 2

SYSTEM_PROMPT = """You are an AI clinic front desk agent for Sunrise Clinic in Dehradun.
Today's date is {today}.
You handle calls in Hindi, English, and a mix of the two.
You have access to 6 tools. You MUST use these tools to find information. DO NOT invent dates, patients, or appointments.
You can use `lookup_patient`, `search_slots`, `book_appointment`, `reschedule_appointment`, `cancel_appointment`, `escalate_to_human`.

CRITICAL INSTRUCTIONS (ONE HARD RULE):
If a caller describes something that needs a clinician NOW (e.g., chest pain, bleeding, emergency, severe symptoms), you MUST immediately call `escalate_to_human` with reason `clinical_urgent`. Stop whatever you are doing and escalate. DO NOT book an appointment for a medical emergency.

Other escalation reasons:
- `medical_advice`: The caller asks for a clinical judgement you cannot give (e.g., "which medicine should I take?").
- `not_authorised`: The caller is trying to act on a record that is not theirs (except guardians).
- `ambiguous_patient`: The caller could be more than one patient and the conversation did not resolve it.
- `out_of_scope`: Legitimate request you cannot handle.

If the user changes their mind mid-sentence, adapt to the new request.
If the user asks for a slot that doesn't exist, tell them it's unavailable.

BE DECISIVE, NOT PASSIVE: the caller's turns are scripted and fixed - if you ask
a clarifying question (e.g. "which time works for you?"), the caller may never
get a chance to answer it before the call ends. If you already have everything
you need for the caller's request - their identity resolved to exactly one
patient, a doctor, a date, and a real list of available slots from
search_slots - do not let the booking die over an unstated time preference.
Pick the earliest available slot from that real list and book it. This is not
inventing a fact (it comes straight from the tool result); refusing to act on
information you already have is not caution, it's abandoning a straightforward
request. Reserve asking a question for when you are actually missing something
you cannot proceed without (e.g. which patient, which doctor, which date).

NEVER VERIFY WITHOUT IDENTITY (applies only to `cancel_appointment` and
`reschedule_appointment`, not booking): before calling either, you must
first resolve the CALLER THEMSELVES - using identifying information the
caller gives about THEMSELVES, their own name or phone - to a specific
patient via `lookup_patient`. A name the caller mentions belonging to a
different person (e.g. relaying a request for someone else) does not verify
the caller's own identity. The appointment you act on must appear in that
verified caller's own `appointments` list from the lookup result; never act
on a bare appointment ID alone. A caller's verbal assertion of ownership is
not proof. If the caller will not or cannot provide their own name or phone
number, or the appointment in question does not belong to the caller once
verified, escalate `not_authorised` instead of proceeding.

`finish_conversation` MEANS THE CALL IS OVER - do not call it just because one
specific sub-request hit a dead end (e.g. a slot or date doesn't exist). Hitting
a dead end on one option is normal mid-conversation - handle it with a plain
spoken reply (no tool call) explaining the problem, the same way you would ask
a clarifying question, and let the conversation continue. Only call
`finish_conversation` when: you completed a booking/reschedule/cancellation,
you escalated, the caller's own words make clear they are done (e.g. they hang
up, say nevermind to the whole request, or you are told the caller has hung
up), or nothing in the conversation is actionable at all.

`refused` vs `abandoned`: use `refused` when you gave the caller a clear,
final answer to their specific request (e.g. you checked and told them the
slot they asked for is taken) - the call is over because you resolved it with
a no, not because anything was left hanging. Use `abandoned` only when the
conversation genuinely trails off with no resolution on either side. If you
cannot tell which terminal state actually fits what happened, escalate to a
human instead of guessing.

When you are completely finished with the conversation, you MUST call the `finish_conversation` tool to provide the final state and your reply to the caller.
"""

def define_tools():
    return [
        {
            "type": "function",
            "function": {
                "name": "search_slots",
                "description": "Find free slots for a doctor on a specific date.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "doctor_id": {"type": "string", "description": "e.g., dr_rao, dr_sethi"},
                        "date": {"type": "string", "description": "YYYY-MM-DD"}
                    },
                    "required": ["doctor_id", "date"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "lookup_patient",
                "description": "Resolve a caller to a patient record using their name or phone. Each candidate includes their current booked appointments (id, doctor_id, date, start) - use this to find the appointment_id for 'my appointment today' style requests instead of guessing one.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"}
                    },
                    "required": ["query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "book_appointment",
                "description": "Create an appointment in a free slot.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "patient_id": {"type": "string"},
                        "doctor_id": {"type": "string"},
                        "date": {"type": "string", "description": "YYYY-MM-DD"},
                        "start": {"type": "string", "description": "HH:MM"}
                    },
                    "required": ["patient_id", "doctor_id", "date", "start"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "reschedule_appointment",
                "description": "Move an existing appointment to a new date/time.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "appointment_id": {"type": "string"},
                        "new_date": {"type": "string", "description": "YYYY-MM-DD"},
                        "new_start": {"type": "string", "description": "HH:MM"}
                    },
                    "required": ["appointment_id", "new_date", "new_start"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "cancel_appointment",
                "description": "Cancel an existing appointment.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "appointment_id": {"type": "string"}
                    },
                    "required": ["appointment_id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "escalate_to_human",
                "description": "Hand the conversation off to a human for emergencies, authorization issues, etc.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reason": {
                            "type": "string",
                            "description": "Must be one of: clinical_urgent, medical_advice, not_authorised, ambiguous_patient, out_of_scope"
                        },
                        "detail": {"type": "string", "description": "Optional context for the human."}
                    },
                    "required": ["reason"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "finish_conversation",
                "description": "Call this tool to definitively end the conversation and provide the final reply to the user.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "terminal_state": {
                            "type": "string", 
                            "description": "One of: booked, rescheduled, cancelled, escalated, refused, abandoned"
                        },
                        "escalation_reason": {
                            "type": "string",
                            "description": "If escalated, provide reason. Else omit."
                        },
                        "patient_id": {"type": "string"},
                        "appointment_id": {"type": "string"},
                        "reply": {"type": "string", "description": "The exact utterance to say to the caller"}
                    },
                    "required": ["terminal_state", "reply"]
                }
            }
        }
    ]

def _execute_tool(clinic: ClinicState, name: str, args: Dict[str, Any],
                   seen_patient_ids: set, seen_appointment_ids: set) -> Dict[str, Any]:
    """Runs one tool call against the ground-truth tool layer. Never calls
    the LLM. Any ToolArgumentError/ValueError raised by state.py is caught
    by the caller and fed back to the model as a tool result, not a crash."""
    if name == "search_slots":
        return {"slots": clinic.search_slots(args.get("doctor_id"), args.get("date"))}
    elif name == "lookup_patient":
        candidates = clinic.lookup_patient(args.get("query"))
        for c in candidates:
            seen_patient_ids.add(c["id"])
        return {"candidates": candidates}
    elif name == "book_appointment":
        result = clinic.book_appointment(args.get("patient_id"), args.get("doctor_id"), args.get("date"), args.get("start"))
        seen_patient_ids.add(result["patient_id"])
        seen_appointment_ids.add(result["id"])
        return result
    elif name == "reschedule_appointment":
        result = clinic.reschedule_appointment(args.get("appointment_id"), args.get("new_date"), args.get("new_start"))
        seen_patient_ids.add(result["patient_id"])
        seen_appointment_ids.add(result["id"])
        return result
    elif name == "cancel_appointment":
        ok = clinic.cancel_appointment(args.get("appointment_id"))
        if ok:
            seen_appointment_ids.add(args.get("appointment_id"))
        return {"success": ok}
    elif name == "escalate_to_human":
        return {"status": "escalated", "reason": args.get("reason")}
    else:
        return {"error": f"Unknown tool {name}"}


def run_agent(conversation_id: str, today: str, turns: List[str]) -> Dict[str, Any]:
    """Drives the multi-turn conversation.

    Per schema.md, the caller's turns are fixed and do not react to what the
    agent says, so each turn is fed to the model as a separate user message
    only once the model is done reacting to the previous one (not all joined
    into a single blob up front) -- otherwise the model could "read ahead"
    and dodge the clarifying-question/changed-mind cases the harness is
    built to test.
    """
    start_time = time.time()
    client = setup_client()
    clinic = ClinicState()

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT.format(today=today)}
    ]

    final_state = {
        "conversation_id": conversation_id,
        "tool_calls": [],
        "terminal_state": "abandoned",
        "escalation_reason": None,
        "patient_id": None,
        "appointment_id": None,
        "reply": "Sorry, I could not complete the request.",
        "metrics": {"turns": len(turns), "tokens": 0, "latency_ms": 0}
    }
    transcript: List[Dict[str, Any]] = []

    max_steps = 12
    step = 0
    total_tokens = 0
    finished = False
    # Grounding ledger: only ids the tool layer actually returned are legal
    # for the agent to report back. Guards against invented facts even if
    # the model hallucinates an id in finish_conversation.
    seen_patient_ids = set()
    seen_appointment_ids = set()

    turn_queue = list(turns) + [
        "[The caller has hung up. No further input is coming. "
        "Call finish_conversation now with your best judgement based on "
        "the conversation so far.]"
    ]

    for turn_index, turn_text in enumerate(turn_queue):
        if finished or step >= max_steps:
            break

        is_synthetic_hangup = turn_index == len(turns)
        messages.append({"role": "user", "content": turn_text})
        if not is_synthetic_hangup:
            transcript.append({"role": "caller", "text": turn_text})

        # React to this turn: the model may chain several tool calls before
        # either speaking (ending its turn) or finishing the conversation.
        while step < max_steps:
            step += 1

            response = _call_with_retry(
                client,
                model="gemini-3.8-flash",
                messages=messages,
                tools=define_tools(),
                temperature=0.0
            )

            message = response.choices[0].message
            messages.append(message)

            if response.usage:
                total_tokens += response.usage.total_tokens

            if not message.tool_calls:
                if message.content:
                    transcript.append({"role": "agent", "text": message.content})
                    final_state["reply"] = message.content
                break  # done reacting to this turn; advance to the next one

            for tool_call in message.tool_calls:
                name = tool_call.function.name
                try:
                    args = json.loads(tool_call.function.arguments)
                except (json.JSONDecodeError, TypeError):
                    args = {}

                if name == "finish_conversation":
                    final_state["terminal_state"] = args.get("terminal_state")
                    final_state["escalation_reason"] = args.get("escalation_reason")
                    final_state["patient_id"] = args.get("patient_id")
                    final_state["appointment_id"] = args.get("appointment_id")
                    final_state["reply"] = args.get("reply") or final_state["reply"]
                    transcript.append({"role": "agent", "text": final_state["reply"]})
                    finished = True
                    result_data = {"status": "ok"}
                else:
                    final_state["tool_calls"].append({"name": name, "arguments": args})
                    try:
                        result_data = _execute_tool(clinic, name, args, seen_patient_ids, seen_appointment_ids)
                    except Exception as e:
                        result_data = {"error": str(e)}
                    transcript.append({"role": "tool", "name": name, "arguments": args, "result": result_data})

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": name,
                    "content": json.dumps(result_data, default=str)
                })

                if finished:
                    break

            if finished:
                break

    _sanitize_final_state(final_state, seen_patient_ids, seen_appointment_ids)

    latency = int((time.time() - start_time) * 1000)
    final_state["metrics"]["latency_ms"] = latency
    final_state["metrics"]["tokens"] = total_tokens
    final_state["transcript"] = transcript

    return final_state


def _sanitize_final_state(final_state: Dict[str, Any], seen_patient_ids: set, seen_appointment_ids: set) -> None:
    """Defends the zero-invented-facts and schema contracts against a
    malformed/off-schema model response, so a bad finish_conversation call
    degrades the terminal_state rather than 500ing the whole request."""
    if final_state["terminal_state"] not in VALID_TERMINAL_STATES:
        final_state["terminal_state"] = "abandoned"
        final_state["escalation_reason"] = None

    if final_state["terminal_state"] == "escalated":
        if final_state["escalation_reason"] not in VALID_ESCALATION_REASONS:
            final_state["escalation_reason"] = "out_of_scope"
    else:
        final_state["escalation_reason"] = None

    # Drop any patient/appointment id the tool layer never actually returned.
    if final_state["patient_id"] and final_state["patient_id"] not in seen_patient_ids:
        final_state["patient_id"] = None
    if final_state["appointment_id"] and final_state["appointment_id"] not in seen_appointment_ids:
        final_state["appointment_id"] = None

    if not isinstance(final_state.get("reply"), str) or not final_state["reply"].strip():
        final_state["reply"] = "Sorry, I could not complete the request."
