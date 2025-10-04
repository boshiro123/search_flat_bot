from typing import List, Optional, Any
import logging
import json
from datetime import datetime
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

    # Попытка дернуть JSON из __NEXT_DATA__
    try:
        api_results = fetch_realt_via_json_from_html(resp.text)
        if api_results:
            return api_results
    except Exception as e:
        logger.warning("realt json extraction failed: %s", e)

    # Фолбэк на простой HTML разметки
    return parse_realt_html(resp.text)


def _extract_objects_from_html(html: str) -> Optional[list[Any]]:
    soup = BeautifulSoup(html, "lxml")
    script = soup.select_one("script#__NEXT_DATA__")
    if not script or not script.text:
        return None
    try:
        data = json.loads(script.text)
    except Exception:
        return None
    try:
        return (
            data.get("props", {})
            .get("pageProps", {})
            .get("initialState", {})
            .get("objectsListing", {})
            .get("objects")
        )
    except Exception:
        return None


def fetch_realt_via_json_from_html(html: str) -> List[Listing]:
    objects = _extract_objects_from_html(html)
    if not objects or not isinstance(objects, list):
        return []

    results: List[Listing] = []
    for obj in objects:
        obj_uuid = str(obj.get("code") or "")
        if not obj_uuid:
            continue
        url = f"https://realt.by/s/o/2/{obj_uuid}/"
        title = obj.get("title") or obj.get("headline")
        
        # Цена: price + priceCurrency=840 (USD)
        price_val = obj.get("price")
        price = normalize_price(price_val, default_currency="$")

        # Локация: address или streetName
        location = obj.get("address") or obj.get("streetName") or obj.get("townName")

        # Дата создания: createdAt
        created_at = None
        date_str = obj.get("createdAt") or obj.get("created_at")
        if date_str:
            try:
                created_at = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except Exception:
                pass

        results.append(
            Listing(
                source="realt",
                id=obj_uuid,
                url=url,
                title=title,
                price=price,
                location=location,
                created_at=created_at,
            )
        )

    return results

