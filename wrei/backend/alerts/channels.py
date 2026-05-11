"""
Alert Channels — wysyłanie powiadomień przez Telegram.
Dzienny digest z top okazjami + natychmiastowe alerty dla watchlist.
"""
import logging
import os
from datetime import date

import httpx

from backend.db import get_conn

logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def _send_telegram(text: str, parse_mode: str = "HTML") -> bool:
    """Wysyła wiadomość Telegram. Zwraca True jeśli sukces."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logger.debug("[Telegram] Brak tokenu/chat_id — pomijam wysyłkę")
        return False
    try:
        url = TELEGRAM_API.format(token=TELEGRAM_TOKEN)
        resp = httpx.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": False,
        }, timeout=10)
        if resp.status_code == 200:
            return True
        logger.warning("[Telegram] Błąd %d: %s", resp.status_code, resp.text[:200])
        return False
    except Exception as exc:
        logger.error("[Telegram] Wyjątek: %s", exc)
        return False


def _format_score_bar(score: float, width: int = 10) -> str:
    """Tworzy pasek postępu: ████░░░░░░ (np. dla score=0.4)"""
    filled = round(score * width)
    return "█" * filled + "░" * (width - filled)


def _format_listing_card(listing: dict, alert_name: str | None = None) -> str:
    """Formatuje kartę ogłoszenia jako HTML Telegram."""
    score = listing.get("score") or 0
    price = listing.get("price") or 0
    area = listing.get("area") or 0
    psm = listing.get("price_per_m2") or (price / area if area else 0)
    rcn = listing.get("rcn_benchmark")
    cagr = listing.get("cagr_5y")
    txn_gap = listing.get("transaction_gap") or 0

    # Nagłówek
    alert_line = f"🔔 <b>Alert: {alert_name}</b>\n" if alert_name else ""
    score_pct = round(score * 100)
    bar = _format_score_bar(score)

    # Podstawowe info
    lines = [
        alert_line,
        f"🏠 <b>{listing.get('title', 'Ogłoszenie')[:60]}</b>",
        f"📍 {listing.get('district', 'Warszawa')} | {listing.get('portal', '?').upper()}",
        f"",
        f"💰 <b>{price:,} PLN</b> ({psm:.0f} PLN/m²)",
        f"📐 {area} m² | {listing.get('rooms', '?')} pokoje",
        f"",
        f"⭐ Score: {score_pct}% {bar}",
    ]

    # Dane RCN
    if rcn:
        gap_sign = "✅ taniej" if txn_gap > 0 else "⚠️ drożej"
        gap_pct = abs(txn_gap * 100)
        lines += [
            f"📊 RCN benchmark: {rcn:.0f} PLN/m² ({gap_pct:.1f}% {gap_sign})",
        ]
    if cagr:
        trend_icon = "📈" if cagr > 0 else "📉"
        lines.append(f"{trend_icon} Trend 5Y CAGR: {cagr * 100:.1f}%/rok")

    # LLM summary
    llm = listing.get("llm_analysis")
    if llm and isinstance(llm, dict) and llm.get("summary"):
        lines += ["", f"💬 <i>{llm['summary'][:200]}</i>"]

    # Link
    url = listing.get("url", "")
    if url:
        lines += ["", f'🔗 <a href="{url}">Zobacz ogłoszenie</a>']

    return "\n".join(lines)


def send_alert_notification(alert: dict, listing: dict) -> bool:
    """Wysyła natychmiastowe powiadomienie dla dopasowanego alertu."""
    text = _format_listing_card(listing, alert_name=alert.get("name"))
    return _send_telegram(text)


def send_daily_digest():
    """
    Wysyła dzienny digest z top 5 okazjami dnia.
    Wywoływany przez scheduler codziennie o 8:00.
    """
    today = date.today().isoformat()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, url, title, price, area, rooms, district, portal,
               score, price_per_m2, direct_offer, condition,
               rcn_benchmark, cagr_5y, transaction_gap, llm_analysis
        FROM listings
        WHERE DATE(created_at) = %s
          AND score >= 0.15
        ORDER BY score DESC
        LIMIT 5
    """, (today,))
    cols = [d[0] for d in cur.description]
    top_listings = [dict(zip(cols, row)) for row in cur.fetchall()]
    cur.close()
    conn.close()

    if not top_listings:
        logger.info("[Digest] Brak nowych okazji dzisiaj (%s)", today)
        return

    # Nagłówek
    header = (
        f"🌅 <b>WREI — Dzienny Raport {today}</b>\n"
        f"Top {len(top_listings)} okazji z ostatnich 24h:\n"
        f"{'─' * 30}"
    )
    _send_telegram(header)

    for i, listing in enumerate(top_listings, 1):
        card = f"<b>#{i}</b>\n" + _format_listing_card(listing)
        _send_telegram(card)

    logger.info("[Digest] Wysłano %d kart okazji za %s", len(top_listings), today)
