import os
import sys
import asyncio
import logging

# Dodaj ścieżkę do backendu
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.db import init_db, get_conn
from backend.hunt_manager import run_hunt_async

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("integration_test")

async def test_hunt_flow():
    logger.info("Starting integration test...")
    
    # 1. Init DB
    logger.info("Initializing database...")
    init_db()
    
    # 2. Check if we have any portals configured
    from backend.scrapers import AVAILABLE_PORTALS
    if not AVAILABLE_PORTALS:
        logger.error("No portals available!")
        return False
        
    logger.info(f"Available portals: {AVAILABLE_PORTALS}")
    
    # 3. Run a minimal hunt (1 page per portal)
    logger.info("Running a minimal hunt (1 page per portal)...")
    config = {
        "min_price": 0,
        "max_price": 99999999,
        "min_area": 0,
        "max_area": 1000,
        "districts": [],
        "rooms": [],
        "direct_only": False,
        "portals": AVAILABLE_PORTALS[:2] # Weź dwa pierwsze dla testu
    }
    
    # Symulujemy SSE generator
    results_count = 0
    async for event in run_hunt_async(config, pages_per_portal=1):
        if event.get("event") == "listing_saved":
            results_count += 1
            
    logger.info(f"Hunt finished. Saved {results_count} listings.")
    
    # 4. Verify listings in DB
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM listings")
    count = cur.fetchone()[0]
    cur.close()
    conn.close()
    
    logger.info(f"Total listings in DB: {count}")
    
    if count > 0:
        logger.info("SUCCESS: Listings found in DB.")
        return True
    else:
        logger.error("FAILURE: No listings found in DB.")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_hunt_flow())
    sys.exit(0 if success else 1)
