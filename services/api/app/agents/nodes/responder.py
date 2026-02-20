# services/api/app/agents/nodes/responder.py
from langchain_core.callbacks.manager import dispatch_custom_event
from langchain_core.runnables import RunnableConfig

from services.api.app.agents.nodes.constitution import Compass
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
    action = state.get("action", "retrieve")
    documents = state.get("documents", [])

    if action == "direct_answer":
        # We use a leaner prompt that focuses on Persona, not Context
        system_content = (f"{Compass.IDENTITY['persona']}\nTask: Respond to the user's greeting or identity query "
                          f"politely.")
        user_content = query

    else:
        system_content = Compass.SYSTEM_BASE
        context_str = "\n\n".join(documents)
        user_content = f"""
                <context>
                {context_str or 'No documents found.'}
                </context>

                Based on the <context> provided above, answer this question: {query}
            """

    full_response = ''

    async for token in llm.generate_streaming(
        messages=[
            {'role': 'system', 'content': system_content},
            {"role": "user", "content": user_content
             }
        ],
        temperature=0.1
    ):
        full_response += token

        dispatch_custom_event(
            name="llm_token",
            data={"content": token}
        )

    return {"messages": [{"role": "assistant", "content": full_response}]}
