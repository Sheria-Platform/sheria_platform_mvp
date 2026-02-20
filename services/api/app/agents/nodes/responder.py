# services/api/app/agents/nodes/responder.py
from langchain_core.callbacks.manager import dispatch_custom_event
from langchain_core.runnables import RunnableConfig

from services.api.app.agents.state import AgentState


async def generate_node(state: AgentState, config: RunnableConfig) -> dict:
    """
    Generate a response to the user's query using retrieved documents as context.

    This node streams tokens from the LLM as it generates a response based on the
    provided context documents. Each token is dispatched as a custom event for
    real-time streaming to the client. The response includes source citations and
    follows professional assistant guidelines.

    Args:
        state (AgentState): The current agent state containing:
            - current_query (str): The user's question to be answered
            - documents (list, optional): List of retrieved document strings to use as context
        config (RunnableConfig): The runnable configuration containing:
            - configurable["llm"]: The language model instance with streaming capabilities

    Returns:
        dict: A dictionary containing:
            - messages (list): A list with a single assistant message dict containing:
                - role (str): Set to "assistant"
                - content (str): The complete generated response with citations
    """

    llm = config["configurable"]["llm"]

    query = state["current_query"]
    documents = state.get("documents", [])

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

    full_response = ''

    async for token in llm.generate_streaming(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3
    ):
        full_response += token

        dispatch_custom_event(
            name="llm_token",
            data={"content": token}
        )

    return {"messages": [{"role": "assistant", "content": full_response}]}
