from services.api.app.clients.ollama_client import ollama_client
from services.api.app.core.database import get_db_session_manual


async def run_background_tasks(task_type: str, **kwargs):
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
