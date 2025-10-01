from typing import List
import logging
import requests
from bs4 import BeautifulSoup

from ..models import Listing
from ..utils import normalize_price


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
}


def _extract_id_from_url(url: str) -> str:
    # На Realt id присутствует как число в конце URL перед слэшем
    parts = [p for p in url.split("/") if p]
    last = parts[-1]
    return ''.join(ch for ch in last if ch.isdigit()) or last


def parse_realt_html(html: str) -> List[Listing]:
    soup = BeautifulSoup(html, "lxml")

    # Карточки объявлений
    cards = soup.select("a[href*='/rent/flat-for-long/']") or soup.select("a.card-btn")
    results: List[Listing] = []
    seen = set()
    for a in cards:
        href = a.get("href")
        if not href:
            continue
        if href in seen:
            continue
        seen.add(href)
        full_url = href if href.startswith("http") else f"https://realt.by{href}"
        item_id = _extract_id_from_url(full_url)

        title = a.get_text(strip=True) or None
        parent = a.find_parent()
        price = None
        location = None
        if parent:
            price_el = parent.select_one("[class*='price'], [data-price]")
            if price_el:
                price = normalize_price(price_el.get_text(strip=True), default_currency="$")
            loc_el = parent.select_one("[class*='address'], [data-address]")
            if loc_el:
                location = loc_el.get_text(strip=True) or None

        results.append(
            Listing(
                source="realt",
                id=item_id,
                url=full_url,
                title=title,
                price=price,
                location=location,
            )
        )

    return results


def fetch_realt(url: str) -> List[Listing]:
    logger = logging.getLogger("scraper.realt")
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return parse_realt_html(resp.text)

