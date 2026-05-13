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

import operator

logger = logging.getLogger(__name__)

# Map operator strings to operator functions
OPERATORS = {
    "gt":  operator.gt,
    "lt":  operator.lt,
    "ge":  operator.ge,
    "le":  operator.le,
    "eq":  operator.eq,
    "ne":  operator.ne,
    "in":  lambda x, y: x in y if isinstance(y, (list, tuple, set, str)) else False,
    "contains": lambda x, y: y in x if isinstance(x, (list, str)) else False,
}

def evaluate_condition(listing: dict, condition: dict | str) -> bool:
    """
    Safe evaluation of a condition. 
    Supports structured dict format: {"field": {"op": value}, "and": [...]}
    Or falls back to a very limited string parser for simple "field > value" cases.
    """
    if not condition:
        return True
    
    # If it's a string, try to parse it as JSON first
    if isinstance(condition, str):
        import json
        try:
            condition = json.loads(condition)
        except json.JSONDecodeError:
            # Legacy string fallback - very limited safety!
            # In production we should migrate all alerts to JSON.
            logger.warning("[Evaluator] Legacy string condition detected: %s. Please migrate to JSON.", condition)
            return _evaluate_legacy_string(listing, condition)

    if not isinstance(condition, dict):
        return False

    # Logic for structured JSON
    # Example: {"score": {"gt": 0.25}, "district": {"eq": "Mokotów"}}
    for field, rule in condition.items():
        if field == "and":
            if not all(evaluate_condition(listing, r) for r in rule):
                return False
            continue
        if field == "or":
            if not any(evaluate_condition(listing, r) for r in rule):
                return False
            continue

        val = listing.get(field)
        if isinstance(rule, dict):
            for op_name, threshold in rule.items():
                op_func = OPERATORS.get(op_name)
                if not op_func:
                    logger.error("[Evaluator] Unknown operator: %s", op_name)
                    return False
                try:
                    if not op_func(val, threshold):
                        return False
                except Exception as e:
                    logger.debug("[Evaluator] Comparison error for %s %s %s: %s", val, op_name, threshold, e)
                    return False
        else:
            # Default to equality
            if val != rule:
                return False
                
    return True

def _evaluate_legacy_string(listing: dict, expr: str) -> bool:
    """
    Extremely limited and safe string parser for legacy expressions.
    Only supports 'field op value' joined by 'and'.
    """
    parts = [p.strip() for p in expr.split(" and ")]
    for part in parts:
        match = re.match(r"(\w+)\s*([><!=]=?)\s*(.*)", part)
        if not match:
            logger.warning("[Evaluator] Could not parse legacy part: %s", part)
            return False
        field, op, val_str = match.groups()
        val_str = val_str.strip("'\" ")
        
        actual_val = listing.get(field)
        try:
            # Try to convert threshold to float if possible
            threshold = float(val_str) if '.' in val_str or val_str.isdigit() else val_str
        except ValueError:
            threshold = val_str
            
        op_map = {">": operator.gt, "<": operator.lt, ">=": operator.ge, "<=": operator.le, "==": operator.eq, "!=": operator.ne}
        op_func = op_map.get(op)
        if not op_func: return False
        
        try:
            if not op_func(actual_val, threshold): return False
        except Exception: return False
    return True


def get_watchlist_alerts() -> list[dict]:
    """Pobiera aktywne alerty z DB."""
    from backend.db import get_conn
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, name, condition_expr, condition_json, min_score, city_slug
            FROM watchlist
            WHERE active = TRUE
            ORDER BY id
        """)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def get_recent_listings_for_alerts(hours: int = 1, limit: int = 200) -> list[dict]:
    """Zwraca oferty dodane w ostatnich N godzinach (świeże)."""
    from backend.db import get_conn
    with get_conn() as conn:
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
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def mark_alert_sent(listing_id: int, watchlist_id: int) -> None:
    """Zapisuje że alert został wysłany (żeby nie wysyłać dwa razy)."""
    from backend.db import get_conn
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO alert_sent_log (listing_id, watchlist_id)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING
        """, (listing_id, watchlist_id))
        conn.commit()


def was_alert_sent(listing_id: int, watchlist_id: int) -> bool:
    """Sprawdza czy dla tej pary (listing, watchlist) alert już był wysłany."""
    from backend.db import get_conn
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT 1 FROM alert_sent_log
            WHERE listing_id = %s AND watchlist_id = %s
        """, (listing_id, watchlist_id))
        return cur.fetchone() is not None


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
            # Sprawdź warunek (preferuj JSON)
            condition = alert.get("condition_json") or alert.get("condition_expr") or ""
            if not evaluate_condition(listing, condition):
                continue
            # Sprawdź czy już wysłano
            if was_alert_sent(listing["id"], alert["id"]):
                continue
            matched.append(listing)

        for listing in matched[:5]:  # max 5 powiadomień per alert per run
            try:
                from backend.db import create_price_alert
                send_alert_notification(alert, listing)
                mark_alert_sent(listing["id"], alert["id"])
                # Log to price_alerts for UI history
                create_price_alert(
                    listing_id=listing["id"],
                    alert_type="new_high_score" if (listing.get("score") or 0) > 0.25 else "watchlist_match",
                    new_value=listing.get("price")
                )
            except Exception:
                logger.exception("[Alerts] Błąd wysyłania alertu %s dla %s", alert["name"], listing.get("url"))
