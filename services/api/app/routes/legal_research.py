# services/api/app/routes/legal_research.py
"""POST /api/v1/legal-research — Sheria Ask judicial research endpoint.

Structured legal research API for judges, magistrates, and court staff.
Unlike the generic chat endpoint, this route:

- Always retrieves from Kenya Law Reports (no planner shortcut to direct_answer).
- Accepts optional ``jurisdiction`` and ``date_range`` filters applied as
  Qdrant payload filters so only relevant courts are searched.
- Returns structured ``citations`` alongside the IRAC answer text.

Streaming response format (NDJSON, one JSON object per line):

    {"event": "status", "step": "retriever", "session_id": "..."}
    {"event": "status", "step": "responder", "session_id": "..."}
    {"event": "answer", "content": "...", "citations": [...], "session_id": "..."}
"""

import json
import logging
import time
import uuid
from collections.abc import AsyncGenerator

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from services.api.app.agents.legal_research_graph import legal_research_app
from services.api.app.agents.state import AgentState
from services.api.app.auth.jwt import get_current_user
from services.api.app.cache.semantic import SemanticCache
from services.api.app.clients.ollama_client import OllamaClient
from services.api.app.dependencies import get_llm_client, get_memory, get_semantic_cache
from services.api.app.logging import bind_context
from services.api.app.memory.postgres import PostgresMemory
from services.api.app.streaming import iter_agent_events

router = APIRouter()
logger = logging.getLogger(__name__)


# --- Schemas ---


class DateRange(BaseModel):
    from_date: str = Field(alias="from", description="Start year, e.g. '2010'")
    to_date: str = Field(alias="to", description="End year, e.g. '2026'")

    model_config = {"populate_by_name": True}


class LegalResearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Legal research question")
    jurisdiction: list[str] | None = Field(
        default=None,
        description=(
            "Optional court filter. Valid values: 'Supreme Court', "
            "'Court of Appeal', 'High Court', 'Industrial Court', etc."
        ),
        examples=[["Supreme Court", "Court of Appeal"]],
    )
    date_range: DateRange | None = Field(
        default=None,
        description="Optional year range to restrict results",
    )
    session_id: str | None = Field(
        default=None,
        description="UUID for the conversation thread (created if omitted)",
    )


# --- Route ---


@router.post("")
async def legal_research(
    req: LegalResearchRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
    cache: SemanticCache = Depends(get_semantic_cache),
    memory: PostgresMemory = Depends(get_memory),
    llm: OllamaClient = Depends(get_llm_client),
):
    """Judicial legal research endpoint (streaming).

    Retrieves relevant Kenya Law Reports chunks and synthesises a cited
    IRAC-structured answer.  Always hits the retriever — never short-circuits
    to a generic direct answer.
    """
    session_id = req.session_id or str(uuid.uuid4())
    user_id = user["id"]
    bind_context(session_id=session_id, user_id=user_id)

    request_start = time.perf_counter()
    logger.info(
        "Legal research request received",
        extra={
            "query_length": len(req.query),
            "jurisdiction": req.jurisdiction,
            "date_range": req.date_range.model_dump() if req.date_range else None,
        },
    )

    # Semantic cache check — reuse query vector for retriever if cached
    cached_ans, query_vector = await cache.get_cached_response(req.query)
    if cached_ans:
        logger.info("Legal research cache hit")

        async def _stream_cache() -> AsyncGenerator[str, None]:
            yield (
                json.dumps(
                    {
                        "event": "answer",
                        "content": cached_ans,
                        "citations": [],
                        "session_id": session_id,
                    }
                )
                + "\n"
            )

        background_tasks.add_task(
            memory.add_message, session_id, "user", req.query, user_id
        )
        background_tasks.add_task(
            memory.add_message, session_id, "assistant", cached_ans, user_id
        )
        return StreamingResponse(_stream_cache(), media_type="application/x-ndjson")

    # Build initial agent state — action is not set here; this graph skips the
    # planner so action is irrelevant, but jurisdiction_filter is consumed by
    # the retriever node.
    initial_state = AgentState(
        messages=[{"role": "user", "content": req.query}],
        current_query=req.query,
        documents=[],
        plan=[],
        action="retrieve",
        tool_choice="",
        tool_input="",
        query_vector=query_vector or [],
        jurisdiction_filter=req.jurisdiction or [],
        citations=[],
    )

    async def event_generator() -> AsyncGenerator[str, None]:
        final_answer = ""
        final_citations: list[dict] = []

        try:
            async for node_name, node_data, status_json in iter_agent_events(
                legal_research_app,
                initial_state,
                config={"configurable": {"llm": llm, "user_id": user_id}},
                session_id=session_id,
                metric_prefix="legal_",
            ):
                yield status_json

                # Capture structured citations from retriever
                if node_name == "retriever":
                    final_citations = node_data.get("citations", [])

                # Capture final answer from responder
                if node_name == "responder":
                    if node_data.get("messages"):
                        ai_msg = node_data["messages"][-1]
                        final_answer = ai_msg.get("content", "")

                        yield (
                            json.dumps(
                                {
                                    "event": "answer",
                                    "content": final_answer,
                                    "citations": final_citations,
                                    "session_id": session_id,
                                }
                            )
                            + "\n"
                        )

            if final_answer:
                total_ms = round((time.perf_counter() - request_start) * 1000, 2)
                logger.info(
                    "Legal research completed",
                    extra={
                        "duration_ms": total_ms,
                        "answer_length": len(final_answer),
                        "citation_count": len(final_citations),
                    },
                )
                await memory.add_message(session_id, "user", req.query, user_id)
                await memory.add_message(session_id, "assistant", final_answer, user_id)
                await cache.set_cached_response(req.query, final_answer)

            yield json.dumps({"event": "done", "session_id": session_id}) + "\n"

        except Exception:
            logger.exception("Error in legal research stream")
            yield (
                json.dumps(
                    {
                        "event": "error",
                        "content": "An internal error occurred during legal research.",
                    }
                )
                + "\n"
            )

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")
