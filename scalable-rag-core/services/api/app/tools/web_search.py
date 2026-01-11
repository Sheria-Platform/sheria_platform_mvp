# services/api/app/tools/web_search.py
import httpx
import os

async def web_search_tool(query: str) -> str:
    """Tool: Search the Internet."""

    api_key = os.getenv("TAVILY_API_KEY")

    if not api_key: return "Web search disabled."

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.tavily.com/search",
                json={"api_key": api_key, "query": query, "max_results": 3}
            )

            data = response.json()
            results = data.get("results", [])
            return "\n".join([f"- {r['title']}: {r['content']}" for r in results])

    except Exception as e:
        return f"Web Search Error: {str(e)}"
