"""
Analizator trendów cenowych — oblicza CAGR, benchmarki i momentum
na podstawie danych transakcyjnych z RCN (Deweloperuch).
"""
import logging
from statistics import median

logger = logging.getLogger(__name__)


def get_rcn_benchmark(
    city_slug: str,
    district: str | None = None,
    rooms: int | str | None = None,
    area: float | None = None,
    last_quarters: int = 2,
) -> float | None:
    # Normalizacja pokoi
    if isinstance(rooms, str):
        mapping = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5}
        rooms = mapping.get(rooms.upper(), 1) if not rooms.isdigit() else int(rooms)

    from backend.db import get_conn
    conn = get_conn()
    cur = conn.cursor()

    # Wyznacz zakres kwartałów
    cur.execute("SELECT MAX(year), MAX(quarter) FROM transaction_prices WHERE city_slug = %s", (city_slug,))
    row = cur.fetchone()
    if not row or not row[0]:
        cur.close(); conn.close(); return None
    
    max_year, max_qtr = row
    quarters = []
    y, q = max_year, max_qtr
    for _ in range(last_quarters):
        quarters.append((y, q))
        q -= 1
        if q == 0: q = 4; y -= 1
    
    qtr_cond = " OR ".join(["(year=%s AND quarter=%s)"] * len(quarters))
    params = [p for pair in quarters for p in pair]

    def _fetch(extra_where: str, extra_params: list) -> float | None:
        where = f"city_slug = %s AND is_flipped = FALSE AND ({qtr_cond})"
        all_params = [city_slug] + params + extra_params
        if extra_where: where += f" AND {extra_where}"
        cur.execute(f"SELECT amount_sqm FROM transaction_prices WHERE {where} AND amount_sqm > 1000", all_params)
        values = [r[0] for r in cur.fetchall()]
        if len(values) >= 5: return round(median(values), 2)
        return None

    # Strategia: od najbardziej szczegółowej do ogólnej
    result = None
    # 1. Dzielnica + Pokoje + Metraż (+/- 15%)
    if district and rooms and area:
        result = _fetch("district = %s AND rooms_number = %s AND area BETWEEN %s AND %s", 
                        [district, rooms, area * 0.85, area * 1.15])
    # 2. Dzielnica + Metraż
    if result is None and district and area:
        result = _fetch("district = %s AND area BETWEEN %s AND %s", [district, area * 0.85, area * 1.15])
    # 3. Dzielnica + Pokoje
    if result is None and district and rooms:
        result = _fetch("district = %s AND rooms_number = %s", [district, rooms])
    # 4. Sama dzielnica
    if result is None and district:
        result = _fetch("district = %s", [district])
    # 5. Całe miasto + Metraż
    if result is None and area:
        result = _fetch("area BETWEEN %s AND %s", [area * 0.85, area * 1.15])
    
    cur.close(); conn.close()
    return result



def compute_cagr(
    city_slug: str,
    district: str | None = None,
    years: int = 5,
) -> float | None:
    """
    Oblicza CAGR (Compound Annual Growth Rate) ceny/m² za ostatnie N lat.
    Porównuje ten sam kwartał (Q4) rok do roku, żeby wyeliminować sezonowość.
    Zwraca wartość dziesiętną, np. 0.08 = 8% rocznie.
    """
    from backend.db import get_conn

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT MAX(year) FROM transaction_prices WHERE city_slug = %s
    """, (city_slug,))
    row = cur.fetchone()
    if not row or not row[0]:
        cur.close(); conn.close()
        return None

    max_year = row[0]
    start_year = max_year - years

    def _median_for_year(year: int, quarter: int = 4) -> float | None:
        where = "city_slug = %s AND year = %s AND quarter = %s AND is_flipped = FALSE"
        params = [city_slug, year, quarter]
        if district:
            where += " AND district = %s"
            params.append(district)
        cur.execute(f"""
            SELECT amount_sqm FROM transaction_prices WHERE {where}
        """, params)
        values = [r[0] for r in cur.fetchall() if r[0] and r[0] > 1000]
        if len(values) >= 5:
            return median(values)
        return None

    # Spróbuj Q4, fallback Q3, Q2, Q1 jeśli brak
    p_end = p_start = None
    for q in [4, 3, 2, 1]:
        p_end = p_end or _median_for_year(max_year, q)
        p_start = p_start or _median_for_year(start_year, q)

    cur.close(); conn.close()

    if not p_end or not p_start or p_start <= 0:
        return None

    cagr = (p_end / p_start) ** (1 / years) - 1
    return round(cagr, 4)


def get_quarterly_trend(
    city_slug: str,
    district: str | None = None,
    last_n: int = 20,
) -> list[dict]:
    """
    Zwraca listę mediany ceny/m² per kwartał (ostatnie N kwartałów),
    posortowane rosnąco wg daty. Używane do wykresów w dashboardzie.
    """
    from backend.db import get_conn

    conn = get_conn()
    cur = conn.cursor()

    where = "city_slug = %s AND is_flipped = FALSE"
    params: list = [city_slug]
    if district:
        where += " AND district = %s"
        params.append(district)

    cur.execute(f"""
        SELECT year, quarter,
               PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY amount_sqm) AS median_sqm,
               COUNT(*) AS cnt
        FROM transaction_prices
        WHERE {where} AND amount_sqm > 1000
        GROUP BY year, quarter
        HAVING COUNT(*) >= 5
        ORDER BY year DESC, quarter DESC
        LIMIT %s
    """, params + [last_n])

    rows = []
    for year, quarter, med, cnt in cur.fetchall():
        rows.append({
            "year": year,
            "quarter": quarter,
            "label": f"{year} Q{quarter}",
            "median_sqm": round(float(med), 2) if med else None,
            "count": int(cnt),
        })

    cur.close(); conn.close()
    return list(reversed(rows))  # chronologicznie rosnąco


def get_offer_vs_transaction_gap(
    city_slug: str,
    district: str | None = None,
) -> float | None:
    """
    Zwraca różnicę procentową między mediną ofertową (listings) a transakcyjną (RCN).
    Wartość dodatnia = oferty droższe niż realne transakcje (typowe, bo są negocjacje).
    Wartość > 15% sugeruje rynek z dużym potencjałem negocjacji.
    """
    from backend.db import get_conn

    conn = get_conn()
    cur = conn.cursor()

    # Ceny ofertowe (z listings)
    where_off = "price_per_m2 IS NOT NULL"
    params_off: list = []
    if district:
        where_off += " AND district = %s"
        params_off.append(district)
    cur.execute(f"SELECT price_per_m2 FROM listings WHERE {where_off}", params_off)
    offer_vals = [r[0] for r in cur.fetchall() if r[0] and r[0] > 1000]

    cur.close(); conn.close()

    rcn = get_rcn_benchmark(city_slug, district)
    if not rcn or not offer_vals:
        return None

    offer_median = median(offer_vals)
    return round((offer_median - rcn) / rcn, 4)  # np. 0.12 = 12% drożej niż transakcje
