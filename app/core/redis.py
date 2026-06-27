import redis.asyncio as redis
from typing import Optional
from app.core.config import settings

class RedisClient:
    _instance: Optional[redis.Redis] = None

    @classmethod
    def get_client(cls) -> redis.Redis:
        if cls._instance is None:
            # We use decode_responses=True to automatically decode bytes to str
            cls._instance = redis.from_url(settings.redis_url, decode_responses=True)
        return cls._instance

    @classmethod
    async def close(cls):
        if cls._instance:
            await cls._instance.aclose()
            cls._instance = None

# Helper functions for common cache operations
async def get_cache(key: str) -> Optional[str]:
    try:
        client = RedisClient.get_client()
        return await client.get(key)
    except Exception:
        # Fail gracefully if Redis is down
        return None

async def set_cache(key: str, value: str, expire_seconds: int = 300) -> None:
    try:
        client = RedisClient.get_client()
        await client.set(key, value, ex=expire_seconds)
    except Exception:
        pass

async def delete_cache(pattern: str) -> None:
    try:
        client = RedisClient.get_client()
        keys = await client.keys(pattern)
        if keys:
            await client.delete(*keys)
    except Exception:
        pass
