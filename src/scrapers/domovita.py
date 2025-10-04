from typing import List
import logging
import requests
from bs4 import BeautifulSoup
from datetime import datetime

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

    # Ищем все контейнеры с объявлениями
    containers = soup.select("div.found_item[data-key]")
    results: List[Listing] = []
    seen_ids = set()
    
    for container in containers:
        # ID из data-key
        item_id = container.get("data-key")
        if not item_id or item_id in seen_ids:
            continue
        seen_ids.add(item_id)
        
        # Ссылка на объявление
        link = container.select_one("a.link-object, a.title--listing")
        if not link:
            continue
        href = link.get("href")
        if not href:
            continue
        full_url = href if href.startswith("http") else f"https://domovita.by{href}"
        
        # Заголовок
        title = link.get_text(strip=True) or None
        
        # Цена
        price = None
        price_el = container.select_one("div.price")
        if price_el:
            price = normalize_price(price_el.get_text(strip=True), default_currency="$")
        
        # Локация
        location = None
        loc_el = container.select_one("div.gr, [class*='address']")
        if loc_el:
            location = loc_el.get_text(strip=True) or None
        
        # Дата: формат "04.10.2025" в <div class="date">
        created_at = None
        date_el = container.select_one("div.date")
        if date_el:
            date_text = date_el.get_text(strip=True)
            try:
                # Парсим дату в формате DD.MM.YYYY
                created_at = datetime.strptime(date_text, "%d.%m.%Y")
            except Exception:
                pass
        
        results.append(
            Listing(
                source="domovita",
                id=item_id,
                url=full_url,
                title=title,
                price=price,
                location=location,
                created_at=created_at,
            )
        )

    return results


def fetch_domovita(url: str) -> List[Listing]:
    logger = logging.getLogger("scraper.domovita")
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return parse_domovita_html(resp.text)

