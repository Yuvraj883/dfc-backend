import logging
from typing import Optional
from upstash_redis.asyncio import Redis as UpstashRedis
from app.core.config import settings

logger = logging.getLogger(__name__)

class RedisClient:
    _instance: Optional[UpstashRedis] = None

    @classmethod
    def get_client(cls) -> Optional[UpstashRedis]:
        if cls._instance is None:
            if settings.upstash_redis_rest_url and settings.upstash_redis_rest_token:
                cls._instance = UpstashRedis(
                    url=settings.upstash_redis_rest_url,
                    token=settings.upstash_redis_rest_token
                )
            else:
                logger.warning("Upstash Redis credentials not configured.")
        return cls._instance

# Helper functions for common cache operations
async def get_cache(key: str) -> Optional[str]:
    try:
        client = RedisClient.get_client()
        if client:
            return await client.get(key)
    except Exception as e:
        logger.error(f"Redis get_cache error: {e}")
    return None

async def set_cache(key: str, value: str, expire_seconds: int = 300) -> None:
    try:
        client = RedisClient.get_client()
        if client:
            await client.set(key, value, ex=expire_seconds)
    except Exception as e:
        logger.error(f"Redis set_cache error: {e}")

async def delete_cache(pattern: str) -> None:
    try:
        client = RedisClient.get_client()
        if client:
            # upstash_redis supports scan/keys, but keys is simpler for small caches
            keys = await client.keys(pattern)
            if keys:
                await client.delete(*keys)
    except Exception as e:
        logger.error(f"Redis delete_cache error: {e}")
