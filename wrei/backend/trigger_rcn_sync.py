import asyncio
import os
from arq import create_pool
from arq.connections import RedisSettings

async def trigger():
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    print(f"Connecting to Redis at {REDIS_HOST}...")
    redis = await create_pool(RedisSettings(host=REDIS_HOST))
    
    city = "warszawa"
    print(f"Enqueuing full RCN sync for {city}...")
    
    # Przekazujemy city_slug i opcjonalnie lata (choć nowa wersja ignoruje lata i leci po wszystkich kwartałach od 2006)
    job = await redis.enqueue_job('import_rcn_history_task', city, 20)
    
    print(f"Job enqueued: {job.job_id}")
    await redis.close()
    print("Done. You can check the logs with 'docker logs -f wrei-worker-1'")

if __name__ == "__main__":
    asyncio.run(trigger())
