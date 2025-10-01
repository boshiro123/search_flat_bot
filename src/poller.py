from datetime import datetime
from typing import List
import logging
import time

from .config import load_config
from .state import StateStore
from .bot import BotApp
from .scrapers.kufar import fetch_kufar, parse_kufar_html
from .scrapers.domovita import fetch_domovita, parse_domovita_html
from .scrapers.realt import fetch_realt, parse_realt_html
from .browser import fetch_rendered_html


async def poll_once(state: StateStore, bot: BotApp) -> None:
    logger = logging.getLogger("poller")
    t0 = time.perf_counter()
    cfg = load_config()
    logger.info("cycle start")

    # Первый запуск: прогреваем кэш и выходим без рассылки
    if not state.seen_ids_by_source:
        for src, url, fetch in (
            ("kufar", cfg.kufar_url, fetch_kufar),
            ("domovita", cfg.domovita_url, fetch_domovita),
            ("realt", cfg.realt_url, fetch_realt),
        ):
            try:
                items = fetch(url)
                state.mark_seen(src, {i.id for i in items})
                logger.info("warmup %s: fetched=%d", src, len(items))
            except Exception as e:
                logger.warning("warmup %s failed: %s", src, e)
        logger.info("warmup done")
        return

    new_items: List = []
    kufar_fetched = 0
    kufar_new = 0

    try:
        kufar_items = fetch_kufar(cfg.kufar_url)
        kufar_fetched = len(kufar_items)
        fresh = [i for i in kufar_items if state.is_new("kufar", i.id)]
        kufar_new = len(fresh)
        if not kufar_fetched:
            try:
                html = await fetch_rendered_html(cfg.kufar_url, wait_selector="a[href*='/item/']")
                kufar_items = parse_kufar_html(html)
                kufar_fetched = len(kufar_items)
                fresh = [i for i in kufar_items if state.is_new("kufar", i.id)]
                kufar_new = len(fresh)
            except Exception as e2:
                logger.warning("kufar playwright fallback failed: %s", e2)
        if fresh:
            state.mark_seen("kufar", {i.id for i in fresh})
            new_items.extend(fresh)
        logger.info("kufar: fetched=%d new=%d", kufar_fetched, kufar_new)
        if fresh:
            logger.info("kufar new urls: %s", ", ".join(i.url for i in fresh[:3]))
    except Exception as e:
        logger.warning("kufar fetch failed: %s", e)

    domovita_fetched = 0
    domovita_new = 0
    try:
        domovita_items = fetch_domovita(cfg.domovita_url)
        domovita_fetched = len(domovita_items)
        fresh = [i for i in domovita_items if state.is_new("domovita", i.id)]
        domovita_new = len(fresh)
        if not domovita_fetched:
            try:
                html = await fetch_rendered_html(cfg.domovita_url, wait_selector="a[href*='/rent/']")
                domovita_items = parse_domovita_html(html)
                domovita_fetched = len(domovita_items)
                fresh = [i for i in domovita_items if state.is_new("domovita", i.id)]
                domovita_new = len(fresh)
            except Exception as e2:
                logger.warning("domovita playwright fallback failed: %s", e2)
        if fresh:
            state.mark_seen("domovita", {i.id for i in fresh})
            new_items.extend(fresh)
        logger.info("domovita: fetched=%d new=%d", domovita_fetched, domovita_new)
        if fresh:
            logger.info("domovita new urls: %s", ", ".join(i.url for i in fresh[:3]))
    except Exception as e:
        logger.warning("domovita fetch failed: %s", e)

    realt_fetched = 0
    realt_new = 0
    try:
        realt_items = fetch_realt(cfg.realt_url)
        realt_fetched = len(realt_items)
        fresh = [i for i in realt_items if state.is_new("realt", i.id)]
        realt_new = len(fresh)
        if not realt_fetched:
            try:
                html = await fetch_rendered_html(cfg.realt_url, wait_selector="a[href*='/rent/flat-for-long/']")
                realt_items = parse_realt_html(html)
                realt_fetched = len(realt_items)
                fresh = [i for i in realt_items if state.is_new("realt", i.id)]
                realt_new = len(fresh)
            except Exception as e2:
                logger.warning("realt playwright fallback failed: %s", e2)
        if fresh:
            state.mark_seen("realt", {i.id for i in fresh})
            new_items.extend(fresh)
        logger.info("realt: fetched=%d new=%d", realt_fetched, realt_new)
        if fresh:
            logger.info("realt new urls: %s", ", ".join(i.url for i in fresh[:3]))
    except Exception as e:
        logger.warning("realt fetch failed: %s", e)

    if new_items:
        state.reset_empty_cycles()
        await bot.broadcast(new_items)
        logger.info("broadcasting %d new items", len(new_items))
    else:
        empty = state.increment_empty_cycle()
        if empty % 5 == 0:
            await bot.notify_no_updates(empty)
        logger.info("no updates this cycle, empty_cycles=%d", empty)

    duration = time.perf_counter() - t0
    total_new = len(new_items)
    logger.info(
        "cycle: %.2fs | kufar fetched=%d new=%d | domovita fetched=%d new=%d | realt fetched=%d new=%d | total_new=%d | empty_cycles=%d",
        duration, kufar_fetched, kufar_new, domovita_fetched, domovita_new, realt_fetched, realt_new, total_new, state.empty_cycles,
    )

