from fastapi import APIRouter, HTTPException, Query
from backend.db import (
    get_listings, get_new_listings, get_listing_by_id, 
    get_listing_price_history, save_llm_analysis
)

router = APIRouter(prefix="/listings", tags=["listings"])

def _serialize(obj: dict) -> dict:
    out = {}
    for k, v in obj.items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out

@router.get("")
async def listings_endpoint(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    min_score: float = Query(None),
    portal: str = Query(None),
    district: str = Query(None),
    direct_only: bool = Query(False),
    min_price: int = Query(None),
    max_price: int = Query(None),
    min_area: float = Query(None),
    max_area: float = Query(None),
):
    rows = get_listings(
        limit=limit, offset=offset, min_score=min_score,
        portal=portal, district=district, direct_only=direct_only,
        min_price=min_price, max_price=max_price,
        min_area=min_area, max_area=max_area,
    )
    return {"count": len(rows), "listings": [_serialize(r) for r in rows]}

@router.get("/new")
async def listings_new(hours: int = Query(24, ge=1, le=168)):
    rows = get_new_listings(hours=hours)
    return {"count": len(rows), "listings": [_serialize(r) for r in rows]}

@router.get("/{listing_id}")
async def listing_detail(listing_id: int):
    listing = get_listing_by_id(listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    history = get_listing_price_history(listing.get("url", ""))
    return {**_serialize(listing), "price_history": [_serialize(h) for h in history]}

@router.post("/{listing_id}/analyze")
async def trigger_ai_analysis(listing_id: int):
    from backend.nlp.llm_scorer import analyze_listing_with_llm
    listing = get_listing_by_id(listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    analysis = await analyze_listing_with_llm(listing)
    if analysis:
        save_llm_analysis(listing["url"], analysis)
        return {"status": "done", "analysis": analysis}
    return {"status": "error", "message": "Analiza nie powiodła się (sprawdź Ollama)"}
