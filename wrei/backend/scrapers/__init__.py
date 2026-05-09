from .olx import search as olx_search
from .olx import available as olx_available
from .otodom import search as otodom_search
from .otodom import available as otodom_available

PORTAL_SCRAPERS = {
    "olx": olx_search,
    "otodom": otodom_search,
}

AVAILABLE_PORTALS = ["olx", "otodom"]
