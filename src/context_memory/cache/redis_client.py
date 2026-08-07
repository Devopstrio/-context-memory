"""Production-grade Redis client with connection pooling, retry, and circuit breaker."""

import asyncio
import json
import time
from collections.abc import Callable
from enum import Enum
from typing import Any

import redis.asyncio as aioredis
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from context_memory.config.settings import get_settings

logger = structlog.get_logger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class RedisCircuitBreaker:
    """Circuit breaker for Redis connections."""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_requests: int = 3,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_requests = half_open_max_requests
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._half_open_requests = 0
        self._lock = asyncio.Lock()

    async def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute function with circuit breaker protection."""
        async with self._lock:
            if self._state == CircuitState.OPEN:
                if time.time() - self._last_failure_time >= self.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_requests = 0
                    logger.info("Circuit breaker transitioning to HALF_OPEN")
                else:
                    raise RedisUnavailableError("Circuit breaker is OPEN")

            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_requests >= self.half_open_max_requests:
                    raise RedisUnavailableError("Circuit breaker HALF_OPEN limit reached")
                self._half_open_requests += 1

        try:
            result = await func(*args, **kwargs)
            async with self._lock:
                if self._state == CircuitState.HALF_OPEN:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._half_open_requests = 0
                    logger.info("Circuit breaker transitioned to CLOSED")
                else:
                    self._failure_count = 0
            return result
        except Exception:
            async with self._lock:
                self._failure_count += 1
                self._last_failure_time = time.time()
                if self._failure_count >= self.failure_threshold:
                    self._state = CircuitState.OPEN
                    logger.error(
                        "Circuit breaker transitioned to OPEN",
                        failure_count=self._failure_count,
                    )
                elif self._state == CircuitState.HALF_OPEN:
                    self._state = CircuitState.OPEN
                    logger.warning("Circuit breaker back to OPEN from HALF_OPEN")
            raise


class RedisUnavailableError(Exception):
    """Exception raised when Redis is unavailable."""

    pass


class RedisClient:
    """Enterprise Redis client with production-grade reliability."""

    def __init__(self, redis_url: str | None = None) -> None:
        settings = get_settings()
        self.redis_url = redis_url or settings.redis_url
        self._pool: aioredis.ConnectionPool[Any] | None = None
        self._client: aioredis.Redis[Any] | None = None
        self._fallback_store: dict[str, tuple[str, float]] = {}
        self._use_redis = False
        self.circuit_breaker = RedisCircuitBreaker(
            failure_threshold=5,
            recovery_timeout=30.0,
        )

    async def connect(self) -> None:
        """Establish Redis connection with retry."""
        try:
            pool_kwargs: dict[str, Any] = {
                "max_connections": get_settings().redis_pool_size,
                "socket_timeout": get_settings().redis_socket_timeout,
                "socket_connect_timeout": get_settings().redis_socket_connect_timeout,
                "retry_on_timeout": get_settings().redis_retry_on_timeout,
                "decode_responses": True,
            }
            if get_settings().redis_ssl:
                pool_kwargs["connection_class"] = aioredis.SSLConnection

            self._pool = aioredis.ConnectionPool.from_url(
                self.redis_url,
                **pool_kwargs,
            )
            self._client = aioredis.Redis(
                connection_pool=self._pool,
                decode_responses=True,
            )
            await self._client.ping()
            self._use_redis = True
            logger.info(
                "Redis connection established",
                url=self.redis_url.split("@")[-1] if "@" in self.redis_url else self.redis_url,
            )
        except Exception as e:
            self._use_redis = False
            self._client = None
            logger.warning(
                "Redis connection failed, using in-memory fallback",
                error=str(e),
            )

    async def disconnect(self) -> None:
        """Gracefully close Redis connections."""
        if self._client:
            try:
                await self._client.close()
            except Exception as e:
                logger.warning("Error closing Redis client", error=str(e))
        if self._pool:
            try:
                await self._pool.disconnect()
            except Exception as e:
                logger.warning("Error disconnecting Redis pool", error=str(e))
        self._use_redis = False
        self._client = None
        self._pool = None

    async def ping(self) -> bool:
        """Check Redis connectivity."""
        if not self._use_redis or not self._client:
            return bool(self._fallback_store)
        try:
            result = await self.circuit_breaker.call(self._client.ping)
            return bool(result)
        except Exception:
            return bool(self._fallback_store)

    @retry(
        retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        stop=stop_after_attempt(3),
    )
    async def get(self, key: str) -> str | None:
        """Get a string value from Redis."""
        if not self._use_redis or not self._client:
            return self._get_from_fallback(key)
        try:
            value: str | None = await self.circuit_breaker.call(self._client.get, key)
            return value
        except (RedisUnavailableError, Exception) as e:
            logger.warning("Redis get failed, using fallback", key=key, error=str(e))
            return self._get_from_fallback(key)

    @retry(
        retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        stop=stop_after_attempt(3),
    )
    async def set(
        self,
        key: str,
        value: str,
        ttl: int | None = None,
    ) -> bool:
        """Set a string value in Redis with optional TTL."""
        if not self._use_redis or not self._client:
            self._set_in_fallback(key, value, ttl)
            return True
        try:
            if ttl:
                await self.circuit_breaker.call(self._client.setex, key, ttl, value)
            else:
                await self.circuit_breaker.call(self._client.set, key, value)
            return True
        except (RedisUnavailableError, Exception) as e:
            logger.warning("Redis set failed, using fallback", key=key, error=str(e))
            self._set_in_fallback(key, value, ttl)
            return True

    async def get_json(self, key: str) -> dict[str, Any] | None:
        """Get and deserialize a JSON value from Redis."""
        value = await self.get(key)
        if value is None:
            return None
        try:
            res: dict[str, Any] = json.loads(value)
            return res
        except json.JSONDecodeError as e:
            logger.error("Failed to decode JSON from cache", key=key, error=str(e))
            return None

    async def set_json(
        self,
        key: str,
        value: dict[str, Any],
        ttl: int | None = 300,
    ) -> bool:
        """Serialize and set a JSON value in Redis."""
        try:
            serialized = json.dumps(value, default=str)
            return await self.set(key, serialized, ttl)
        except (TypeError, ValueError) as e:
            logger.error("Failed to serialize JSON for cache", key=key, error=str(e))
            return False

    @retry(
        retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        stop=stop_after_attempt(3),
    )
    async def delete(self, key: str) -> bool:
        """Delete a key from Redis."""
        if not self._use_redis or not self._client:
            self._fallback_store.pop(key, None)
            return True
        try:
            await self.circuit_breaker.call(self._client.delete, key)
            return True
        except (RedisUnavailableError, Exception) as e:
            logger.warning("Redis delete failed", key=key, error=str(e))
            self._fallback_store.pop(key, None)
            return True

    @retry(
        retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        stop=stop_after_attempt(3),
    )
    async def exists(self, key: str) -> bool:
        """Check if a key exists in Redis."""
        if not self._use_redis or not self._client:
            return key in self._fallback_store
        try:
            result = await self.circuit_breaker.call(self._client.exists, key)
            return bool(result)
        except (RedisUnavailableError, Exception) as e:
            logger.warning("Redis exists check failed", key=key, error=str(e))
            return key in self._fallback_store

    async def increment(self, key: str, amount: int = 1) -> int:
        """Increment a counter in Redis atomically."""
        if not self._use_redis or not self._client:
            current = int(self._fallback_store.get(key, ("0", 0))[0]) + amount
            self._fallback_store[key] = (str(current), time.time() + 86400)
            return current
        try:
            return int(await self.circuit_breaker.call(self._client.incrby, key, amount))
        except (RedisUnavailableError, Exception) as e:
            logger.warning("Redis increment failed", key=key, error=str(e))
            current = int(self._fallback_store.get(key, ("0", 0))[0]) + amount
            self._fallback_store[key] = (str(current), time.time() + 86400)
            return current

    async def get_ttl(self, key: str) -> int:
        """Get TTL of a key in seconds."""
        if not self._use_redis or not self._client:
            if key in self._fallback_store:
                remaining = self._fallback_store[key][1] - time.time()
                return max(0, int(remaining))
            return -2
        try:
            return int(await self.circuit_breaker.call(self._client.ttl, key))
        except (RedisUnavailableError, Exception):
            return -1

    async def acquire_lock(
        self,
        lock_name: str,
        timeout: int = 10,
        blocking: bool = True,
        blocking_timeout: int | None = None,
    ) -> bool:
        """Acquire a distributed lock."""
        if not self._use_redis or not self._client:
            return True
        try:
            lock = self._client.lock(
                lock_name,
                timeout=timeout,
                blocking=blocking,
                blocking_timeout=blocking_timeout,
            )
            acquired = await lock.acquire()
            return bool(acquired)
        except Exception as e:
            logger.warning("Failed to acquire lock", lock_name=lock_name, error=str(e))
            return True

    async def release_lock(self, lock_name: str) -> None:
        """Release a distributed lock."""
        if not self._use_redis or not self._client:
            return
        try:
            lock = self._client.lock(lock_name)
            await lock.release()
        except Exception as e:
            logger.warning("Failed to release lock", lock_name=lock_name, error=str(e))

    def _get_from_fallback(self, key: str) -> str | None:
        """Get value from in-memory fallback store."""
        if key in self._fallback_store:
            value, expires_at = self._fallback_store[key]
            if expires_at > time.time():
                return value
            del self._fallback_store[key]
        return None

    def _set_in_fallback(self, key: str, value: str, ttl: int | None = None) -> None:
        """Set value in in-memory fallback store."""
        expires_at = time.time() + (ttl if ttl else 3600)
        self._fallback_store[key] = (value, expires_at)
        if len(self._fallback_store) > 10000:
            self._cleanup_fallback()

    def _cleanup_fallback(self) -> None:
        """Clean up expired entries from fallback store."""
        now = time.time()
        expired_keys = [k for k, (_, exp) in self._fallback_store.items() if exp <= now]
        for key in expired_keys:
            del self._fallback_store[key]


async def get_redis_client() -> RedisClient:
    """Factory function to create and connect Redis client."""
    client = RedisClient()
    await client.connect()
    return client
