# services/api/app/routes/chat.py
import json
import logging
import time
import uuid
from collections.abc import AsyncGenerator

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from libs.observability.metrics import CACHE_HITS
from services.api.app.agents.graph import agent_app
from services.api.app.agents.state import AgentState
from services.api.app.auth.jwt import get_current_user
from services.api.app.cache.semantic import SemanticCache
from services.api.app.clients.ollama_client import OllamaClient
from services.api.app.dependencies import get_chat_repo, get_llm_client, get_semantic_cache
from services.api.app.logging import bind_context
from services.api.app.memory.chat_repository import ChatRepository
from services.api.app.streaming import iter_agent_events

router = APIRouter()
logger = logging.getLogger(__name__)


# --- Schemas ---
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="The user's query")
    session_id: str | None = Field(
        default=None, description="UUID for the conversation thread"
    )
    web_search: bool = Field(
        default=False,
        description="When True, the agent may query https://new.kenyalaw.org for live results",
    )


# --- Routes ---


@router.post("/stream")
async def chat_stream(
    req: ChatRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
    cache: SemanticCache = Depends(get_semantic_cache),
    memory: ChatRepository = Depends(get_chat_repo),
    llm: OllamaClient = Depends(get_llm_client),
):
    """
    Main Chat Endpoint (Streaming).
    Orchestrates the RAG flow: Cache -> History -> Agent -> Stream.
    """
    # 1. Setup Session Context
    session_id = req.session_id or str(uuid.uuid4())
    user_id = user["id"]

    # Attach session and user to all log records for this request
    bind_context(session_id=session_id, user_id=user_id)

    request_start = time.perf_counter()
    logger.info(
        "Chat request received",
        extra={"message_length": len(req.message)},
    )

    # 2. Semantic Cache Check (Fast Path)
    cache_start = time.perf_counter()
    cached_ans, query_vector = await cache.get_cached_response(req.message)
    cache_duration_ms = round((time.perf_counter() - cache_start) * 1000, 2)

    if cached_ans:
        CACHE_HITS.labels(result="hit").inc()
        logger.info(
            "Semantic cache hit",
            extra={"duration_ms": cache_duration_ms},
        )

        async def stream_cache():
            yield (
                json.dumps(
                    {"event": "answer", "content": cached_ans, "session_id": session_id}
                )
                + "\n"
            )
            yield json.dumps({"event": "done", "session_id": session_id}) + "\n"

        background_tasks.add_task(
            memory.add_message, session_id, "user", req.message, user_id
        )
        background_tasks.add_task(
            memory.add_message, session_id, "assistant", cached_ans, user_id
        )

        return StreamingResponse(stream_cache(), media_type="application/x-ndjson")

    CACHE_HITS.labels(result="miss").inc()
    logger.info(
        "Semantic cache miss",
        extra={"duration_ms": cache_duration_ms},
    )

    # 3. Load Conversation History (Context Window)
    history_objs = await memory.get_history(session_id, limit=6)
    history_dicts: list[dict[str, str]] = [
        {"role": msg.role, "content": msg.content}  # type: ignore[dict-item]
        for msg in history_objs
    ]
    history_dicts.append({"role": "user", "content": req.message})

    # 4. Initialize Agent State (LangGraph)
    initial_state = AgentState(
        messages=history_dicts,
        current_query=req.message,
        documents=[],
        plan=[],
        action="",
        tool_choice="",
        tool_input="",
        query_vector=query_vector or [],  # reuse embedding from cache check
        jurisdiction_filter=[],  # not used by generic chat -- legal-research route only
        citations=[],
        web_search_enabled=req.web_search,
    )

    # 5. Define Generator for Streaming Response
    async def event_generator() -> AsyncGenerator[str, None]:
        final_answer = ""

        try:
            async for node_name, node_data, status_json in iter_agent_events(
                agent_app,
                initial_state,
                config={"configurable": {"llm": llm, "user_id": user_id}},
                session_id=session_id,
            ):
                yield status_json

                # Capture Final Answer from Responder Node
                if node_name == "responder":
                    if node_data.get("messages"):
                        ai_msg = node_data["messages"][-1]
                        final_answer = ai_msg.get("content", "")
                        yield (
                            json.dumps(
                                {
                                    "event": "answer",
                                    "content": final_answer,
                                    "session_id": session_id,
                                }
                            )
                            + "\n"
                        )

            # 6. Post-Processing
            if final_answer:
                total_ms = round((time.perf_counter() - request_start) * 1000, 2)
                logger.info(
                    "Chat request completed",
                    extra={"duration_ms": total_ms, "answer_length": len(final_answer)},
                )
                await memory.add_message(session_id, "user", req.message, user_id)
                await memory.add_message(session_id, "assistant", final_answer, user_id)
                await cache.set_cached_response(req.message, final_answer)

            yield json.dumps({"event": "done", "session_id": session_id}) + "\n"

        except Exception:
            logger.exception("Error in chat stream")
            yield (
                json.dumps(
                    {
                        "event": "error",
                        "content": "An internal error occurred.",
                    }
                )
                + "\n"
            )

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")
