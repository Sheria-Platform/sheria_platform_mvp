# services/api/app/tools/vector_search.py
from services.api.app.clients.qdrant import qdrant_client
from services.api.app.clients.ray_embed import embed_client

async def search_vector_tool(query: str) -> str:
    """Tool: Search the Vector Database for documents."""
    try:
        vector = await embed_client.embed_query(query)
        results = await qdrant_client.search(vector, limit=3)
        
        formatted = ""
        for r in results:
            meta = r.payload.get("metadata", {})
            formatted += f"- {r.payload.get('text', '')[:200]}... [Source: {meta.get('filename')}]\n"
        return formatted if formatted else "No relevant documents found."
    except Exception as e:
        return f"Search Error: {str(e)}"