from typing import Iterable, List, Optional, Any
import logging
import json
from urllib.parse import urlencode
from datetime import datetime
import requests
from bs4 import BeautifulSoup

from ..models import Listing
from ..utils import normalize_price


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
}


def _extract_id_from_url(url: str) -> str:
    # На Kufar id обычно в конце URL: /item/{id}
    parts = [p for p in url.split("/") if p]
    return parts[-1].split("?")[0]


def parse_kufar_html(html: str) -> List[Listing]:
    soup = BeautifulSoup(html, "lxml")
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


def fetch_kufar(url: str) -> List[Listing]:
    logger = logging.getLogger("scraper.kufar")
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    # Попытка дернуть официальный API через __NEXT_DATA__ → queryForBe
    try:
        api_results = fetch_kufar_via_api_from_html(resp.text, page_url=url)
        if api_results:
            return api_results
    except Exception as e:
        logger.warning("kufar api extraction failed: %s", e)

    # Фолбэк на простой HTML разметки (если сервер всё же отдал ссылки)
    return parse_kufar_html(resp.text)


def _extract_query_for_be_from_html(html: str) -> Optional[dict[str, Any]]:
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
            .get("initialState", {})
            .get("router", {})
            .get("queryForBe")
        )
    except Exception:
        return None


def fetch_kufar_via_api_from_html(html: str, page_url: str) -> List[Listing]:
    query = _extract_query_for_be_from_html(html)
    if not query or not isinstance(query, dict):
        return []
    qs = urlencode(query)
    api_url = f"https://api.kufar.by/search-api/v1/search/rendered-paginated?{qs}"

    headers = dict(HEADERS)
    headers.update({
        "Accept": "application/json, text/plain, */*",
        "Referer": page_url,
    })
    resp = requests.get(api_url, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    ads = (
        data.get("ads")
        or (data.get("result") or {}).get("ads")
        or data.get("items")
        or []
    )

    results: List[Listing] = []
    for ad in ads:
        ad_id = str(ad.get("ad_id") or ad.get("id") or ad.get("adId") or "")
        if not ad_id:
            continue
        url = (
            ad.get("ad_link")
            or ad.get("url")
            or f"https://re.kufar.by/vi/{ad_id}"
        )
        title = ad.get("subject") or ad.get("title")

        # Цена может быть числом, строкой или объектом
        price_val = ad.get("price") or ad.get("price_usd") or ad.get("price_byn") or ad.get("price_byr")
        price = normalize_price(price_val, default_currency="$")

        location = (
            ad.get("region_name")
            or ad.get("location")
            or ad.get("settlement")
            or ad.get("region")
        )

        # Дата создания: list_time или created_at
        created_at = None
        date_str = ad.get("list_time") or ad.get("created_at") or ad.get("listTime")
        if date_str:
            try:
                # Формат ISO: 2025-10-01T20:22:05+03:00 или timestamp
                if isinstance(date_str, (int, float)):
                    created_at = datetime.fromtimestamp(date_str)
                else:
                    created_at = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except Exception:
                pass

        results.append(
            Listing(
                source="kufar",
                id=ad_id,
                url=url,
                title=title,
                price=price,
                location=location,
                created_at=created_at,
            )
        )

    return results

