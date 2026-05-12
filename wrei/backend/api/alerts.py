from fastapi import APIRouter
from backend.db import get_alerts

router = APIRouter(prefix="/alerts", tags=["alerts"])

@router.get("")
async def fetch_alerts(limit: int = 50):
    return get_alerts(limit=limit)
