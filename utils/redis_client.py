import time
from typing import Optional

import redis
from redis import Redis

from config import settings

_redis_client: Optional[Redis] = None
MIN_ACTIVE_JOB_TTL_SECONDS = 60 * 60
_memory_cooldowns: dict[int, int] = {}
_memory_active_jobs: dict[int, dict[int, int]] = {}



def _now() -> int:
    return int(time.time())



def _cleanup_memory_state() -> None:
    now = _now()

    expired_users = [user_id for user_id, expires_at in _memory_cooldowns.items() if expires_at <= now]
    for user_id in expired_users:
        _memory_cooldowns.pop(user_id, None)

    empty_groups = []
    for group_id, jobs in _memory_active_jobs.items():
        expired_jobs = [download_id for download_id, expires_at in jobs.items() if expires_at <= now]
        for download_id in expired_jobs:
            jobs.pop(download_id, None)
        if not jobs:
            empty_groups.append(group_id)

    for group_id in empty_groups:
        _memory_active_jobs.pop(group_id, None)



def get_redis() -> Redis:
    """Get Redis client singleton."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=5,
        )
    return _redis_client



def set_cooldown(user_id: int, seconds: int) -> None:
    """Set cooldown for user."""
    if settings.DEV_MODE:
        _memory_cooldowns[user_id] = _now() + seconds
        return

    redis_client = get_redis()
    redis_client.setex(f"cooldown:user:{user_id}", seconds, "1")



def check_cooldown(user_id: int) -> bool:
    """Check if user is in cooldown."""
    if settings.DEV_MODE:
        _cleanup_memory_state()
        return user_id in _memory_cooldowns

    redis_client = get_redis()
    return redis_client.exists(f"cooldown:user:{user_id}") > 0



def get_active_jobs(group_id: int) -> int:
    """Get count of active jobs for a group after expiring stale entries."""
    if settings.DEV_MODE:
        _cleanup_memory_state()
        return len(_memory_active_jobs.get(group_id, {}))

    redis_client = get_redis()
    key = f"jobs:group:{group_id}"
    now = _now()
    pipe = redis_client.pipeline()
    pipe.zremrangebyscore(key, "-inf", now)
    pipe.zcard(key)
    _, active_count = pipe.execute()
    return int(active_count or 0)



def register_active_job(group_id: int, download_id: int, ttl_seconds: int) -> None:
    """Track a job with expiry so crashes cannot block the group forever."""
    if settings.DEV_MODE:
        _cleanup_memory_state()
        group_jobs = _memory_active_jobs.setdefault(group_id, {})
        group_jobs[download_id] = _now() + max(ttl_seconds, MIN_ACTIVE_JOB_TTL_SECONDS)
        return

    redis_client = get_redis()
    key = f"jobs:group:{group_id}"
    now = _now()
    expires_at = now + max(ttl_seconds, MIN_ACTIVE_JOB_TTL_SECONDS)
    pipe = redis_client.pipeline()
    pipe.zremrangebyscore(key, "-inf", now)
    pipe.zadd(key, {str(download_id): expires_at})
    pipe.expire(key, expires_at - now)
    pipe.execute()



def clear_active_job(group_id: int, download_id: int) -> None:
    """Remove a tracked job after completion or queue failure."""
    if settings.DEV_MODE:
        jobs = _memory_active_jobs.get(group_id)
        if not jobs:
            return
        jobs.pop(download_id, None)
        if not jobs:
            _memory_active_jobs.pop(group_id, None)
        return

    redis_client = get_redis()
    key = f"jobs:group:{group_id}"
    now = _now()
    pipe = redis_client.pipeline()
    pipe.zrem(key, str(download_id))
    pipe.zremrangebyscore(key, "-inf", now)
    pipe.zcard(key)
    _, _, remaining = pipe.execute()

    if not remaining:
        redis_client.delete(key)
