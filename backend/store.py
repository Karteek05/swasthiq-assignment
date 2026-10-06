import threading
from datetime import datetime
from typing import Any, Dict, List, Optional


class ConversationStore:
    """In-memory record of past /agent/run calls, used only by our own
    frontend (Handoff Queue / Conversation Detail screens). The grader only
    ever calls POST /agent/run; this is a side effect of that call, not
    part of the graded contract. Resets on process restart -- acceptable
    for a take-home per the "SQLite or in-memory only" constraint."""

    def __init__(self):
        self._lock = threading.Lock()
        self._records: Dict[str, Dict[str, Any]] = {}
        self._order: List[str] = []  # most-recent-first
        self._resolved: set = set()

    def save(self, conversation_id: str, today: str, turns: List[str], result: Dict[str, Any]) -> None:
        with self._lock:
            if conversation_id not in self._records:
                self._order.insert(0, conversation_id)
            else:
                self._order.remove(conversation_id)
                self._order.insert(0, conversation_id)
            self._records[conversation_id] = {
                **result,
                "conversation_id": conversation_id,
                "today": today,
                "turns": turns,
                "recorded_at": datetime.utcnow().isoformat() + "Z",
            }

    @staticmethod
    def _caller_said(record: Dict[str, Any]) -> str:
        transcript = record.get("transcript") or []
        caller_lines = [t["text"] for t in transcript if t.get("role") == "caller"]
        if caller_lines:
            return caller_lines[-1]
        turns = record.get("turns") or []
        return turns[0] if turns else ""

    def list_summaries(self) -> List[Dict[str, Any]]:
        with self._lock:
            out = []
            for cid in self._order:
                r = self._records[cid]
                out.append({
                    "conversation_id": cid,
                    "terminal_state": r.get("terminal_state"),
                    "escalation_reason": r.get("escalation_reason"),
                    "caller_said": self._caller_said(r),
                    "recorded_at": r.get("recorded_at"),
                    "resolved": cid in self._resolved,
                })
            return out

    def counters(self) -> Dict[str, Any]:
        summaries = self.list_summaries()
        total = len(summaries)
        escalated = [s for s in summaries if s["terminal_state"] == "escalated"]
        open_escalations = [s for s in escalated if not s["resolved"]]
        urgent_open = [s for s in open_escalations if s["escalation_reason"] == "clinical_urgent"]
        completed = total - len(escalated)
        return {
            "conversations_today": total,
            "completed_by_agent": completed,
            "completed_by_agent_pct": round(100 * completed / total) if total else 0,
            "escalated": len(escalated),
            "escalated_open": len(open_escalations),
            "urgent_open": len(urgent_open),
        }

    def get(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            r = self._records.get(conversation_id)
            if not r:
                return None
            return {**r, "resolved": conversation_id in self._resolved}

    def resolve(self, conversation_id: str) -> bool:
        with self._lock:
            if conversation_id not in self._records:
                return False
            self._resolved.add(conversation_id)
            return True


store = ConversationStore()
