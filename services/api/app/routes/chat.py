# services/api/app/routes/chat.py
import uuid
import json
import logging
from typing import AsyncGenerator
from fastapi import APIRouter, Depends, BackgroundTasks
from fastapi.responses import StreamingResponse
from services.api.app.auth.jwt import get_current_user
from services.api.app.agents.graph import agent_app
from services.api.app.agents.state import AgentState
from services.api.app.memory.postgres import postgres_memory
from services.api.app.cache.semantic import semantic_cache


router = APIRouter()
logger = logging.getLogger(__name__)

class ChatRequest(BaseModel):
    message: str
    session_id: str = None

@router.post("/stream")
async def chat_stream(req: ChatRequest, background_tasks: BackgroundTasks, user: dict = Depends(get_current_user)):
    """Main Chat Endpoint (Streaming). orchestrates Cache -> History -> Agent."""
    session_id = req.session_id or str(uuid.uuid4())
    user_id = user["id"]
    
    # 1. Check Cache
    cached_ans = await semantic_cache.get_cached_response(req.message)
    if cached_ans:
        async def stream_cache():
            yield json.dumps({"type": "answer", "content": cached_ans}) + "\n"
        return StreamingResponse(stream_cache(), media_type="application/x-ndjson")

    # 2. Load History
    history_objs = await postgres_memory.get_history(session_id, limit=6)
    history_dicts = [{"role": msg.role, "content": msg.content} for msg in history_objs]
    history_dicts.append({"role": "user", "content": req.message})

    # 3. Initialize Agent State
    initial_state = AgentState(messages=history_dicts, current_query=req.message, documents=[], plan=[])
    async def event_generator():
        final_answer = ""
        async for event in agent_app.astream(initial_state):
            node_name = list(event.keys())[0]
            node_data = event[node_name]
            
            # Emit status update
            yield json.dumps({"type": "status", "node": node_name}) + "\n"
            if node_name == "responder" and "messages" in node_data:
                final_answer = node_data["messages"][-1]["content"]
                yield json.dumps({"type": "answer", "content": final_answer}) + "\n"
        
        # Background: Save to DB & Cache
        if final_answer:
            await postgres_memory.add_message(session_id, "user", req.message, user_id)
            await postgres_memory.add_message(session_id, "assistant", final_answer, user_id)
            await semantic_cache.set_cached_response(req.message, final_answer)
    return StreamingResponse(event_generator(), media_type="application/x-ndjson")