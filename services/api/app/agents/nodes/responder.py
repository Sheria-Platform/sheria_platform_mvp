# services/api/app/agents/nodes/responder.py
import logging
import time

from services.api.app.agents.state import AgentState
from services.api.app.clients.ollama_client import ollama_client  # Replaces ray_llm

logger = logging.getLogger(__name__)


async def generate_node(state: AgentState) -> dict:
    """
    Synthesizes the final answer using retrieved documents.

    Uses Ollama /api/chat instead of Ray Serve for LLM inference.
    """
    query = state["current_query"]
    documents = state.get("documents", [])

    logger.info(
        "Responder node started",
        extra={"node": "responder", "doc_count": len(documents)},
    )
    start = time.perf_counter()

    context_str = "\n\n".join(documents)

    prompt = f"""
    You are a helpful Enterprise Assistant. Use the context below to answer the user's question.

    Context:
    {context_str}

    Question:
    {query}

    Instructions:
    1. Cite sources using [Source: Filename].
    2. If the answer is not in the context, say "I don't have that information in my documents."
    3. Be concise and professional.
    """

    # Call Ollama LLM (replaces llm_client.chat_completion)
    answer = await ollama_client.chat_completion(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,  # Low creativity, high fidelity
    )

    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    logger.info(
        "Responder node completed",
        extra={
            "node": "responder",
            "duration_ms": duration_ms,
            "answer_length": len(answer),
        },
    )

    return {"messages": [{"role": "assistant", "content": answer}]}
