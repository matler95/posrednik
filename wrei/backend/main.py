from fastapi import FastAPI, HTTPException, Query
from backend.analysis import enrich_listings, find_opportunities
from backend.db import init_db, save_listings
from backend.scheduler import start_scheduler, crawl_all_sources
from backend.scraper import available_portals, search

app = FastAPI(
    title="WREI Warszawa",
    description="Aplikacja do wyszukiwania ofert sprzedaży nieruchomości w Warszawie i identyfikowania okazji cenowych.",
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/portals")
def get_portals():
    return {"portals": available_portals()}


@app.get("/search")
def search_listings(
    query_url: str | None = Query(None, description="Pełny adres wyszukiwania w Otodom dla Warszawy."),
    portals: str = Query("otodom", description="Lista portali do przeszukania, np. otodom,olx."),
    pages: int = Query(1, ge=1, description="Liczba stron do przeszukania na portalu."),
    min_price: int | None = Query(None, ge=0, description="Minimalna cena oferty."),
    max_price: int | None = Query(None, ge=0, description="Maksymalna cena oferty."),
    min_area: int | None = Query(None, ge=0, description="Minimalny metraż w m2."),
    max_area: int | None = Query(None, ge=0, description="Maksymalny metraż w m2."),
    rooms: str | None = Query(None, description="Liczba pokoi, np. 2 lub 3-4."),
    direct_only: bool = Query(False, description="Tylko oferty bezpośrednie, bez biura nieruchomości."),
    threshold: float = Query(0.15, ge=0, le=1, description="Próg okazji jako ułamek wartości."),
):
    try:
        listings = search(
            query_url=query_url,
            portals=portals,
            min_price=min_price,
            max_price=max_price,
            min_area=min_area,
            max_area=max_area,
            rooms=rooms,
            pages=pages,
            direct_only=direct_only,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    enriched = enrich_listings(listings)
    opportunities = find_opportunities(enriched, threshold)
    return {
        "query_url": query_url,
        "filters": {
            "portals": portals,
            "pages": pages,
            "min_price": min_price,
            "max_price": max_price,
            "min_area": min_area,
            "max_area": max_area,
            "rooms": rooms,
            "direct_only": direct_only,
            "threshold": threshold,
        },
        "total_listings": len(enriched),
        "listings": enriched,
        "opportunities": opportunities,
    }


@app.post("/run-crawl")
def run_crawl(
    portals: str = Query("otodom", description="Lista portali do przeszukania, np. otodom,olx."),
    pages: int = Query(1, ge=1, description="Liczba stron do przeszukania na portalu."),
    min_price: int | None = Query(None, ge=0, description="Minimalna cena oferty."),
    max_price: int | None = Query(None, ge=0, description="Maksymalna cena oferty."),
    min_area: int | None = Query(None, ge=0, description="Minimalny metraż w m2."),
    max_area: int | None = Query(None, ge=0, description="Maksymalny metraż w m2."),
    rooms: str | None = Query(None, description="Liczba pokoi, np. 2 lub 3-4."),
    direct_only: bool = Query(False, description="Tylko oferty bezpośrednie, bez biura nieruchomości."),
):
    try:
        listings = search(
            portals=portals,
            min_price=min_price,
            max_price=max_price,
            min_area=min_area,
            max_area=max_area,
            rooms=rooms,
            pages=pages,
            direct_only=direct_only,
        )
        save_listings(listings)
        return {"status": "ok", "saved": len(listings)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.on_event("startup")
def on_startup():
    init_db()
    start_scheduler()
