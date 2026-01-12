# scripts/warmup_cache.py
import asyncio
from services.api.app.cache.semantic import semantic_cache

# List of Frequently Asked Questions
FAQ = [
    ("What are your business hours?", "Our business hours are 9 AM to 5 PM."),
    ("What is the return policy?", "Return within 30 days."),
]

async def warmup():
    print("🔥 Warming up semantic cache...")
    for question, answer in FAQ:
        await semantic_cache.set_cached_response(question, answer)
    print("✅ Cache warmup complete.")

if __name__ == "__main__":
    asyncio.run(warmup())