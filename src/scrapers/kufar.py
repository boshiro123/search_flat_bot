from typing import Iterable, List
import requests
from bs4 import BeautifulSoup

from ..models import Listing


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
}


def _extract_id_from_url(url: str) -> str:
    # На Kufar id обычно в конце URL: /item/{id}
    parts = [p for p in url.split("/") if p]
    return parts[-1].split("?")[0]


def fetch_kufar(url: str) -> List[Listing]:
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    cards: Iterable = soup.select("a[data-name='adLink'], a.SerpItem_link__") or soup.select("a[href*='/item/']")
    results: List[Listing] = []
    for a in cards:
        href = a.get("href")
        if not href:
            continue
        full_url = href if href.startswith("http") else f"https://re.kufar.by{href}"
        item_id = _extract_id_from_url(full_url)

        title_el = a.get_text(strip=True) or None
        # Попытка найти цену рядом
        parent = a.find_parent()
        price_text = None
        location_text = None
        if parent:
            price_el = parent.select_one("[data-name='price'], span, div:contains('$')")
            if price_el:
                price_text = price_el.get_text(strip=True) or None
            loc_el = parent.select_one("[data-name='location'], span, div")
            if loc_el:
                location_text = loc_el.get_text(strip=True) or None

        results.append(
            Listing(
                source="kufar",
                id=item_id,
                url=full_url,
                title=title_el,
                price=price_text,
                location=location_text,
            )
        )

    return results

