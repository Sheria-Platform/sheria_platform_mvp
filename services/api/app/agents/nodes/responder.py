# services/api/app/agents/nodes/responder.py
"""LangGraph Responder node.

Synthesises the final answer from retrieved documents using the Ollama LLM.
Formats citations in Kenya Law Reports style and structures the response
using IRAC (Issue, Rule, Application, Conclusion).
"""

import logging

from services.api.app.agents.decorators import node_timer
from services.api.app.agents.state import AgentState
from services.api.app.clients.ollama_client import ollama_client

logger = logging.getLogger(__name__)


async def generate_node(state: AgentState) -> dict:
    """Synthesize the final answer using retrieved documents.

    Calls Ollama with a structured IRAC prompt that includes retrieved Kenya
    Law Reports context and prior conversation turns for multi-turn awareness.

    Args:
        state: Current agent state.  Must contain ``"current_query"`` and
            ``"documents"`` (list of retrieved context strings).

    Returns:
        Partial state dict with ``"messages"`` containing the assistant's
        cited legal research response.
    """
    query = state["current_query"]
    documents = state.get("documents", [])

    context_str = "\n\n".join(documents)

    # Include prior turns for multi-turn awareness (exclude current user message)
    history_messages = state.get("messages", [])
    prior_turns = history_messages[:-1][-4:]  # up to 2 prior turns
    history_text = (
        "\n".join(f"{m['role'].capitalize()}: {m['content']}" for m in prior_turns)
        if prior_turns
        else "None"
    )

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

    answer = ""
    async with node_timer("responder", logger):
        answer = await ollama_client.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,  # Low creativity, high fidelity
        )

    return {"messages": [{"role": "assistant", "content": answer}]}
