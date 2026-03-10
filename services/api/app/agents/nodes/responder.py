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

    # Include prior turns for multi-turn awareness (exclude current user message)
    history_messages = state.get("messages", [])
    prior_turns = history_messages[:-1][-4:]  # up to 2 prior turns
    history_text = "\n".join(
        f"{m['role'].capitalize()}: {m['content']}" for m in prior_turns
    ) if prior_turns else "None"

    prompt = f"""
You are Sheria, an AI legal research assistant for Kenya's judiciary.
You support judges, magistrates, registrars, and court staff in their legal research.

IMPORTANT: You assist with legal research only. The judge makes all final decisions.
Never recommend a specific judgment outcome. Present law objectively and completely.

Conversation History:
{history_text}

Retrieved Legal Context:
{context_str}

Legal Research Query:
{query}

Instructions:
1. CITATIONS: Cite every authority in Kenya Law format: [Year] Court Number
   (e.g., [2019] KESC 12, [2021] KECA 45, [2018] KEHC 234).
   Use [Source: filename] for document references.

2. PRECEDENT HIERARCHY: Clearly distinguish authority levels —
   - Binding: Supreme Court binds all courts; Court of Appeal binds High Court and below.
   - Persuasive: Decisions from other jurisdictions, High Court decisions at same level, obiter dicta.

3. STRUCTURE: For legal issues use IRAC format —
   - Issue: State the precise legal question.
   - Rule: State the applicable legal test, statute, or principle.
   - Application: Apply the rule to the facts or query.
   - Conclusion: State the resulting legal position clearly.

4. LIMITATIONS: If the answer is not in the retrieved context, say:
   "I could not find sufficient case law in the current database for this query.
   Consider consulting Kenya Law Reports directly or broadening the search scope."
   Do NOT fabricate case names, citations, or legal principles.

5. JUDICIAL INDEPENDENCE: For queries touching on case outcomes, close with:
   "This research is provided to assist your deliberations. The decision rests with the court."
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
