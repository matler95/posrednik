import asyncio
import json
import logging
import os
import uuid
from typing import AsyncGenerator
from arq import create_pool
from arq.connections import RedisSettings
from backend.db import get_hunt_config, get_hunt_job

logger = logging.getLogger(__name__)
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")

class JobStatus:
    PENDING     = "pending"
    RUNNING     = "running"
    ENRICHING   = "enriching"
    SAVING      = "saving"
    AI_ANALYSIS = "ai_analysis"
    DONE        = "done"
    ERROR       = "error"

class HuntJobManager:
    def __init__(self):
        self._redis_pool = None

    async def _get_redis(self):
        if self._redis_pool is None:
            self._redis_pool = await create_pool(RedisSettings(host=REDIS_HOST))
        return self._redis_pool

    async def start_job(self, config: dict):
        job_id = str(uuid.uuid4())
        redis = await self._get_redis()
        # Enqueue task in ARQ
        await redis.enqueue_job("run_hunt_job_task", job_id, config)
        
        # Return a dummy object for compatibility
        from dataclasses import dataclass
        @dataclass
        class SimpleJob:
            job_id: str
            status: str
        return SimpleJob(job_id=job_id, status=JobStatus.PENDING)

    @property
    def current_job(self):
        return None

hunt_manager = HuntJobManager()

async def stream_job_events(job_id: str) -> AsyncGenerator[str, None]:
    """Streams job events from Redis Pub/Sub."""
    redis_conn = await create_pool(RedisSettings(host=REDIS_HOST))
    pubsub = redis_conn.pubsub()
    channel_name = f"hunt_events:{job_id}"
    
    await pubsub.subscribe(channel_name)
    logger.info("[SSE] Subscribed to %s", channel_name)
    
    try:
        # First, send current status from DB
        job_db = get_hunt_job(job_id)
        if job_db:
            yield f"data: {json.dumps({'type': 'status', 'status': job_db['status'], 'message': 'Połączono z sesją.'})}\n\n"

        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=30.0)
            if message:
                data = message['data']
                yield f"data: {data.decode('utf-8') if isinstance(data, bytes) else data}\n\n"
                
                # Check for termination
                try:
                    event = json.loads(data)
                    if event.get("type") in ("done", "error"):
                        break
                except: pass
            else:
                yield 'data: {"type":"heartbeat"}\n\n'
    finally:
        await pubsub.unsubscribe(channel_name)
        await redis_conn.close()