# services/api/app/clients/ollama_client.py
"""
Ollama LLM Client - Replaces Ray Serve ray_llm.py.

Provides an async HTTP interface to Ollama's /api/chat endpoint with:
- Connection pooling (20 keepalive / 50 max connections)
- Exponential backoff retries via libs/retry/backoff.py
- Configurable timeouts (default 60s)
- Streaming support
- Health check
"""
import json
import logging
from collections.abc import AsyncGenerator

import httpx

from libs.retry.backoff import exponential_backoff
from services.api.app.core.config import settings

logger = logging.getLogger(__name__)


class OllamaClient:
    """
    Async HTTP client for the Ollama LLM API.

    Lifecycle is managed by the FastAPI lifespan in main.py:
        await ollama_client.start()   # on startup
        await ollama_client.close()   # on shutdown
    """

    def __init__(self) -> None:
        self.base_url: str = settings.OLLAMA_BASE_URL
        self.model: str = settings.OLLAMA_LLM_MODEL
        self.timeout: int = settings.OLLAMA_TIMEOUT
        # Initialized during startup
        self.client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        """Initialize the persistent HTTP client pool. Called on app startup."""
        limits = httpx.Limits(max_keepalive_connections=20, max_connections=50)
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(self.timeout),
            limits=limits,
        )
        logger.info(
            "Ollama LLM client initialized. base_url=%s model=%s",
            self.base_url,
            self.model,
        )

    async def close(self) -> None:
        """Release the HTTP client pool. Called on app shutdown."""
        if self.client:
            await self.client.aclose()
            logger.info("Ollama LLM client closed.")

    async def health_check(self) -> bool:
        """Return True if Ollama is reachable and responding."""
        try:
            if not self.client:
                return False
            response = await self.client.get("/api/tags", timeout=5.0)
            return response.status_code == 200
        except Exception as exc:
            logger.warning("Ollama health check failed: %s", exc)
            return False

    @exponential_backoff(max_retries=3, base_delay=1.0)
    async def chat_completion(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 1024,
        json_mode: bool = False,
    ) -> str:
        """
        Call Ollama /api/chat (non-streaming) and return the assistant text.

        Replaces RayLLMClient.chat_completion().

        Args:
            messages:    List of {"role": ..., "content": ...} dicts.
            temperature: Sampling temperature (0.0 = deterministic).
            max_tokens:  Maximum tokens to generate.
            json_mode:   Ask Ollama to constrain output to valid JSON.

        Returns:
            The assistant's response as a plain string.

        Raises:
            RuntimeError: If client is not yet started.
            httpx.HTTPStatusError: On non-2xx responses.
            httpx.TimeoutException: On request timeout.
        """
        if not self.client:
            raise RuntimeError("OllamaClient not initialized. Call start() first.")

        payload: dict = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if json_mode:
            payload["format"] = "json"

        try:
            response = await self.client.post("/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
            return data["message"]["content"]

        except httpx.HTTPStatusError as exc:
            logger.error(
                "Ollama API error: status=%s body=%s",
                exc.response.status_code,
                exc.response.text[:200],
            )
            raise
        except httpx.TimeoutException:
            logger.error("Ollama request timed out after %ss", self.timeout)
            raise
        except KeyError as exc:
            raise RuntimeError(f"Unexpected Ollama response structure: {exc}") from exc

    async def generate_streaming(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> AsyncGenerator[str, None]:
        """
        Stream tokens from Ollama /api/chat with stream=True.

        Yields individual content chunks as they arrive from the model.
        """
        if not self.client:
            raise RuntimeError("OllamaClient not initialized. Call start() first.")

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        try:
            async with self.client.stream("POST", "/api/chat", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    content = chunk.get("message", {}).get("content", "")
                    if content:
                        yield content
                    if chunk.get("done", False):
                        break

        except httpx.HTTPStatusError as exc:
            logger.error("Ollama streaming error: status=%s", exc.response.status_code)
            raise
        except httpx.TimeoutException:
            logger.error("Ollama streaming request timed out")
            raise

    async def generate_conversation_title(self, user_query: str) -> str:
        """
        Summarizes a user query into a 5-word title.
        """
        # Keep it simple and focused
        prompt = f"""Summarize the following query into a concise title of no more than 5 words. 
        Focus on contextualizing the query. Do not use punctuation.
        Do not provide any introductory text. Output only the title.

        QUERY: {user_query}
        TITLE:"""

        # Prepare the messages for the chat_completion endpoint
        messages = [{"role": "user", "content": prompt}]

        # Call your existing utility
        # We use low temperature for consistency (titles shouldn't be 'creative')
        title = await self.chat_completion(
            messages=messages,
            temperature=0.2,
            max_tokens=20
        )

        return title.strip()


# Global singleton — lifecycle managed by main.py lifespan
ollama_client = OllamaClient()
