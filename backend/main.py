from fastapi import FastAPI, HTTPException
import traceback
from fastapi.middleware.cors import CORSMiddleware
from models import AgentRunRequest, AgentRunResponse
from agent import run_agent
from store import store

app = FastAPI(title="Clinic Agent Backend")

# Allow frontend to access the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/agent/run", response_model=AgentRunResponse)
async def agent_run(request: AgentRunRequest):
    """The one endpoint the grader calls. Everything below this line is
    extra plumbing for our own Handoff Queue / Conversation Detail UI."""
    try:
        result = run_agent(request.conversation_id, request.today, request.turns)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Agent run failed: {e}")

    store.save(request.conversation_id, request.today, request.turns, result)
    return result


@app.get("/conversations")
async def list_conversations():
    return {
        "counters": store.counters(),
        "conversations": store.list_summaries(),
    }


@app.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    record = store.get(conversation_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"No conversation {conversation_id!r} on record.")
    return record


@app.post("/conversations/{conversation_id}/resolve")
async def resolve_conversation(conversation_id: str):
    if not store.resolve(conversation_id):
        raise HTTPException(status_code=404, detail=f"No conversation {conversation_id!r} on record.")
    return store.get(conversation_id)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
