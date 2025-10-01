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
    # На Domovita обычно формат /flats/rent/{city}/{slug}-{id}
    tail = url.split("-")[-1]
    return tail.strip("/")


def parse_domovita_html(html: str) -> List[Listing]:
    soup = BeautifulSoup(html, "lxml")

    cards = soup.select("a[href*='/rent/']")
    results: List[Listing] = []
    seen_urls = set()
    for a in cards:
        href = a.get("href")
        if not href or href in seen_urls:
            continue
        seen_urls.add(href)
        full_url = href if href.startswith("http") else f"https://domovita.by{href}"
        item_id = _extract_id_from_url(full_url)

        # Заголовок и цена часто рядом
        title = a.get_text(strip=True) or None
        parent = a.find_parent()
        price = None
        location = None
        if parent:
            price_el = parent.select_one("[class*='price'], [data-qa='price']")
            if price_el:
                price = normalize_price(price_el.get_text(strip=True), default_currency="$")
            loc_el = parent.select_one("[class*='address'], [data-qa='address']")
            if loc_el:
                location = loc_el.get_text(strip=True) or None

        results.append(
            Listing(
                source="domovita",
                id=item_id,
                url=full_url,
                title=title,
                price=price,
                location=location,
            )
        )

    return results


def fetch_domovita(url: str) -> List[Listing]:
    logger = logging.getLogger("scraper.domovita")
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return parse_domovita_html(resp.text)

