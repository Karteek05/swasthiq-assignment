"""Exercises the HTTP layer (main.py) end to end: POST /agent/run persists
to the conversation store, and the queue/detail/resolve endpoints our own
frontend relies on read that store back correctly. Stubs the LLM call the
same way test_agent_flow.py does, so it runs without hitting the real API.
"""
import json
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import agent
import store as store_module
from fastapi.testclient import TestClient


def _msg(tool_calls=None, content=None):
    return SimpleNamespace(tool_calls=tool_calls, content=content)


def _tool_call(call_id, name, arguments):
    return SimpleNamespace(id=call_id, function=SimpleNamespace(name=name, arguments=json.dumps(arguments)))


def _response(message, tokens=10):
    return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=SimpleNamespace(total_tokens=tokens))


def test_agent_run_persists_and_queue_reflects_it(monkeypatch):
    # Fresh store per test so counts are predictable regardless of test order.
    monkeypatch.setattr(store_module, "store", store_module.ConversationStore())
    import main
    monkeypatch.setattr(main, "store", store_module.store)

    calls = iter([
        _response(_msg(tool_calls=[_tool_call("c1", "escalate_to_human", {"reason": "clinical_urgent"})])),
        _response(_msg(tool_calls=[_tool_call("c2", "finish_conversation", {
            "terminal_state": "escalated",
            "escalation_reason": "clinical_urgent",
            "reply": "Connecting you now.",
        })])),
    ])
    monkeypatch.setattr(agent, "_call_with_retry", lambda client, **kw: next(calls))
    monkeypatch.setattr(agent, "setup_client", lambda: None)

    client = TestClient(main.app)

    resp = client.post("/agent/run", json={
        "conversation_id": "cv_api_1",
        "today": "2026-10-01",
        "turns": ["Seene mein dard ho raha hai"],
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["conversation_id"] == "cv_api_1"
    assert body["terminal_state"] == "escalated"
    assert "transcript" not in body  # graded contract stays clean

    queue = client.get("/conversations").json()
    assert queue["counters"]["escalated"] == 1
    assert queue["counters"]["escalated_open"] == 1
    assert queue["counters"]["urgent_open"] == 1
    assert queue["conversations"][0]["conversation_id"] == "cv_api_1"

    detail = client.get("/conversations/cv_api_1").json()
    assert detail["terminal_state"] == "escalated"
    assert len(detail["transcript"]) > 0
    assert detail["resolved"] is False

    resolved = client.post("/conversations/cv_api_1/resolve").json()
    assert resolved["resolved"] is True

    queue_after = client.get("/conversations").json()
    assert queue_after["counters"]["escalated_open"] == 0
    assert queue_after["counters"]["urgent_open"] == 0


def test_get_unknown_conversation_404s(monkeypatch):
    monkeypatch.setattr(store_module, "store", store_module.ConversationStore())
    import main
    monkeypatch.setattr(main, "store", store_module.store)
    client = TestClient(main.app)

    resp = client.get("/conversations/cv_does_not_exist")
    assert resp.status_code == 404


def test_malformed_request_body_returns_422_not_500():
    import main
    client = TestClient(main.app)
    resp = client.post("/agent/run", json={"conversation_id": "cv_x"})  # missing today/turns
    assert resp.status_code == 422
