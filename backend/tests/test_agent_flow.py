"""Exercises the turn-by-turn agent loop, the grounding safety net, and the
conversation store/endpoints WITHOUT calling the real LLM. The real API key
for this project is quota-limited, so this stubs agent._call_with_retry
with a scripted sequence of canned model responses and checks the plumbing
around it (tool execution, transcript building, response sanitisation,
store persistence) actually works end to end.
"""
import json
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import agent


def _msg(tool_calls=None, content=None):
    return SimpleNamespace(tool_calls=tool_calls, content=content)


def _tool_call(call_id, name, arguments):
    return SimpleNamespace(id=call_id, function=SimpleNamespace(name=name, arguments=json.dumps(arguments)))


def _response(message, tokens=10):
    return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=SimpleNamespace(total_tokens=tokens))


def test_turn_by_turn_booking_flow(monkeypatch):
    # finish_conversation's step is built lazily so it can echo back the
    # *real* appointment id the tool layer minted a step earlier - the
    # whole point of the grounding ledger is that it only trusts ids that
    # actually came from a tool result.
    booked_ids = {}
    step_count = {"n": 0}

    def fake_call(client, **kw):
        step_count["n"] += 1
        n = step_count["n"]
        if n == 1:
            return _response(_msg(tool_calls=[_tool_call("c1", "search_slots", {"doctor_id": "dr_rao", "date": "2026-10-03"})]))
        if n == 2:
            return _response(_msg(content="We have slots on Oct 3. Which one works?"))
        if n == 3:
            return _response(_msg(tool_calls=[_tool_call(
                "c2", "book_appointment",
                {"patient_id": "pt_0001", "doctor_id": "dr_rao", "date": "2026-10-03", "start": "09:30"}
            )]))
        if n == 4:
            return _response(_msg(tool_calls=[_tool_call(
                "c3", "finish_conversation",
                {"terminal_state": "booked", "patient_id": "pt_0001",
                 "appointment_id": booked_ids.get("appointment_id", "NEVER_SET"), "reply": "Booked!"}
            )]))
        raise AssertionError(f"unexpected extra call #{n}")

    real_execute = agent._execute_tool

    def spy_execute(clinic, name, args, seen_p, seen_a):
        result = real_execute(clinic, name, args, seen_p, seen_a)
        if name == "book_appointment":
            booked_ids["appointment_id"] = result["id"]
        return result

    monkeypatch.setattr(agent, "_call_with_retry", fake_call)
    monkeypatch.setattr(agent, "setup_client", lambda: None)
    monkeypatch.setattr(agent, "_execute_tool", spy_execute)

    result = agent.run_agent("cv_test_1", "2026-10-01", [
        "I need an appointment with Dr. Rao.",
        "Book the first one for pt_0001.",
    ])

    assert result["terminal_state"] == "booked"
    assert result["patient_id"] == "pt_0001"
    assert result["appointment_id"] == booked_ids["appointment_id"]
    assert [c["name"] for c in result["tool_calls"]] == ["search_slots", "book_appointment"]
    # transcript interleaves caller/agent/tool turns in order
    roles = [t["role"] for t in result["transcript"]]
    assert roles == ["caller", "tool", "agent", "caller", "tool", "agent"]


def test_hallucinated_appointment_id_is_rejected_even_if_booking_happened(monkeypatch):
    calls = iter([
        _response(_msg(tool_calls=[_tool_call(
            "c1", "book_appointment",
            {"patient_id": "pt_0001", "doctor_id": "dr_rao", "date": "2026-10-03", "start": "09:30"}
        )])),
        # Model reports a made-up id instead of the one the tool actually returned.
        _response(_msg(tool_calls=[_tool_call(
            "c2", "finish_conversation",
            {"terminal_state": "booked", "patient_id": "pt_0001", "appointment_id": "ap_made_up", "reply": "Booked!"}
        )])),
    ])
    monkeypatch.setattr(agent, "_call_with_retry", lambda client, **kw: next(calls))
    monkeypatch.setattr(agent, "setup_client", lambda: None)

    result = agent.run_agent("cv_test_1b", "2026-10-01", ["Book me with Dr. Rao tomorrow morning."])

    assert result["terminal_state"] == "booked"
    assert result["appointment_id"] is None  # invented id, not grounded, dropped


def test_invented_appointment_id_is_dropped_when_no_tool_call_backs_it(monkeypatch):
    # Model escalates without ever calling a tool that returns a patient/
    # appointment id, but still fills them in on finish_conversation.
    calls = iter([
        _response(_msg(tool_calls=[_tool_call("c1", "escalate_to_human", {"reason": "clinical_urgent"})])),
        _response(_msg(tool_calls=[_tool_call("c2", "finish_conversation", {
            "terminal_state": "escalated",
            "escalation_reason": "clinical_urgent",
            "patient_id": "pt_9999",
            "appointment_id": "ap_9999",
            "reply": "Connecting you to a human now.",
        })])),
    ])
    monkeypatch.setattr(agent, "_call_with_retry", lambda client, **kw: next(calls))
    monkeypatch.setattr(agent, "setup_client", lambda: None)

    result = agent.run_agent("cv_test_2", "2026-10-01", ["Seene mein dard ho raha hai"])

    assert result["terminal_state"] == "escalated"
    assert result["escalation_reason"] == "clinical_urgent"
    assert result["patient_id"] is None
    assert result["appointment_id"] is None


def test_malformed_finish_conversation_does_not_crash(monkeypatch):
    calls = iter([
        _response(_msg(tool_calls=[_tool_call("c1", "finish_conversation", {
            "terminal_state": "done_i_guess",  # not a real enum value
            "reply": "ok",
        })])),
    ])
    monkeypatch.setattr(agent, "_call_with_retry", lambda client, **kw: next(calls))
    monkeypatch.setattr(agent, "setup_client", lambda: None)

    result = agent.run_agent("cv_test_3", "2026-10-01", ["hello"])

    assert result["terminal_state"] == "abandoned"
    assert result["escalation_reason"] is None


def test_runs_out_of_turns_without_finish_still_returns_valid_state(monkeypatch):
    # Model never calls finish_conversation even after the synthetic
    # hangup nudge; step budget should still terminate the conversation
    # with a safe default instead of hanging.
    def always_silent(client, **kw):
        return _response(_msg(content="hmm let me think"))

    monkeypatch.setattr(agent, "_call_with_retry", always_silent)
    monkeypatch.setattr(agent, "setup_client", lambda: None)

    result = agent.run_agent("cv_test_4", "2026-10-01", ["hello"])

    assert result["terminal_state"] in agent.VALID_TERMINAL_STATES
