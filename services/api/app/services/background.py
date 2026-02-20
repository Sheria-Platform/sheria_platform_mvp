from services.api.app.clients.ollama_client import ollama_client
from services.api.app.core.database import get_db_session_manual


async def run_background_tasks(task_type: str, **kwargs):
    """
    Execute background tasks for conversation management operations.

    This function handles asynchronous background tasks related to conversation
    management, including adding messages to conversations and updating conversation
    titles. It creates a database session and uses ConversationCRUDManager to
    perform the requested operations.

    Args:
        task_type (str): The type of background task to execute. Supported values:
            - 'add_message': Adds a new message to a conversation
            - 'update_title': Updates the title of a conversation based on user query
        **kwargs: Variable keyword arguments depending on task_type:
            For 'add_message':
                - conversation_id (str): The ID of the conversation to add the message to
                - role (str): The role of the message sender (e.g., 'user', 'assistant')
                - content (str): The content of the message to add
            For 'update_title':
                - conversation_id (str): The ID of the conversation to update
                - user_id (str): The ID of the user who owns the conversation
                - user_query (str): The user's query used to generate the conversation title

    Returns:
        None

    Raises:
        ValueError: If required parameters for the specified task_type are missing
    """
    from services.api.app.services.rag import ConversationCRUDManager

    async with get_db_session_manual() as session:
        memory = ConversationCRUDManager(db_session=session)

        if task_type == 'add_message':
            conversation_id = kwargs.get('conversation_id')
            if not conversation_id:
                raise ValueError('Missing conversation_id')

            role = kwargs.get('role')
            if not role:
                raise ValueError('Missing role')

            content = kwargs.get('content')
            if not content:
                raise ValueError('Missing content')

            await memory.add_message(conversation_id=conversation_id, role=role, content=content)

        elif task_type == 'update_title':
            conversation_id = kwargs.get('conversation_id')
            if not conversation_id:
                raise ValueError('Missing conversation_id')

            user_id = kwargs.get('user_id')
            if not user_id:
                raise ValueError('Missing user_id')

            user_query = kwargs.get('user_query')
            if not user_query:
                raise ValueError('Missing user_query')

            title = await ollama_client.generate_conversation_title(user_query)

            await memory.update_conversation_title(conversation_id=conversation_id, new_title=title, user_id=user_id)
