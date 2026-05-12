from .olx import search as olx_search, available as olx_available
from .otodom import search as otodom_search, available as otodom_available
from .morizon import search as morizon_search, available as morizon_available
from .gratka import search as gratka_search, available as gratka_available
from .domiporta import search as domiporta_search, available as domiporta_available
from .nieruchomosci_online import search as no_search, available as no_available

PORTAL_SCRAPERS = {
    "olx": olx_search,
    "otodom": otodom_search,
    # "morizon": morizon_search,  # Wyłączone - błędy 403 / brak JSON API
    # "gratka": gratka_search,   # Wyłączone - błędy 403 / brak JSON API
    "domiporta": domiporta_search,
    "nieruchomosci_online": no_search,
}

AVAILABLE_PORTALS = list(PORTAL_SCRAPERS.keys())