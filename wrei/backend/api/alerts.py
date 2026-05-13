from fastapi import APIRouter, HTTPException, Query
from backend.db import get_alerts, get_watchlist, create_watchlist_item, delete_watchlist_item
from backend.api.schemas import AlertConfigSchema

router = APIRouter(prefix="/alerts", tags=["alerts"])

@router.get("")
async def fetch_triggered_alerts(limit: int = 50):
    return get_alerts(limit=limit)

@router.get("/watchlist")
async def fetch_watchlist(limit: int = 50):
    return get_watchlist(limit=limit)

@router.post("/watchlist")
async def add_alert_config(config: AlertConfigSchema):
    new_id = create_watchlist_item(config.dict())
    return {"status": "created", "id": new_id}

@router.delete("/watchlist/{item_id}")
async def remove_alert_config(item_id: int):
    success = delete_watchlist_item(item_id)
    if not success:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"status": "deleted"}
