"""
Alert Evaluator — sprawdza warunki alertów i zwraca dopasowane oferty.

Alerty przechowywane w tabeli `watchlist` (DB):
  - name: nazwa alertu
  - condition_expr: wyrażenie Python (safe eval) np. "score > 0.3 and district == 'Mokotów'"
  - min_score: szybki filtr DB
  - active: czy alert aktywny

Dostępne zmienne w wyrażeniu:
  score, price, price_per_m2, area, rooms, district, direct_offer,
  rcn_benchmark, cagr_5y, transaction_gap, text_score, photo_score,
  days_on_market, portal, condition
"""
import logging
import re

logger = logging.getLogger(__name__)

# Dozwolone nazwy w wyrażeniu alert condition
SAFE_NAMES = {
    "score", "price", "price_per_m2", "area", "rooms", "district",
    "direct_offer", "rcn_benchmark", "cagr_5y", "transaction_gap",
    "text_score", "photo_score", "days_on_market", "portal", "condition",
    "True", "False", "None", "and", "or", "not", "in",
}

# Niedozwolone wzorce (bezpieczeństwo)
FORBIDDEN_PATTERNS = [
    r"__", r"import", r"exec", r"eval", r"open", r"os\.", r"sys\.",
    r"subprocess", r"socket", r"lambda", r"class ", r"def ",
]


def is_safe_expression(expr: str) -> bool:
    """Sprawdza czy wyrażenie zawiera tylko bezpieczne konstrukcje."""
    for pat in FORBIDDEN_PATTERNS:
        if re.search(pat, expr):
            return False
    return True


def evaluate_condition(listing: dict, condition_expr: str) -> bool:
    """
    Bezpieczna ocena wyrażenia warunkowego dla danej oferty.
    Zwraca True jeśli warunek spełniony.
    """
    if not condition_expr or not condition_expr.strip():
        return True
    if not is_safe_expression(condition_expr):
        logger.warning("[Evaluator] Niebezpieczne wyrażenie: %s", condition_expr)
        return False

    # Spłaszcz wartości liczbowe z None → 0
    context = {
        "score":           float(listing.get("score") or 0),
        "price":           int(listing.get("price") or 0),
        "price_per_m2":    float(listing.get("price_per_m2") or 0),
        "area":            float(listing.get("area") or 0),
        "rooms":           str(listing.get("rooms") or ""),
        "district":        str(listing.get("district") or ""),
        "direct_offer":    bool(listing.get("direct_offer")),
        "rcn_benchmark":   float(listing.get("rcn_benchmark") or 0),
        "cagr_5y":         float(listing.get("cagr_5y") or 0),
        "transaction_gap": float(listing.get("transaction_gap") or 0),
        "text_score":      float(listing.get("text_score") or 0),
        "photo_score":     float(listing.get("photo_score") or 0),
        "days_on_market":  int(listing.get("days_on_market") or 0),
        "portal":          str(listing.get("portal") or ""),
        "condition":       str(listing.get("condition") or ""),
        # builtins wyłączone
        "__builtins__":    {},
    }

    try:
        return bool(eval(condition_expr, {"__builtins__": {}}, context))  # noqa: S307
    except Exception as exc:
        logger.debug("[Evaluator] Błąd eval '%s': %s", condition_expr, exc)
        return False


def get_watchlist_alerts() -> list[dict]:
    """Pobiera aktywne alerty z DB."""
    from backend.db import get_conn
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, name, condition_expr, min_score, city_slug
        FROM watchlist
        WHERE active = TRUE
        ORDER BY id
    """)
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    cur.close()
    conn.close()
    return rows


def get_recent_listings_for_alerts(hours: int = 1, limit: int = 200) -> list[dict]:
    """Zwraca oferty dodane w ostatnich N godzinach (świeże)."""
    from backend.db import get_conn
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, url, title, price, area, rooms, district, portal,
               score, price_per_m2, direct_offer, condition, days_on_market,
               rcn_benchmark, cagr_5y, transaction_gap, text_score, photo_score,
               llm_analysis, images
        FROM listings
        WHERE created_at >= NOW() - INTERVAL '%s hours'
          AND score IS NOT NULL
        ORDER BY score DESC
        LIMIT %s
    """, (hours, limit))
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    cur.close()
    conn.close()
    return rows


def mark_alert_sent(listing_id: int, watchlist_id: int) -> None:
    """Zapisuje że alert został wysłany (żeby nie wysyłać dwa razy)."""
    from backend.db import get_conn
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO alert_sent_log (listing_id, watchlist_id)
        VALUES (%s, %s)
        ON CONFLICT DO NOTHING
    """, (listing_id, watchlist_id))
    conn.commit()
    cur.close()
    conn.close()


def was_alert_sent(listing_id: int, watchlist_id: int) -> bool:
    """Sprawdza czy dla tej pary (listing, watchlist) alert już był wysłany."""
    from backend.db import get_conn
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT 1 FROM alert_sent_log
        WHERE listing_id = %s AND watchlist_id = %s
    """, (listing_id, watchlist_id))
    exists = cur.fetchone() is not None
    cur.close()
    conn.close()
    return exists


def run_alert_check():
    """
    Główna funkcja wywoływana przez scheduler co 15 min.
    Sprawdza wszystkie aktywne alerty i wysyła powiadomienia.
    """
    from backend.alerts.channels import send_alert_notification

    alerts = get_watchlist_alerts()
    if not alerts:
        return

    listings = get_recent_listings_for_alerts(hours=1)
    if not listings:
        return

    logger.info("[Alerts] Sprawdzam %d alertów dla %d ofert", len(alerts), len(listings))

    for alert in alerts:
        matched = []
        for listing in listings:
            # Szybki filtr score
            if (alert.get("min_score") or 0) > (listing.get("score") or 0):
                continue
            # Filtr miasto
            if alert.get("city_slug") and listing.get("city_slug") != alert["city_slug"]:
                continue
            # Sprawdź warunek
            if not evaluate_condition(listing, alert.get("condition_expr") or ""):
                continue
            # Sprawdź czy już wysłano
            if was_alert_sent(listing["id"], alert["id"]):
                continue
            matched.append(listing)

        for listing in matched[:5]:  # max 5 powiadomień per alert per run
            try:
                send_alert_notification(alert, listing)
                mark_alert_sent(listing["id"], alert["id"])
            except Exception:
                logger.exception("[Alerts] Błąd wysyłania alertu %s dla %s", alert["name"], listing.get("url"))
