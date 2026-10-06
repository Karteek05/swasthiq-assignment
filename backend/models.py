from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict
from enum import Enum

class TerminalState(str, Enum):
    booked = "booked"
    rescheduled = "rescheduled"
    cancelled = "cancelled"
    escalated = "escalated"
    refused = "refused"
    abandoned = "abandoned"

class EscalationReason(str, Enum):
    clinical_urgent = "clinical_urgent"
    medical_advice = "medical_advice"
    not_authorised = "not_authorised"
    ambiguous_patient = "ambiguous_patient"
    out_of_scope = "out_of_scope"

class AgentRunRequest(BaseModel):
    conversation_id: str
    today: str
    turns: List[str]

class ToolCallSchema(BaseModel):
    name: str
    arguments: Dict[str, Any]

class Metrics(BaseModel):
    turns: int
    tokens: int
    latency_ms: int

class AgentRunResponse(BaseModel):
    conversation_id: str
    tool_calls: List[ToolCallSchema]
    terminal_state: TerminalState
    escalation_reason: Optional[EscalationReason] = None
    patient_id: Optional[str] = None
    appointment_id: Optional[str] = None
    reply: str
    metrics: Metrics
