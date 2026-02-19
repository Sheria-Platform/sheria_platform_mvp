# services/api/app/routes/chat.py
import json
import logging
import uuid
from collections.abc import AsyncGenerator

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from services.api.app.agents.graph import agent_app
from services.api.app.agents.state import AgentState
from services.api.app.auth.jwt import get_current_user

# Import classes for type hinting
from services.api.app.cache.semantic import SemanticCache
from services.api.app.cache.semantic import semantic_cache as global_cache
from services.api.app.clients.ollama_client import OllamaClient  # Replaces RayLLMClient
from services.api.app.clients.ollama_client import ollama_client as global_llm
from services.api.app.memory.postgres import PostgresMemory
from services.api.app.memory.postgres import postgres_memory as global_memory

router = APIRouter()
logger = logging.getLogger(__name__)

# --- Dependency Providers (DI) ---
# These wrappers allow easy dependency overrides in pytest
# e.g., app.dependency_overrides[get_llm_client] = MockOllamaClient


def get_semantic_cache() -> SemanticCache:
    return global_cache


def get_memory() -> PostgresMemory:
    return global_memory


def get_llm_client() -> OllamaClient:
    return global_llm


# --- Schemas ---
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="The user's query")
    session_id: str = Field(
        default=None, description="UUID for the conversation thread"
    )


# --- Routes ---


@router.post("/stream")
async def chat_stream(
    req: ChatRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
    # Inject dependencies via FastAPI Depends
    cache: SemanticCache = Depends(get_semantic_cache),
    memory: PostgresMemory = Depends(get_memory),
    llm: OllamaClient = Depends(get_llm_client),
):
    """
    Main Chat Endpoint (Streaming).
    Orchestrates the RAG flow: Cache -> History -> Agent -> Stream.
    """
    # 1. Setup Session Context
    session_id = req.session_id or str(uuid.uuid4())
    user_id = user["id"]

    logger.info("Chat request for session %s from user %s", session_id, user_id)

    # 2. Semantic Cache Check (Fast Path)
    cached_ans = await cache.get_cached_response(req.message)

    if cached_ans:
        logger.info("Cache hit for session %s", session_id)

        async def stream_cache():
            yield json.dumps(
                {"type": "answer", "content": cached_ans, "session_id": session_id}
            ) + "\n"

        background_tasks.add_task(
            memory.add_message, session_id, "user", req.message, user_id
        )
        background_tasks.add_task(
            memory.add_message, session_id, "assistant", cached_ans, user_id
        )

        return StreamingResponse(stream_cache(), media_type="application/x-ndjson")

    # 3. Load Conversation History (Context Window)
    history_objs = await memory.get_history(session_id, limit=6)
    history_dicts = [{"role": msg.role, "content": msg.content} for msg in history_objs]
    history_dicts.append({"role": "user", "content": req.message})

    # 4. Initialize Agent State (LangGraph)
    initial_state = AgentState(
        messages=history_dicts, current_query=req.message, documents=[], plan=[]
    )

    # 5. Define Generator for Streaming Response
    async def event_generator() -> AsyncGenerator[str]:
        final_answer = ""

        try:
            async for event in agent_app.astream(
                initial_state, config={"configurable": {"llm": llm, "user_id": user_id}}
            ):
                node_name = list(event.keys())[0]
                node_data = event[node_name]

                # Emit Status Update
                yield json.dumps(
                    {
                        "type": "status",
                        "node": node_name,
                        "session_id": session_id,
                        "info": f"Completed step: {node_name}",
                    }
                ) + "\n"

                # Capture Final Answer from Responder Node
                if node_name == "responder":
                    if "messages" in node_data and node_data["messages"]:
                        ai_msg = node_data["messages"][-1]
                        final_answer = ai_msg.get("content", "")

                        yield json.dumps(
                            {
                                "type": "answer",
                                "content": final_answer,
                                "session_id": session_id,
                            }
                        ) + "\n"

            # 6. Post-Processing
            if final_answer:
                await memory.add_message(session_id, "user", req.message, user_id)
                await memory.add_message(session_id, "assistant", final_answer, user_id)
                await cache.set_cached_response(req.message, final_answer)

        except Exception as e:
            logger.error("Error in chat stream: %s", e, exc_info=True)
            yield json.dumps(
                {"type": "error", "content": "An internal error occurred."}
            ) + "\n"

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")
